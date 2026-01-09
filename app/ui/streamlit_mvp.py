"""
UI MVP para Phoenix Legal conectada con FastAPI backend.

Esta versión usa el cliente API para consumir los endpoints
endurecidos (PANTALLAS 0-6) en lugar del grafo antiguo.
"""
import streamlit as st
import io
from pathlib import Path
import sys

# Agregar path al proyecto
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.ui.api_client import PhoenixLegalClient

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

client = get_api_client()

# =========================================
# SIDEBAR: SELECCIÓN DE CASO
# =========================================

st.sidebar.title("⚖️ Phoenix Legal")
st.sidebar.markdown("---")

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
        case_options = {f"{case['name']} ({case['case_id'][:8]}...)": case['case_id'] 
                       for case in cases}
        selected_case_name = st.sidebar.selectbox(
            "Seleccionar caso:",
            options=["-- Nuevo Caso --"] + list(case_options.keys())
        )
        
        if selected_case_name != "-- Nuevo Caso --":
            selected_case_id = case_options[selected_case_name]
            st.session_state["selected_case_id"] = selected_case_id
        else:
            st.session_state["selected_case_id"] = None
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
tab1, tab2, tab3, tab4 = st.tabs([
    "🆕 Gestión de Casos",
    "📤 Documentos",
    "📊 Análisis",
    "📄 Informe Legal"
])

# =========================================
# TAB 1: GESTIÓN DE CASOS
# =========================================

with tab1:
    st.header("🆕 Gestión de Casos")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Crear Nuevo Caso")
        with st.form("create_case_form"):
            case_name = st.text_input(
                "Nombre del caso *",
                placeholder="Ej: Empresa XYZ - Concurso 2026"
            )
            client_ref = st.text_input(
                "Referencia del cliente (opcional)",
                placeholder="Ej: REF-2026-001"
            )
            
            submit = st.form_submit_button("✅ Crear Caso")
            
            if submit:
                if not case_name:
                    st.error("El nombre del caso es obligatorio")
                else:
                    try:
                        with st.spinner("Creando caso..."):
                            result = client.create_case(
                                name=case_name,
                                client_ref=client_ref if client_ref else None
                            )
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
                    if case['client_ref']:
                        st.write(f"**Ref. Cliente:** {case['client_ref']}")
        else:
            st.info("No hay casos creados todavía")

# =========================================
# TAB 2: DOCUMENTOS
# =========================================

with tab2:
    st.header("📤 Gestión de Documentos")
    
    if not st.session_state.get("selected_case_id"):
        st.warning("⚠️ Selecciona o crea un caso primero")
    else:
        case_id = st.session_state["selected_case_id"]
        
        # Obtener info del caso
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
            help="Formatos soportados: PDF, Excel (.xlsx, .xls), Word (.docx, .doc), TXT, CSV. Puedes subir múltiples archivos a la vez."
        )
        
        if uploaded_files:
            if st.button("📤 Subir Documentos", type="primary"):
                try:
                    with st.spinner(f"Subiendo {len(uploaded_files)} documento(s)..."):
                        files = [
                            (file.name, file.getvalue())
                            for file in uploaded_files
                        ]
                        results = client.upload_documents(case_id, files)
                    
                    st.success(f"✅ {len(results)} documento(s) subido(s)")
                    
                    # Mostrar resultados
                    for result in results:
                        status_icon = "✅" if result["status"] == "ingested" else "⚠️"
                        st.write(f"{status_icon} {result['filename']} - {result['status']}")
                        
                        # FASE 2A: Mostrar avisos de duplicados
                        if result.get("is_duplicate", False):
                            duplicate_filename = result.get("duplicate_of_filename", "desconocido")
                            similarity = result.get("duplicate_similarity", 0.0)
                            duplicate_action = result.get("duplicate_action")
                            
                            # Mostrar aviso con color de advertencia
                            if similarity == 1.0:
                                st.warning(
                                    f"⚠️  **DUPLICADO EXACTO**: Este documento tiene el mismo contenido que **{duplicate_filename}** (100% idéntico)"
                                )
                            else:
                                st.warning(
                                    f"⚠️  **DUPLICADO SEMÁNTICO**: Este documento es {similarity*100:.1f}% similar a **{duplicate_filename}**"
                                )
                            
                            # Si el abogado aún no ha tomado acción, mostrar opciones
                            if duplicate_action == "pending":
                                st.info("👨‍⚖️ **Decisión requerida**: ¿Qué deseas hacer con este documento?")
                                
                                col1, col2, col3 = st.columns(3)
                                
                                with col1:
                                    if st.button(
                                        "✅ Mantener ambos",
                                        key=f"keep_{result['document_id']}",
                                        help="Ambos documentos son relevantes y deben analizarse"
                                    ):
                                        try:
                                            updated = client.resolve_duplicate_action(
                                                case_id,
                                                result['document_id'],
                                                "keep_both"
                                            )
                                            st.success("✅ Ambos documentos serán analizados")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Error: {e}")
                                
                                with col2:
                                    if st.button(
                                        "🏷️ Marcar como duplicado",
                                        key=f"mark_{result['document_id']}",
                                        help="Este documento es redundante, pero mantenerlo para auditoría"
                                    ):
                                        try:
                                            updated = client.resolve_duplicate_action(
                                                case_id,
                                                result['document_id'],
                                                "mark_duplicate"
                                            )
                                            st.success("✅ Documento marcado como duplicado")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Error: {e}")
                                
                                with col3:
                                    if st.button(
                                        "🚫 Excluir del análisis",
                                        key=f"exclude_{result['document_id']}",
                                        help="Este documento no debe incluirse en el análisis legal"
                                    ):
                                        try:
                                            updated = client.resolve_duplicate_action(
                                                case_id,
                                                result['document_id'],
                                                "exclude_from_analysis"
                                            )
                                            st.success("✅ Documento excluido del análisis")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Error: {e}")
                            else:
                                # Ya se tomó una acción
                                action_labels = {
                                    "keep_both": "✅ Mantener ambos",
                                    "mark_duplicate": "🏷️ Marcado como duplicado",
                                    "exclude_from_analysis": "🚫 Excluido del análisis",
                                }
                                st.info(f"👨‍⚖️ **Decisión tomada**: {action_labels.get(duplicate_action, duplicate_action)}")
                    
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
                        if doc.get('error_message'):
                            st.error(f"Error: {doc['error_message']}")
            else:
                st.info("No hay documentos en este caso todavía")
        except Exception as e:
            st.error(f"Error al listar documentos: {e}")

# =========================================
# TAB 3: ANÁLISIS
# =========================================

with tab3:
    st.header("📊 Análisis Técnico")
    
    if not st.session_state.get("selected_case_id"):
        st.warning("⚠️ Selecciona o crea un caso primero")
    else:
        case_id = st.session_state["selected_case_id"]
        
        # Obtener alertas
        if st.button("🔍 Ejecutar Análisis", type="primary"):
            try:
                with st.spinner("Analizando caso..."):
                    alerts = client.get_analysis_alerts(case_id)
                
                if alerts:
                    st.success(f"✅ {len(alerts)} alerta(s) detectada(s)")
                    
                    # Agrupar por tipo
                    for alert in alerts:
                        severity_color = {
                            "high": "🔴",
                            "medium": "🟡",
                            "low": "🟢"
                        }.get(alert.get("severity", "low"), "⚪")
                        
                        with st.expander(f"{severity_color} {alert['alert_type']}"):
                            st.write(f"**Mensaje:** {alert['message']}")
                            if alert.get('evidence'):
                                st.write(f"**Evidencia:** {len(alert['evidence'])} documento(s)")
                else:
                    st.info("No se detectaron alertas en este caso")
            except Exception as e:
                st.error(f"Error al ejecutar análisis: {e}")

# =========================================
# TAB 4: INFORME LEGAL
# =========================================

with tab4:
    st.header("📄 Informe Legal")
    
    if not st.session_state.get("selected_case_id"):
        st.warning("⚠️ Selecciona o crea un caso primero")
    else:
        case_id = st.session_state["selected_case_id"]
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📄 Generar Informe Legal", type="primary"):
                try:
                    with st.spinner("Generando informe legal..."):
                        report = client.generate_legal_report(case_id)
                    
                    st.success("✅ Informe legal generado")
                    
                    # Mostrar resumen
                    st.subheader("📋 Resumen del Informe")
                    st.write(f"**ID del Informe:** `{report.get('report_id', 'N/A')}`")
                    st.write(f"**Generado:** {report.get('generated_at', 'N/A')}")
                    st.write(f"**Hallazgos:** {len(report.get('findings', []))}")
                    
                    # Mostrar findings
                    findings = report.get('findings', [])
                    if findings:
                        st.subheader("🔍 Hallazgos Legales")
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
