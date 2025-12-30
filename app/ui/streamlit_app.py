"""
UI Web para Phoenix Legal - MVP con Streamlit.

Interfaz mínima para usuarios (abogados/analistas) para:
- Crear/seleccionar casos
- Subir documentos
- Ejecutar análisis
- Ver estado
- Descargar PDF
"""
import streamlit as st
import os
from pathlib import Path
import time
from datetime import datetime

# Configuración de la página
st.set_page_config(
    page_title="Phoenix Legal",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Imports locales
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.graphs.audit_graph import build_audit_graph
from app.core.logger import get_logger
from app.core.monitoring import get_monitor

logger = get_logger()
monitor = get_monitor()

# Configuración
CASES_DIR = Path("clients_data/cases")
CASES_DIR.mkdir(parents=True, exist_ok=True)


def get_existing_cases():
    """Obtiene lista de casos existentes."""
    cases = []
    if CASES_DIR.exists():
        for case_dir in CASES_DIR.iterdir():
            if case_dir.is_dir():
                cases.append(case_dir.name)
    return sorted(cases)


def create_case(case_id: str):
    """Crea estructura de carpetas para un nuevo caso."""
    case_path = CASES_DIR / case_id
    docs_path = case_path / "documents"
    reports_path = case_path / "reports"
    
    docs_path.mkdir(parents=True, exist_ok=True)
    reports_path.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Caso creado", case_id=case_id, action="case_create")
    return case_path


def upload_document(case_id: str, uploaded_file):
    """Guarda un documento subido."""
    case_path = CASES_DIR / case_id
    docs_path = case_path / "documents"
    
    file_path = docs_path / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    logger.info(
        f"Documento subido",
        case_id=case_id,
        action="document_upload",
        filename=uploaded_file.name,
        size_bytes=uploaded_file.size
    )
    
    return file_path


def analyze_case(case_id: str):
    """Ejecuta análisis completo del caso."""
    from app.fixtures.audit_cases import CASE_RETAIL_001
    
    # Crear estado base
    state = {
        "case_id": case_id,
        "company_profile": CASE_RETAIL_001["company_profile"],
        "documents": [],
        "timeline": [],
        "risks": [],
        "missing_documents": [],
        "legal_findings": [],
        "auditor_llm": None,
        "prosecutor_llm": None,
        "rule_based_findings": [],
        "notes": None,
        "report": None,
    }
    
    # Cargar documentos del caso
    docs_path = CASES_DIR / case_id / "documents"
    if docs_path.exists():
        for doc_file in docs_path.iterdir():
            if doc_file.is_file():
                state["documents"].append({
                    "doc_id": doc_file.stem,
                    "doc_type": "documento",
                    "content": f"Documento: {doc_file.name}",
                    "date": datetime.now().isoformat()[:10],
                })
    
    # Ejecutar grafo
    with monitor.track_case_analysis(case_id):
        graph = build_audit_graph()
        result = graph.invoke(state)
    
    logger.info(
        f"Análisis completado",
        case_id=case_id,
        action="analysis_complete",
        risks_detected=len(result.get("risks", [])),
        findings=len(result.get("legal_findings", []))
    )
    
    return result


def get_latest_report(case_id: str):
    """Obtiene el último informe PDF generado."""
    reports_path = CASES_DIR / case_id / "reports"
    latest_file = reports_path / "latest.txt"
    
    if latest_file.exists():
        with open(latest_file, "r") as f:
            latest_pdf = f.read().strip()
        
        pdf_path = reports_path / latest_pdf
        if pdf_path.exists():
            return pdf_path
    
    # Buscar el último PDF por fecha
    if reports_path.exists():
        pdfs = sorted(reports_path.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        if pdfs:
            return pdfs[0]
    
    return None


# ======================================
# UI PRINCIPAL
# ======================================

st.title("⚖️ Phoenix Legal")
st.subheader("Sistema de Análisis Legal Automatizado")

# Sidebar
with st.sidebar:
    st.header("Navegación")
    page = st.radio(
        "Seleccionar acción:",
        ["📁 Gestión de Casos", "📊 Análisis", "📄 Informes", "📈 Métricas"]
    )
    
    st.markdown("---")
    st.caption("Phoenix Legal v2.0")
    st.caption("© 2024")

# ======================================
# PÁGINA: GESTIÓN DE CASOS
# ======================================

if page == "📁 Gestión de Casos":
    st.header("Gestión de Casos")
    
    tab1, tab2 = st.tabs(["Nuevo Caso", "Casos Existentes"])
    
    # Tab: Nuevo Caso
    with tab1:
        st.subheader("Crear Nuevo Caso")
        
        with st.form("new_case_form"):
            case_id = st.text_input(
                "ID del Caso",
                placeholder="ej: CASE_2024_001",
                help="Identificador único del caso"
            )
            
            submit = st.form_submit_button("Crear Caso")
            
            if submit:
                if not case_id:
                    st.error("❌ Debe proporcionar un ID de caso")
                elif case_id in get_existing_cases():
                    st.error(f"❌ El caso '{case_id}' ya existe")
                else:
                    try:
                        create_case(case_id)
                        st.success(f"✅ Caso '{case_id}' creado exitosamente")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error creando caso: {e}")
    
    # Tab: Casos Existentes
    with tab2:
        st.subheader("Casos Existentes")
        
        cases = get_existing_cases()
        
        if not cases:
            st.info("ℹ️ No hay casos creados aún")
        else:
            st.write(f"**Total de casos:** {len(cases)}")
            
            for case in cases:
                with st.expander(f"📁 {case}"):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        case_path = CASES_DIR / case
                        docs = list((case_path / "documents").glob("*")) if (case_path / "documents").exists() else []
                        reports = list((case_path / "reports").glob("*.pdf")) if (case_path / "reports").exists() else []
                        
                        st.write(f"📄 Documentos: {len(docs)}")
                        st.write(f"📊 Informes: {len(reports)}")
                    
                    with col2:
                        if st.button("Seleccionar", key=f"select_{case}"):
                            st.session_state["selected_case"] = case
                            st.success(f"✅ Caso '{case}' seleccionado")

# ======================================
# PÁGINA: ANÁLISIS
# ======================================

elif page == "📊 Análisis":
    st.header("Análisis de Caso")
    
    # Seleccionar caso
    selected_case = st.session_state.get("selected_case")
    
    if not selected_case:
        st.warning("⚠️ Primero seleccione un caso en 'Gestión de Casos'")
    else:
        st.info(f"📁 Caso seleccionado: **{selected_case}**")
        
        tab1, tab2 = st.tabs(["Subir Documentos", "Ejecutar Análisis"])
        
        # Tab: Subir Documentos
        with tab1:
            st.subheader("Subir Documentación")
            
            uploaded_files = st.file_uploader(
                "Seleccionar archivos",
                type=["pdf", "txt", "docx"],
                accept_multiple_files=True
            )
            
            if st.button("Subir Documentos"):
                if not uploaded_files:
                    st.error("❌ No se seleccionaron archivos")
                else:
                    progress_bar = st.progress(0)
                    for i, uploaded_file in enumerate(uploaded_files):
                        upload_document(selected_case, uploaded_file)
                        progress_bar.progress((i + 1) / len(uploaded_files))
                    
                    st.success(f"✅ {len(uploaded_files)} documento(s) subido(s) exitosamente")
            
            # Mostrar documentos existentes
            st.markdown("---")
            st.subheader("Documentos del Caso")
            
            docs_path = CASES_DIR / selected_case / "documents"
            if docs_path.exists():
                docs = list(docs_path.iterdir())
                if docs:
                    for doc in docs:
                        st.write(f"📄 {doc.name} ({doc.stat().st_size} bytes)")
                else:
                    st.info("ℹ️ No hay documentos subidos aún")
        
        # Tab: Ejecutar Análisis
        with tab2:
            st.subheader("Ejecutar Análisis Completo")
            
            st.warning("⚠️ El análisis puede tomar varios minutos. No cierre la página.")
            
            if st.button("▶️ Iniciar Análisis", type="primary"):
                try:
                    with st.spinner("🔄 Ejecutando análisis..."):
                        start_time = time.time()
                        
                        # Barra de progreso simulada
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        status_text.text("📝 Analizando documentos...")
                        progress_bar.progress(20)
                        
                        status_text.text("⏱️ Extrayendo timeline...")
                        progress_bar.progress(40)
                        
                        status_text.text("🔍 Detectando riesgos...")
                        progress_bar.progress(60)
                        
                        # Ejecutar análisis real
                        result = analyze_case(selected_case)
                        
                        status_text.text("🤖 Análisis LLM...")
                        progress_bar.progress(80)
                        
                        status_text.text("📄 Generando informe PDF...")
                        progress_bar.progress(100)
                        
                        elapsed = time.time() - start_time
                        
                        st.success(f"✅ Análisis completado en {elapsed:.1f} segundos")
                        
                        # Mostrar resumen
                        st.markdown("---")
                        st.subheader("Resumen del Análisis")
                        
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Riesgos Detectados", len(result.get("risks", [])))
                        
                        with col2:
                            st.metric("Hallazgos Legales", len(result.get("legal_findings", [])))
                        
                        with col3:
                            overall_risk = result.get("report", {}).get("overall_risk", "indeterminate")
                            st.metric("Riesgo Global", overall_risk.upper())
                        
                        st.info("ℹ️ Informe PDF generado. Descárguelo en la sección 'Informes'.")
                
                except Exception as e:
                    st.error(f"❌ Error durante el análisis: {e}")
                    logger.error("Error en análisis", case_id=selected_case, action="analysis_error", error=e)

# ======================================
# PÁGINA: INFORMES
# ======================================

elif page == "📄 Informes":
    st.header("Informes Generados")
    
    selected_case = st.session_state.get("selected_case")
    
    if not selected_case:
        st.warning("⚠️ Primero seleccione un caso en 'Gestión de Casos'")
    else:
        st.info(f"📁 Caso seleccionado: **{selected_case}**")
        
        # Buscar informe
        pdf_path = get_latest_report(selected_case)
        
        if pdf_path:
            st.success(f"✅ Informe disponible: {pdf_path.name}")
            
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**Tamaño:** {pdf_path.stat().st_size / 1024:.1f} KB")
                st.write(f"**Generado:** {datetime.fromtimestamp(pdf_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
            
            with col2:
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        label="⬇️ Descargar PDF",
                        data=f.read(),
                        file_name=pdf_path.name,
                        mime="application/pdf"
                    )
        else:
            st.info("ℹ️ No hay informes generados aún. Ejecute un análisis primero.")

# ======================================
# PÁGINA: MÉTRICAS
# ======================================

elif page == "📈 Métricas":
    st.header("Métricas del Sistema")
    
    metrics = monitor.get_metrics()
    
    # Métricas generales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Casos Analizados", metrics["total_cases_analyzed"])
    
    with col2:
        st.metric("Errores Totales", metrics["total_errors"])
    
    with col3:
        st.metric("Tiempo Promedio", f"{metrics['avg_execution_time_ms']/1000:.1f}s")
    
    with col4:
        llm_rate = metrics["llm"]["success_rate"]
        st.metric("LLM Success Rate", f"{llm_rate}%")
    
    # Métricas detalladas
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Llamadas LLM")
        st.write(f"**Total:** {metrics['llm']['total_calls']}")
        st.write(f"**Errores:** {metrics['llm']['errors']}")
        st.write(f"**Tasa de éxito:** {metrics['llm']['success_rate']}%")
    
    with col2:
        st.subheader("Consultas RAG")
        st.write(f"**Total:** {metrics['rag']['total_queries']}")
        st.write(f"**Errores:** {metrics['rag']['errors']}")
        st.write(f"**Tasa de éxito:** {metrics['rag']['success_rate']}%")
    
    # Tiempos por fase
    if metrics["phase_times"]:
        st.markdown("---")
        st.subheader("Tiempos por Fase")
        
        for phase, times in metrics["phase_times"].items():
            with st.expander(f"⏱️ {phase}"):
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Promedio", f"{times['avg_ms']}ms")
                with col2:
                    st.metric("Mínimo", f"{times['min_ms']}ms")
                with col3:
                    st.metric("Máximo", f"{times['max_ms']}ms")
                with col4:
                    st.metric("Ejecuciones", times['count'])
    
    st.markdown("---")
    st.caption(f"Última actualización: {metrics['generated_at']}")

