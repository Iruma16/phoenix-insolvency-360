import streamlit as st
import pandas as pd
import sqlite3
import analisis
import ingesta
import database
import json
import os
import time

st.set_page_config(page_title="Phoenix Legal", page_icon="⚖️", layout="wide")

# Título y estilo
st.title("🦅 Phoenix Insolvency 360")
st.markdown("---")

# --- MENÚ LATERAL ---
st.sidebar.header("📂 Panel de Control")
opcion = st.sidebar.radio("Navegación", ["Visión General (Dashboard)", "Subir Facturas", "Datos en Bruto", "Auditoría IA"])

def cargar_datos():
    conn = sqlite3.connect("phoenix.db")
    try:
        df_fact = pd.read_sql_query("SELECT * FROM facturas", conn)
        df_cont = pd.read_sql_query("SELECT * FROM contabilidad", conn)
        
        # Convertimos fechas a objetos de tiempo reales para poder GRAFICAR
        if not df_fact.empty and 'fecha_emision' in df_fact.columns:
            df_fact['fecha_emision'] = pd.to_datetime(df_fact['fecha_emision'], errors='coerce')
            
    except:
        df_fact, df_cont = pd.DataFrame(), pd.DataFrame()
    conn.close()
    return df_fact, df_cont

df_facturas, df_contabilidad = cargar_datos()

# --- 1. DASHBOARD VISUAL ---
if opcion == "Visión General (Dashboard)":
    st.header("📊 Cuadro de Mandos Financiero")
    
    col1, col2, col3 = st.columns(3)
    total_deuda = df_facturas['total_factura'].sum() if not df_facturas.empty else 0
    
    saldo_banco = 0
    if not df_contabilidad.empty:
        saldo_banco = df_contabilidad[df_contabilidad['concepto'].str.contains("Banco", na=False, case=False)]['importe'].sum()
        if saldo_banco == 0: 
            saldo_banco = df_contabilidad[df_contabilidad['tipo_deuda'] == 'Activo']['importe'].sum()

    diferencia = saldo_banco - total_deuda
    
    with col1: st.metric("Deuda Total", f"{total_deuda:,.2f} €", delta_color="inverse")
    with col2: st.metric("Tesorería", f"{saldo_banco:,.2f} €")
    with col3:
        estado = "INSOLVENCIA" if diferencia < 0 else "SOLVENTE"
        st.metric("Estado Técnico", estado, f"{diferencia:,.2f} €", delta_color="off" if diferencia > 0 else "inverse")

    st.markdown("---")

    # GRÁFICOS
    if not df_facturas.empty:
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("📈 Evolución del Impago")
            # Para graficar necesitamos fechas datetime (ya convertidas en cargar_datos)
            if 'fecha_emision' in df_facturas.columns:
                grafico_tiempo = df_facturas.set_index('fecha_emision')[['total_factura']].sort_index()
                st.line_chart(grafico_tiempo)
            else:
                st.warning("No hay fechas válidas para graficar.")

        with c2:
            st.subheader("🍩 Principales Acreedores")
            por_proveedor = df_facturas.groupby('proveedor')['total_factura'].sum()
            st.bar_chart(por_proveedor)
    else:
        st.info("Sube facturas para ver los gráficos de inteligencia de negocio.")

# --- 2. SUBIDA AUDITADA ---
elif opcion == "Subir Facturas":
    st.header("📥 Ingesta de Documentos")
    st.info("Sistema protegido: Rechaza duplicados y normaliza fechas.")
    
    archivo = st.file_uploader("Sube factura PDF", type="pdf")
    
    if archivo and st.button("🧠 Analizar, Validar y Guardar"):
        with open("temp.pdf", "wb") as f: f.write(archivo.getbuffer())
        texto_crudo = ingesta.leer_pdf("temp.pdf")
        
        if texto_crudo:
            datos = ingesta.extraer_datos_con_ia(texto_crudo)
            if datos:
                exito = database.guardar_factura_db(datos, texto_original=texto_crudo)
                if exito:
                    st.success(f"✅ Factura {datos['numero_factura']} procesada.")
                    st.balloons()
                    time.sleep(1) 
                    st.rerun() 
                else:
                    st.warning("⚠️ ALERTA: Factura duplicada.")
            else:
                st.error("❌ Error: Datos inválidos.")
            if os.path.exists("temp.pdf"): os.remove("temp.pdf")

# --- 3. TABLAS ---
elif opcion == "Datos en Bruto":
    tab1, tab2 = st.tabs(["Facturas", "Contabilidad"])
    with tab1: st.dataframe(df_facturas, use_container_width=True)
    with tab2: st.dataframe(df_contabilidad, use_container_width=True)

# --- 4. AUDITORÍA IA (CORREGIDO) ---
elif opcion == "Auditoría IA":
    st.header("🕵️‍♀️ Auditoría Forense & Generación de Informe")
    
    col_izq, col_der = st.columns([1, 3])
    with col_izq:
        boton_ejecutar = st.button("🚀 EJECUTAR ANÁLISIS", type="primary")
    
    if boton_ejecutar:
        if df_facturas.empty or df_contabilidad.empty:
            st.error("Faltan datos.")
        else:
            with st.spinner("El Agente IA está analizando evidencias..."):
                
                # --- CORRECCIÓN CRÍTICA ---
                # Creamos una copia para la IA y convertimos las fechas a TEXTO
                # para que JSON no falle.
                df_ia = df_facturas.copy()
                if 'fecha_emision' in df_ia.columns:
                    df_ia['fecha_emision'] = df_ia['fecha_emision'].astype(str)
                if 'created_at' in df_ia.columns:
                    df_ia['created_at'] = df_ia['created_at'].astype(str)

                informe = analisis.analizar_fraude(
                    df_ia.to_dict('records'), df_contabilidad.to_dict('records')
                )
                
                st.session_state['informe_generado'] = informe

    if 'informe_generado' in st.session_state:
        st.markdown("---")
        st.markdown("### 📑 Informe Ejecutivo Final")
        st.markdown(st.session_state['informe_generado'])
        st.markdown("---")
        st.download_button(
            label="💾 Descargar Informe (TXT)",
            data=st.session_state['informe_generado'],
            file_name="INFORME_FORENSE_PHOENIX.md",
            mime="text/markdown"
        )