import streamlit as st
import pandas as pd
import plotly.express as px

# --- 🏗️ IMPORTACIONES MODULARES ---
from core import database
from core import ingesta
from core import ingesta_csv
from core.init_db import init_db
from core.pdf_exporter import generar_pdf_informe
from agentes.auditor import analisis
from agentes.estratega import estratega

# --- 🧱 INICIALIZACIÓN DB (una sola vez) ---
if "db_initialized" not in st.session_state:
    init_db()
    st.session_state["db_initialized"] = True

# --- ⚙️ CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Phoenix Insolvency 360",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 🔄 MEMORIA: RECUPERACIÓN DE SESIÓN SQL ---
def inicializar_app():
    if 'df_banco' not in st.session_state:
        df_sql = database.cargar_datos_desde_sql()
        if df_sql is not None and not df_sql.empty:
            df_sql['Fecha'] = pd.to_datetime(df_sql['Fecha'], errors='coerce')
            st.session_state['df_banco'] = df_sql
            st.toast("✅ Datos bancarios recuperados", icon="💰")

    if 'texto_pdf' not in st.session_state:
        texto_guardado = database.recuperar_ultimo_pdf()
        if texto_guardado:
            st.session_state['texto_pdf'] = texto_guardado
            st.toast("✅ Texto de facturas recuperado", icon="📄")

inicializar_app()

# --- 🎨 CABECERA ---
st.title("🦅 Phoenix Insolvency 360")
st.markdown("**Plataforma de Auditoría Forense y Reestructuración con IA**")
st.markdown("---")

# --- 📂 SIDEBAR ---
with st.sidebar:
    st.header("📂 Expediente")

    tiene_datos = 'df_banco' in st.session_state and st.session_state['df_banco'] is not None

    if tiene_datos:
        filas = len(st.session_state['df_banco'])
        st.success(f"🟢 CASO ACTIVO: {filas} movimientos")

        with st.expander("➕ Añadir más documentos"):
            uploaded_extra = st.file_uploader(
                "Añadir Excel/CSV extra", type=["csv", "xlsx"], key="extra_upload"
            )
            if uploaded_extra and st.button("📥 Integrar Nuevos Datos"):
                df_new = ingesta_csv.leer_banco(uploaded_extra)
                if df_new is not None:
                    df_new['Fecha'] = pd.to_datetime(df_new['Fecha'], errors='coerce')
                    df_new['Fecha'] = df_new['Fecha'].dt.strftime("%Y-%m-%d")
                    df_new.loc[df_new['Fecha'].isna(), 'Fecha'] = None

                    nuevos, duplicados = database.insert_contabilidad(df_new)
                    st.success(f"✅ Añadidos {nuevos} registros")
                    if duplicados:
                        st.info(f"ℹ️ Omitidos {duplicados} duplicados")

                    st.session_state['df_banco'] = database.cargar_datos_desde_sql()
                    st.rerun()

        st.markdown("---")
        if st.button("🗑️ CERRAR CASO"):
            for k in ['df_banco', 'plan_viabilidad', 'informe_auditor', 'texto_pdf', 'pruebas_forenses']:
                st.session_state.pop(k, None)
            st.rerun()

    else:
        st.info("ℹ️ Inicia el caso subiendo los extractos bancarios.")
        uploaded_csv = st.file_uploader("Subir Banco (CSV/Excel)", type=["csv", "xlsx"])
        uploaded_pdf = st.file_uploader("Subir Facturas (PDF - Opcional)", type="pdf")

        if st.button("🚀 INICIAR PROCESAMIENTO", type="primary"):
            df = ingesta_csv.leer_banco(uploaded_csv)
            if df is not None:
                df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
                df['Fecha'] = df['Fecha'].dt.strftime("%Y-%m-%d")
                df.loc[df['Fecha'].isna(), 'Fecha'] = None

                database.insert_contabilidad(df)

                if uploaded_pdf:
                    texto_pdf = ingesta.extraer_texto_pdf(uploaded_pdf)
                    st.session_state['texto_pdf'] = texto_pdf
                    database.guardar_texto_pdf(uploaded_pdf.name, texto_pdf)

                st.session_state['df_banco'] = database.cargar_datos_desde_sql()
                st.rerun()

# --- 🖥️ PANEL PRINCIPAL ---
if tiene_datos:
    df = st.session_state['df_banco'].copy()

    tab1, tab2, tab3 = st.tabs([
        "🔍 1. Agente Auditor",
        "🧠 2. Agente Estratega",
        "📊 Datos Crudos"
    ])

    # --- AUDITOR ---
    with tab1:
        st.header("Análisis Financiero & Detección de Riesgos")

        df['Importe'] = pd.to_numeric(df['Importe'], errors='coerce').fillna(0)
        gastos = df[df['Importe'] < 0]['Importe'].sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Salidas Totales", f"{abs(gastos):,.2f} €")
        c2.metric("Registros Analizados", len(df))
        c3.metric("Estado", "En Revisión", "⚠️")

        df_chart = (
            df.groupby('Concepto')['Importe']
            .sum()
            .reset_index()
            .sort_values('Importe')
            .head(10)
        )
        st.plotly_chart(
            px.bar(df_chart, x='Importe', y='Concepto', orientation='h'),
            use_container_width=True
        )

        if st.button("🤖 EJECUTAR AUDITORÍA FORENSE (IA)"):
            with st.spinner("Analizando insolvencia..."):
                informe, pruebas = analisis.analizar_financiero(
                    st.session_state.get('texto_pdf', ""),
                    df
                )
                st.session_state['informe_auditor'] = informe
                st.session_state['pruebas_forenses'] = pruebas

        # --- PRUEBA OBJETIVA ---
        if 'pruebas_forenses' in st.session_state:
            pruebas = st.session_state['pruebas_forenses']
            st.subheader("🧾 Prueba objetiva (Banco ↔ Facturas)")

            col1, col2, col3 = st.columns(3)
            col1.metric("Pagos sin factura", len(pruebas.get("pagos_sin_factura", [])))
            col2.metric("Facturas sin pago", len(pruebas.get("facturas_sin_pago", [])))
            col3.metric("Descuadres", len(pruebas.get("descuadres", [])))

            with st.expander("🔍 Ver detalle"):
                for k, titulo in [
                    ("pagos_sin_factura", "❌ Pagos sin factura"),
                    ("facturas_sin_pago", "📄 Facturas sin pago"),
                    ("descuadres", "⚠️ Descuadres")
                ]:
                    if pruebas.get(k):
                        st.markdown(f"### {titulo}")
                        st.dataframe(pd.DataFrame(pruebas[k]), use_container_width=True)

        if (
            'informe_auditor' in st.session_state and
            'pruebas_forenses' in st.session_state
        ):
            if st.button("📄 Descargar informe legal (PDF)"):
                pdf_path = generar_pdf_informe(
                    st.session_state['informe_auditor'],
                    st.session_state['pruebas_forenses']
                )
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        label="⬇️ Descargar PDF",
                        data=f,
                        file_name="Informe_Phoenix_Forense.pdf",
                        mime="application/pdf"
                    )

            

    # --- ESTRATEGA ---
    with tab2:
        st.header("Plan de Viabilidad Legal")
        activos = st.number_input("Activos Líquidos (€)", value=1000, step=500)

        if st.button("⚖️ GENERAR ESTRATEGIA LEGAL", type="primary"):
            if 'informe_auditor' in st.session_state:
                deuda_total = abs(df['Importe'].sum())
                plan = estratega.generar_plan_viabilidad(
                    st.session_state['informe_auditor'][:2000],
                    deuda_total,
                    activos
                )
                st.session_state['plan_viabilidad'] = plan

        if 'plan_viabilidad' in st.session_state:
            st.markdown(st.session_state['plan_viabilidad'])
            st.download_button(
                "💾 Descargar Plan",
                st.session_state['plan_viabilidad'],
                "Plan_Viabilidad_Phoenix.md",
                "text/markdown"
            )

    # --- DATOS CRUDOS ---
    with tab3:
        st.dataframe(df, use_container_width=True)
