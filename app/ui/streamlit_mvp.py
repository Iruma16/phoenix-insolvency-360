"""
UI MVP para Phoenix Legal conectada con FastAPI backend.

Versión refactorizada con componentes reutilizables y caché.
"""
import streamlit as st
import io
from pathlib import Path
import sys

# Agregar path al proyecto
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.ui.api_client import (
    PhoenixLegalClient,
    CaseNotFoundError,
    ValidationErrorAPI,
    ParsingError,
    ServerError,
    PhoenixLegalAPIError,
)
from app.ui.components import (
    render_balance_block,
    render_credits_block,
    render_ratios_block,
    render_insolvency_block,
    render_timeline_block,
)

# Configuración de la página
st.set_page_config(
    page_title="Phoenix Legal - MVP",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar cliente API
@st.cache_resource
def get_api_client():
    return PhoenixLegalClient(base_url="http://localhost:8000")


# Caché para análisis financiero (5 minutos)
@st.cache_data(ttl=300)
def get_financial_analysis_cached(case_id: str):
    """
    Obtiene análisis financiero con caché.
    
    Args:
        case_id: ID del caso
        
    Returns:
        Dict con análisis financiero (serializable)
    """
    client = get_api_client()
    analysis = client.get_financial_analysis(case_id)
    
    # Convertir a dict para que sea cacheable
    return {
        'balance': analysis.balance.dict() if analysis.balance else None,
        'profit_loss': analysis.profit_loss.dict() if analysis.profit_loss else None,
        'credit_classification': [c.dict() for c in analysis.credit_classification],
        'total_debt': analysis.total_debt,
        'ratios': [r.dict() for r in analysis.ratios],
        'insolvency': analysis.insolvency.dict() if analysis.insolvency else None,
        'timeline': [t.dict() for t in analysis.timeline],
    }


client = get_api_client()

# =========================================
# SIDEBAR: HEALTH CHECK + SELECTOR DE CASOS
# =========================================

st.sidebar.title("⚖️ Phoenix Legal")

# Health check
try:
    health = client.health_check()
    st.sidebar.success(f"✅ API: {health['status']}")
except Exception as e:
    st.sidebar.error(f"❌ API no disponible: {e}")
    st.stop()

# Selector de caso
st.sidebar.subheader("📁 Casos")

# Listar casos existentes
try:
    cases = client.list_cases()
    if cases:
        case_options = {f"{case['name']} ({case['case_id'][:8]}...)": case['case_id'] for case in cases}
        selected_label = st.sidebar.selectbox(
            "Selecciona un caso:",
            options=list(case_options.keys()),
            key="case_selector"
        )
        st.session_state["selected_case_id"] = case_options[selected_label]
    else:
        st.sidebar.info("No hay casos creados")
        st.session_state["selected_case_id"] = None
except Exception as e:
    st.sidebar.error(f"Error al cargar casos: {e}")
    st.session_state["selected_case_id"] = None

# =========================================
# PANTALLA PRINCIPAL
# =========================================

# Tabs principales
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🆕 Gestión de Casos",
    "📤 Documentos",
    "📊 Análisis Financiero",
    "⚠️ Alertas",
    "📄 Informe Legal"
])

# =========================================
# TAB 1: GESTIÓN DE CASOS
# =========================================

with tab1:
    st.header("🆕 Gestión de Casos")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Crear Nuevo Caso")
        with st.form("create_case_form"):
            case_name = st.text_input("Nombre del Caso", placeholder="Ej: ACME SL - Concurso 2026")
            client_ref = st.text_input("Referencia Cliente (opcional)", placeholder="REF-2026-001")
            
            submitted = st.form_submit_button("Crear Caso", type="primary")
            
            if submitted and case_name:
                try:
                    result = client.create_case(case_name, client_ref if client_ref else None)
                    st.success(f"✅ Caso creado: {result['case_id']}")
                    st.session_state["selected_case_id"] = result['case_id']
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al crear caso: {e}")
    
    with col2:
        st.subheader("Casos Existentes")
        if cases:
            for case in cases:
                with st.expander(f"📁 {case['name']}"):
                    st.write(f"**ID:** `{case['case_id']}`")
                    st.write(f"**Creado:** {case['created_at']}")
                    st.write(f"**Documentos:** {case['documents_count']}")
                    st.write(f"**Estado:** {case['analysis_status']}")
        else:
            st.info("No hay casos todavía. Crea uno en el panel izquierdo.")

# =========================================
# TAB 2: DOCUMENTOS
# =========================================

with tab2:
    st.header("📤 Gestión de Documentos")
    
    if not st.session_state.get("selected_case_id"):
        st.warning("⚠️ Selecciona o crea un caso primero")
    else:
        case_id = st.session_state["selected_case_id"]
        
        # Mostrar info del caso
        try:
            case_info = client.get_case(case_id)
            st.info(f"📁 Caso: **{case_info['name']}** | 📊 Estado: **{case_info['analysis_status']}**")
        except Exception as e:
            st.error(f"Error al cargar caso: {e}")
        
        st.markdown("---")
        
        # Subir documentos
        st.subheader("📤 Subir Documentos")
        uploaded_files = st.file_uploader(
            "Selecciona archivos (PDF, Excel, Word, TXT, CSV, Email, Imágenes)",
            type=["pdf", "xlsx", "xls", "docx", "doc", "txt", "csv", "eml", "msg", "jpg", "jpeg", "png", "tiff", "tif"],
            accept_multiple_files=True,
            key="file_uploader"
        )
        
        if uploaded_files and st.button("📤 Subir Archivos", type="primary"):
            try:
                # Preparar archivos para check de duplicados
                files_data = []
                for file in uploaded_files:
                    file.seek(0)
                    content = file.read()
                    files_data.append((file.name, content))  # ✅ Solo nombre y contenido
                    file.seek(0)
                
                # Check duplicados
                with st.spinner("Verificando duplicados..."):
                    duplicates = client.check_duplicates_before_upload(case_id, files_data)
                
                if duplicates:
                    st.warning(f"⚠️ Se detectaron {len(duplicates)} archivo(s) duplicado(s)")
                    
                    for dup in duplicates:
                        st.write(f"- **{dup['filename']}**: {dup['duplicate_type']}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✅ Subir de todos modos"):
                            st.session_state["upload_confirmed"] = True
                            st.rerun()
                    with col2:
                        if st.button("❌ Cancelar"):
                            st.info("Subida cancelada")
                            st.stop()
                
                # Si no hay duplicados o usuario confirmó, subir
                if not duplicates or st.session_state.get("upload_confirmed"):
                    with st.spinner(f"Subiendo {len(uploaded_files)} archivo(s)..."):
                        files_for_upload = [
                            (file.name, file.getvalue())  # ✅ Solo nombre y contenido
                            for file in uploaded_files
                        ]
                        result = client.upload_documents(case_id, files_for_upload)
                    
                    st.success(f"✅ {result['uploaded_count']} documento(s) subido(s)")
                    
                    if result.get('errors'):
                        st.warning(f"⚠️ {len(result['errors'])} error(es)")
                        for error in result['errors']:
                            st.error(f"- {error['filename']}: {error['error']}")
                    
                    st.session_state["upload_confirmed"] = False
                    st.rerun()
                
            except Exception as e:
                st.error(f"Error al subir documentos: {e}")
        
        st.markdown("---")
        
        # Listar documentos existentes
        st.subheader("📚 Documentos del Caso")
        try:
            documents = client.list_documents(case_id)
            if documents:
                for doc in documents:
                    status_color = {
                        "ingested": "🟢",
                        "pending": "🟡",
                        "failed": "🔴"
                    }.get(doc["status"], "⚪")
                    
                    with st.expander(f"{status_color} {doc['filename']}"):
                        st.write(f"**ID:** `{doc['document_id']}`")
                        st.write(f"**Estado:** {doc['status']}")
                        st.write(f"**Chunks:** {doc['chunks_count']}")
                        st.write(f"**Subido:** {doc['created_at']}")
                        if doc["status"] == "failed":
                            st.error(f"Error: {doc['error_message']}")
            else:
                st.info("No hay documentos en este caso todavía")
        except Exception as e:
            st.error(f"Error al listar documentos: {e}")

# =========================================
# TAB 3: ANÁLISIS FINANCIERO
# =========================================

with tab3:
    st.header("📊 ANÁLISIS FINANCIERO Y SITUACIÓN PATRIMONIAL")
    
    if not st.session_state.get("selected_case_id"):
        st.warning("⚠️ Selecciona o crea un caso primero")
    else:
        case_id = st.session_state["selected_case_id"]
        
        # Botones para ejecutar y limpiar caché
        col1, col2 = st.columns([3, 1])
        
        with col1:
            execute_analysis = st.button("🔍 Ejecutar Análisis Financiero", type="primary")
        
        with col2:
            if st.button("🔄 Forzar Recalcular"):
                get_financial_analysis_cached.clear()
                st.success("✅ Caché limpiado")
                st.rerun()
        
        if execute_analysis:
            try:
                with st.spinner("Analizando situación financiera..."):
                    # Usar versión cacheada
                    analysis_dict = get_financial_analysis_cached(case_id)
                
                # Extraer datos del dict cacheado
                balance_dict = analysis_dict['balance']
                profit_loss_dict = analysis_dict['profit_loss']
                credits_dicts = analysis_dict['credit_classification']
                total_debt = analysis_dict['total_debt']
                ratios_dicts = analysis_dict['ratios']
                insolvency_dict = analysis_dict['insolvency']
                timeline_dicts = analysis_dict['timeline']
                
                # Usar componentes para renderizar
                render_balance_block(balance_dict, profit_loss_dict)
                render_credits_block(credits_dicts, total_debt)
                render_ratios_block(ratios_dicts)
                render_insolvency_block(insolvency_dict)
                render_timeline_block(timeline_dicts)
            
            except CaseNotFoundError as e:
                st.error(f"❌ **Caso no encontrado**")
                st.write(str(e))
                st.info("💡 Verifica que el caso existe en la lista de casos del sidebar")
            
            except ValidationErrorAPI as e:
                st.error(f"❌ **Error de validación**")
                st.write(str(e))
                st.info("💡 Los documentos subidos pueden tener formato incorrecto o datos inválidos")
            
            except ParsingError as e:
                st.error(f"❌ **Error al procesar documentos**")
                st.write(str(e))
                st.warning("⚠️ El servidor tuvo problemas al extraer datos de los documentos")
                st.info("💡 **Posibles soluciones:**")
                st.write("- Sube documentos con formato más estructurado (Excel, PDF con texto)")
                st.write("- Verifica que los PDFs no sean escaneados sin OCR")
                st.write("- Asegúrate de que los archivos no estén corruptos")
            
            except ServerError as e:
                st.error(f"❌ **Error interno del servidor**")
                st.write(str(e))
                st.warning("⚠️ Hubo un problema en el servidor al procesar la solicitud")
                st.info("💡 Intenta de nuevo en unos momentos o contacta al administrador")
            
            except PhoenixLegalAPIError as e:
                st.error(f"❌ **Error de API**")
                st.write(str(e))
                
                # Si es timeout o conexión, dar más contexto
                error_msg = str(e).lower()
                if "timeout" in error_msg:
                    st.warning("⏱️ El análisis está tardando más de lo esperado")
                    st.info("💡 Esto puede ocurrir con muchos documentos. Intenta:")
                    st.write("- Reducir el número de documentos")
                    st.write("- Subir documentos más pequeños")
                elif "conectar" in error_msg or "connection" in error_msg:
                    st.warning("🔌 No se pudo conectar al servidor")
                    st.info("💡 Verifica que el servidor API esté levantado:")
                    st.code("uvicorn app.main:app --reload --port 8000", language="bash")
            
            except Exception as e:
                st.error(f"❌ **Error inesperado**")
                st.write(f"Tipo: `{type(e).__name__}`")
                st.write(f"Mensaje: {e}")
                import traceback
                with st.expander("🔍 Ver traza completa (para debugging)"):
                    st.code(traceback.format_exc())

# =========================================
# TAB 4: ALERTAS TÉCNICAS
# =========================================

with tab4:
    st.header("⚠️ Alertas Técnicas")
    
    if not st.session_state.get("selected_case_id"):
        st.warning("⚠️ Selecciona o crea un caso primero")
    else:
        case_id = st.session_state["selected_case_id"]
        
        if st.button("🔍 Verificar Alertas", type="primary"):
            try:
                with st.spinner("Analizando calidad de datos..."):
                    alerts = client.get_alerts(case_id)
                
                if alerts:
                    st.warning(f"⚠️ Se detectaron {len(alerts)} alerta(s)")
                    
                    for alert in alerts:
                        severity_color = {
                            "critical": "🔴",
                            "warning": "🟡",
                            "info": "🔵"
                        }.get(alert['severity'], "⚪")
                        
                        with st.expander(f"{severity_color} {alert['alert_type']}"):
                            st.write(f"**Mensaje:** {alert['message']}")
                            if alert.get('evidence'):
                                st.write(f"**Evidencia:** {len(alert['evidence'])} documento(s)")
                else:
                    st.success("✅ No se detectaron problemas de calidad en los datos")
            except Exception as e:
                st.error(f"Error al verificar alertas: {e}")

# =========================================
# TAB 5: INFORME LEGAL
# =========================================

with tab5:
    st.header("📄 Informe Legal")
    
    if not st.session_state.get("selected_case_id"):
        st.warning("⚠️ Selecciona o crea un caso primero")
    else:
        case_id = st.session_state["selected_case_id"]
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📝 Generar Informe", type="primary"):
                try:
                    with st.spinner("Generando informe legal..."):
                        report = client.generate_legal_report(case_id)
                    
                    st.success(f"✅ Informe generado")
                    
                    st.subheader("📋 Resumen del Informe")
                    st.write(f"**ID del Informe:** `{report['report_id']}`")
                    st.write(f"**Generado:** {report['generated_at']}")
                    st.write(f"**Hallazgos:** {len(report.get('findings', []))}")
                    
                    if report.get('findings'):
                        st.subheader("🔍 Hallazgos Principales")
                        findings = report['findings']
                        for i, finding in enumerate(findings, 1):
                            with st.expander(f"{i}. {finding.get('title', 'Sin título')}"):
                                st.write(finding.get('description', 'Sin descripción'))
                                if finding.get('evidence'):
                                    st.write(f"**Evidencia:** {len(finding['evidence'])} documento(s)")
                
                except Exception as e:
                    st.error(f"Error al generar informe: {e}")
        
        with col2:
            if st.button("⬇️ Descargar PDF Certificado"):
                try:
                    with st.spinner("Generando PDF..."):
                        pdf_content = client.download_pdf_report(case_id)
                    
                    st.download_button(
                        label="📥 Descargar PDF",
                        data=pdf_content,
                        file_name=f"informe_legal_{case_id[:8]}.pdf",
                        mime="application/pdf"
                    )
                    st.success("✅ PDF generado")
                except Exception as e:
                    st.error(f"Error al descargar PDF: {e}")

# =========================================
# FOOTER
# =========================================

st.markdown("---")
st.caption("⚖️ Phoenix Legal - Sistema de Análisis Legal Automatizado | v1.0.0")
st.caption("⚠️ Este es un sistema de asistencia técnica. Requiere revisión por profesional legal cualificado.")
