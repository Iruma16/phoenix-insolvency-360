"""
UI Web para Phoenix Legal - MVP con Streamlit.

Interfaz mínima para usuarios (abogados/analistas) para:
- Crear/seleccionar casos
- Subir documentos
- Ejecutar análisis
- Ver estado
- Descargar PDF

VERSIÓN: 2.1.0 - Corregida y hardened
"""
import streamlit as st
import os
from pathlib import Path
import time
from datetime import datetime
from typing import Optional
import hashlib

# Configuración de la página
st.set_page_config(
    page_title="Phoenix Legal",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

from app.graphs.audit_graph import build_audit_graph
from app.core.logger import get_logger
from app.core.monitoring import get_monitor

logger = get_logger()
monitor = get_monitor()

# Disclaimer legal
from app.services.legal_disclaimer import DISCLAIMER_UI_DEMO

# Configuración
CASES_DIR = Path("clients_data/cases")
CASES_DIR.mkdir(parents=True, exist_ok=True)

# Límites de seguridad
MAX_FILE_SIZE_MB = 50
ALLOWED_EXTENSIONS = [".pdf", ".txt", ".docx", ".xlsx", ".xls", ".eml", ".msg", ".png", ".jpg", ".jpeg", ".csv"]


def format_file_size(size_bytes: int) -> str:
    """Convierte bytes a formato human-readable."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def validate_case_id(case_id: str) -> tuple[bool, str]:
    """Valida el formato del case_id."""
    if not case_id:
        return False, "El ID del caso no puede estar vacío"
    
    if len(case_id) < 3:
        return False, "El ID debe tener al menos 3 caracteres"
    
    if len(case_id) > 100:
        return False, "El ID no puede exceder 100 caracteres"
    
    # Solo alfanuméricos, guiones y guiones bajos
    if not all(c.isalnum() or c in ['_', '-'] for c in case_id):
        return False, "Solo se permiten letras, números, guiones y guiones bajos"
    
    if case_id.strip() != case_id:
        return False, "El ID no puede tener espacios al inicio o final"
    
    return True, "OK"


def get_existing_cases():
    """Obtiene lista de casos existentes."""
    cases = []
    if CASES_DIR.exists():
        for case_dir in CASES_DIR.iterdir():
            if case_dir.is_dir() and not case_dir.name.startswith('.'):
                cases.append(case_dir.name)
    return sorted(cases)


def create_case(case_id: str):
    """Crea estructura de carpetas para un nuevo caso."""
    case_path = CASES_DIR / case_id
    docs_path = case_path / "documents"
    reports_path = case_path / "reports"
    
    docs_path.mkdir(parents=True, exist_ok=True)
    reports_path.mkdir(parents=True, exist_ok=True)
    
    logger.info("Caso creado", case_id=case_id, action="case_create")
    return case_path


def get_file_hash(file_content: bytes) -> str:
    """Calcula hash MD5 del contenido del archivo."""
    return hashlib.md5(file_content).hexdigest()


def upload_document(case_id: str, uploaded_file) -> tuple[bool, str, Optional[Path]]:
    """
    Guarda un documento subido con validaciones y detección de duplicados.
    
    Returns:
        (success, message, file_path)
    """
    case_path = CASES_DIR / case_id
    docs_path = case_path / "documents"
    
    # Crear directorio si no existe
    docs_path.mkdir(parents=True, exist_ok=True)
    
    # Validar extensión
    file_ext = Path(uploaded_file.name).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return False, f"Extensión {file_ext} no permitida", None
    
    # Validar tamaño
    file_size = uploaded_file.size
    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        return False, f"Archivo demasiado grande ({format_file_size(file_size)}). Máximo: {MAX_FILE_SIZE_MB} MB", None
    
    if file_size == 0:
        return False, "El archivo está vacío", None
    
    # Leer contenido
    file_content = uploaded_file.getvalue()
    file_hash = get_file_hash(file_content)
    
    file_path = docs_path / uploaded_file.name
    
    # Detectar duplicado por nombre
    if file_path.exists():
        # Comparar hash para ver si es realmente el mismo archivo
        existing_hash = get_file_hash(file_path.read_bytes())
        if existing_hash == file_hash:
            return False, f"⚠️ Duplicado: '{uploaded_file.name}' (mismo contenido)", file_path
        else:
            return False, f"⚠️ Existe '{uploaded_file.name}' con contenido diferente. Renómbrelo primero.", file_path
    
    # Guardar archivo
    try:
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        logger.info(
            "Documento subido",
            case_id=case_id,
            action="document_upload",
            filename=uploaded_file.name,
            size_bytes=file_size,
            file_hash=file_hash
        )
        
        return True, f"✅ '{uploaded_file.name}' subido ({format_file_size(file_size)})", file_path
    
    except Exception as e:
        logger.error(
            "Error subiendo documento",
            case_id=case_id,
            filename=uploaded_file.name,
            error_type=type(e).__name__,
            error_message=str(e)
        )
        return False, f"Error guardando archivo: {str(e)}", None


def read_document_content(file_path: Path) -> str:
    """Lee el contenido real de un documento."""
    try:
        ext = file_path.suffix.lower()
        
        # Archivos de texto plano
        if ext in ['.txt', '.eml', '.csv']:
            return file_path.read_text(encoding='utf-8', errors='ignore')
        
        # Por ahora, para otros formatos solo retornamos metadatos
        # TODO: Integrar parsers para PDF, DOCX, XLSX
        return f"[Archivo {ext.upper()}: {file_path.name}]"
    
    except Exception as e:
        logger.warning(
            "Error leyendo documento",
            filename=file_path.name,
            error_type=type(e).__name__,
            error_message=str(e)
        )
        return f"[Error leyendo {file_path.name}]"


def analyze_case(case_id: str) -> Optional[dict]:
    """
    Ejecuta análisis completo del caso.
    
    CORREGIDO: Usa dict con estructura AuditState (no PhoenixState).
    El grafo espera dict simple, no objetos Pydantic.
    """
    try:
        # Cargar documentos del caso
        documents = []
        docs_path = CASES_DIR / case_id / "documents"
        
        if not docs_path.exists():
            raise ValueError(f"No existe el directorio de documentos para el caso {case_id}")
        
        doc_files = sorted(docs_path.iterdir(), key=lambda p: p.name)
        
        for doc_file in doc_files:
            if doc_file.is_file() and not doc_file.name.startswith('.'):
                content = read_document_content(doc_file)
                
                # Crear dict simple (TypedDict Document)
                documents.append({
                    "doc_id": doc_file.stem,
                    "doc_type": "documento",  # TODO: Inferir tipo por nombre/extensión
                    "content": content,
                    "date": datetime.now().isoformat()[:10]
                })
        
        if not documents:
            raise ValueError(f"No hay documentos para analizar en el caso {case_id}")
        
        # Crear dict simple con estructura AuditState
        # El grafo usa TypedDict, no Pydantic
        state = {
            "case_id": case_id,
            "company_profile": {},
            "documents": documents,  # ← En el root, no en inputs.documents
            "timeline": [],
            "risks": [],
            "missing_documents": [],
            "legal_findings": [],
            "auditor_llm": None,
            "prosecutor_llm": None,
            "rule_based_findings": [],
            "notes": None,
            "report": None
        }
        
        logger.info(
            "Iniciando análisis",
            case_id=case_id,
            action="analysis_start",
            num_documents=len(documents)
        )
        
        # Ejecutar grafo
        graph = build_audit_graph()
        result = graph.invoke(state)
        
        # Resultado es dict con estructura AuditState
        num_risks = len(result.get("risks", []))
        num_findings = len(result.get("legal_findings", []))
        
        logger.info(
            "Análisis completado",
            case_id=case_id,
            action="analysis_complete",
            risks_detected=num_risks,
            findings=num_findings
        )
        
        return result
    
    except Exception as e:
        logger.error(
            "Error en análisis",
            case_id=case_id,
            action="analysis_error",
            error_type=type(e).__name__,
            error_message=str(e)
        )
        raise


def get_latest_report(case_id: str) -> Optional[Path]:
    """Obtiene el último informe PDF generado."""
    try:
        reports_path = CASES_DIR / case_id / "reports"
        
        if not reports_path.exists():
            return None
        
        latest_file = reports_path / "latest.txt"
        
        if latest_file.exists():
            try:
                with open(latest_file, "r", encoding='utf-8') as f:
                    latest_pdf = f.read().strip()
                
                pdf_path = reports_path / latest_pdf
                if pdf_path.exists():
                    return pdf_path
            except Exception as e:
                logger.warning("Error leyendo latest.txt", error=str(e))
        
        # Buscar el último PDF por fecha
        pdfs = sorted(
            reports_path.glob("*.pdf"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        return pdfs[0] if pdfs else None
    
    except Exception as e:
        logger.error(
            "Error buscando reporte",
            case_id=case_id,
            error_type=type(e).__name__,
            error_message=str(e)
        )
        return None


# ======================================
# UI PRINCIPAL
# ======================================

st.title("⚖️ Phoenix Legal")
st.subheader("Sistema de Análisis Legal Automatizado")

# ════════════════════════════════════════════════════════════════
# DISCLAIMER DEMO (OBLIGATORIO)
# ════════════════════════════════════════════════════════════════
st.warning(DISCLAIMER_UI_DEMO)

# Sidebar
with st.sidebar:
    st.header("Navegación")
    page = st.radio(
        "Seleccionar acción:",
        ["📁 Gestión de Casos", "📊 Análisis", "📄 Informes", "📈 Métricas"]
    )
    
    st.markdown("---")
    st.caption("Phoenix Legal v2.1.0")
    st.caption("© 2026")

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
                placeholder="ej: CASE_2026_001",
                help="Identificador único del caso (letras, números, guiones y guiones bajos)"
            )
            
            submit = st.form_submit_button("Crear Caso")
            
            if submit:
                # Validar formato
                is_valid, validation_msg = validate_case_id(case_id)
                
                if not is_valid:
                    st.error(f"❌ {validation_msg}")
                elif case_id in get_existing_cases():
                    st.error(f"❌ El caso '{case_id}' ya existe")
                else:
                    try:
                        create_case(case_id)
                        st.success(f"✅ Caso '{case_id}' creado exitosamente")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error creando caso: {e}")
                        logger.error("Error creando caso", case_id=case_id, error=str(e))
    
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
                        docs_dir = case_path / "documents"
                        reports_dir = case_path / "reports"
                        
                        docs = list(docs_dir.glob("*")) if docs_dir.exists() else []
                        reports = list(reports_dir.glob("*.pdf")) if reports_dir.exists() else []
                        
                        # Calcular tamaño total
                        total_size = sum(d.stat().st_size for d in docs if d.is_file())
                        
                        st.write(f"📄 Documentos: {len(docs)} ({format_file_size(total_size)})")
                        st.write(f"📊 Informes: {len(reports)}")
                    
                    with col2:
                        if st.button("Seleccionar", key=f"select_{case}"):
                            st.session_state["selected_case"] = case
                            st.success(f"✅ Caso '{case}' seleccionado")
                            st.rerun()

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
            
            st.info(f"📏 Tamaño máximo por archivo: {MAX_FILE_SIZE_MB} MB")
            
            uploaded_files = st.file_uploader(
                "Seleccionar archivos",
                type=["pdf", "txt", "docx", "xlsx", "xls", "eml", "msg", "png", "jpg", "jpeg", "csv"],
                accept_multiple_files=True,
                help=f"Formatos permitidos: {', '.join(ALLOWED_EXTENSIONS)}"
            )
            
            if st.button("Subir Documentos"):
                if not uploaded_files:
                    st.error("❌ No se seleccionaron archivos")
                else:
                    progress_bar = st.progress(0)
                    status = st.empty()
                    
                    success_count = 0
                    duplicate_count = 0
                    error_count = 0
                    messages = []
                    
                    for i, uploaded_file in enumerate(uploaded_files):
                        status.text(f"Subiendo {i+1}/{len(uploaded_files)}: {uploaded_file.name}")
                        
                        success, msg, _ = upload_document(selected_case, uploaded_file)
                        
                        if success:
                            success_count += 1
                        elif "Duplicado" in msg:
                            duplicate_count += 1
                        else:
                            error_count += 1
                        
                        messages.append(msg)
                        progress_bar.progress((i + 1) / len(uploaded_files))
                    
                    status.empty()
                    
                    # Mostrar resumen
                    if success_count > 0:
                        st.success(f"✅ {success_count} archivo(s) subido(s) exitosamente")
                    if duplicate_count > 0:
                        st.warning(f"⚠️ {duplicate_count} duplicado(s) detectado(s)")
                    if error_count > 0:
                        st.error(f"❌ {error_count} error(es)")
                    
                    # Mostrar detalles
                    with st.expander("Ver detalles"):
                        for msg in messages:
                            st.write(msg)
            
            # Mostrar documentos existentes
            st.markdown("---")
            st.subheader("Documentos del Caso")
            
            docs_path = CASES_DIR / selected_case / "documents"
            if docs_path.exists():
                docs = sorted(docs_path.iterdir(), key=lambda p: p.name)
                docs = [d for d in docs if d.is_file() and not d.name.startswith('.')]
                
                if docs:
                    total_size = sum(d.stat().st_size for d in docs)
                    st.write(f"**Total:** {len(docs)} documentos ({format_file_size(total_size)})")
                    
                    for doc in docs:
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.write(f"📄 {doc.name}")
                        with col2:
                            st.caption(format_file_size(doc.stat().st_size))
                else:
                    st.info("ℹ️ No hay documentos subidos aún")
            else:
                st.info("ℹ️ No hay documentos subidos aún")
        
        # Tab: Ejecutar Análisis
        with tab2:
            st.subheader("Ejecutar Análisis Completo")
            
            # Verificar que hay documentos
            docs_path = CASES_DIR / selected_case / "documents"
            has_docs = docs_path.exists() and any(docs_path.iterdir())
            
            if not has_docs:
                st.warning("⚠️ No hay documentos para analizar. Suba documentos primero.")
            else:
                st.warning("⚠️ El análisis puede tomar varios minutos. No cierre la página.")
                
                if st.button("▶️ Iniciar Análisis", type="primary"):
                    try:
                        with st.spinner("🔄 Ejecutando análisis..."):
                            start_time = time.time()
                            
                            # Ejecutar análisis real
                            result = analyze_case(selected_case)
                            
                            elapsed = time.time() - start_time
                            
                            st.success(f"✅ Análisis completado en {elapsed:.1f} segundos")
                            
                            # Mostrar resumen
                            st.markdown("---")
                            st.subheader("Resumen del Análisis")
                            
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                num_risks = len(result.get("risks", []))
                                st.metric("Riesgos Detectados", num_risks)
                            
                            with col2:
                                num_findings = len(result.get("legal_findings", []))
                                st.metric("Hallazgos Legales", num_findings)
                            
                            with col3:
                                overall_risk = result.get("report", {}).get("overall_risk", "N/A") if isinstance(result.get("report"), dict) else "N/A"
                                st.metric("Riesgo Global", str(overall_risk).upper())
                            
                            st.info("ℹ️ Informe PDF generado. Descárguelo en la sección 'Informes'.")
                    
                    except ValueError as e:
                        st.error(f"❌ Error de validación: {e}")
                    except Exception as e:
                        st.error(f"❌ Error durante el análisis: {type(e).__name__}: {e}")
                        logger.error(
                            "Error en UI durante análisis",
                            case_id=selected_case,
                            error_type=type(e).__name__,
                            error_message=str(e)
                        )

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
                file_size = pdf_path.stat().st_size
                file_time = datetime.fromtimestamp(pdf_path.stat().st_mtime)
                
                st.write(f"**Tamaño:** {format_file_size(file_size)}")
                st.write(f"**Generado:** {file_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            with col2:
                # Leer archivo para descarga
                try:
                    with open(pdf_path, "rb") as f:
                        pdf_data = f.read()
                    
                    st.download_button(
                        label="⬇️ Descargar PDF",
                        data=pdf_data,
                        file_name=pdf_path.name,
                        mime="application/pdf"
                    )
                except Exception as e:
                    st.error(f"Error leyendo PDF: {e}")
        else:
            st.info("ℹ️ No hay informes generados aún. Ejecute un análisis primero.")

# ======================================
# PÁGINA: MÉTRICAS
# ======================================

elif page == "📈 Métricas":
    st.header("Métricas del Sistema")
    
    try:
        metrics = monitor.get_metrics()
        
        # Métricas generales
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Casos Analizados", metrics.get("total_cases_analyzed", 0))
        
        with col2:
            st.metric("Errores Totales", metrics.get("total_errors", 0))
        
        with col3:
            avg_time = metrics.get("avg_execution_time_ms", 0) / 1000
            st.metric("Tiempo Promedio", f"{avg_time:.1f}s")
        
        with col4:
            llm_rate = metrics.get("llm", {}).get("success_rate", 0)
            st.metric("LLM Success Rate", f"{llm_rate}%")
        
        # Métricas detalladas
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Llamadas LLM")
            llm = metrics.get("llm", {})
            st.write(f"**Total:** {llm.get('total_calls', 0)}")
            st.write(f"**Errores:** {llm.get('errors', 0)}")
            st.write(f"**Tasa de éxito:** {llm.get('success_rate', 0)}%")
        
        with col2:
            st.subheader("Consultas RAG")
            rag = metrics.get("rag", {})
            st.write(f"**Total:** {rag.get('total_queries', 0)}")
            st.write(f"**Errores:** {rag.get('errors', 0)}")
            st.write(f"**Tasa de éxito:** {rag.get('success_rate', 0)}%")
        
        # Tiempos por fase
        phase_times = metrics.get("phase_times", {})
        if phase_times:
            st.markdown("---")
            st.subheader("Tiempos por Fase")
            
            for phase, times in phase_times.items():
                with st.expander(f"⏱️ {phase}"):
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Promedio", f"{times.get('avg_ms', 0)}ms")
                    with col2:
                        st.metric("Mínimo", f"{times.get('min_ms', 0)}ms")
                    with col3:
                        st.metric("Máximo", f"{times.get('max_ms', 0)}ms")
                    with col4:
                        st.metric("Ejecuciones", times.get('count', 0))
        
        st.markdown("---")
        st.caption(f"Última actualización: {metrics.get('generated_at', 'N/A')}")
    
    except Exception as e:
        st.error(f"❌ Error cargando métricas: {e}")
        logger.error("Error cargando métricas", error_type=type(e).__name__, error_message=str(e))
