"""
UI MVP para Phoenix Legal conectada con FastAPI backend.

Versión refactorizada con componentes reutilizables y caché.
"""
import os
import inspect
import json
import time
import re
from pathlib import Path
from typing import Any, Optional
import io
from datetime import datetime, timezone
import traceback

import streamlit as st
import streamlit.components.v1 as components

# Cargar variables desde .env (si existe)
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # No bloquear la UI si python-dotenv no está disponible
    pass

from app.ui.api_client import (
    CaseNotFoundError,
    ParsingError,
    PhoenixLegalAPIError,
    PhoenixLegalClient,
    ServerError,
    ValidationErrorAPI,
)
from app.ui.components import (
    render_balance_block,
    render_credits_block,
    render_insolvency_block,
    render_ratios_block,
    render_suspicious_patterns,
    render_timeline_block_backend,  # ✅ Nueva versión escalable
)
from app.ui.components_modules.evidence import render_alert_evidence_list
from app.services import court_pack_service, pdf_form_filler
from app.models.court_pack import CourtPackState, DebtorFlags

# Configuración de la página
st.set_page_config(
    page_title="Phoenix Legal - MVP", page_icon="⚖️", layout="wide", initial_sidebar_state="expanded"
)

# Bump this cuando cambie la API del cliente (evita bugs por cache viejo)
CLIENT_API_VERSION = 5


# Inicializar cliente API
@st.cache_resource
def _get_api_client_cached(base_url: str, _v: int = CLIENT_API_VERSION):
    # IMPORTANTE: incluir base_url como parámetro para que Streamlit cachee por URL
    # (si no, puede quedarse apuntando al puerto viejo aunque cambies PHOENIX_API_BASE_URL).
    if not base_url:
        raise RuntimeError(
            "Falta PHOENIX_API_BASE_URL. Copia .env.example a .env y define PHOENIX_API_BASE_URL "
            "(ej: http://localhost:8000)."
        )
    return PhoenixLegalClient(base_url=base_url)


def get_api_client() -> PhoenixLegalClient:
    """
    Wrapper sin args para evitar errores en call-sites.
    Mantiene cache por base_url (leído de env) vía _get_api_client_cached().
    """
    base_url = (os.getenv("PHOENIX_API_BASE_URL") or "").strip()
    return _get_api_client_cached(base_url=base_url, _v=CLIENT_API_VERSION)


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
        "balance": analysis.balance.dict() if analysis.balance else None,
        "profit_loss": analysis.profit_loss.dict() if analysis.profit_loss else None,
        "credit_classification": [c.dict() for c in analysis.credit_classification],
        "total_debt": analysis.total_debt,
        "ratios": [r.dict() for r in analysis.ratios],
        "insolvency": analysis.insolvency.dict() if analysis.insolvency else None,
        "timeline": [t.dict() for t in analysis.timeline],
    }


base_url = os.getenv("PHOENIX_API_BASE_URL") or ""
client = get_api_client()
# Fallback defensivo: si Streamlit reutiliza un cache antiguo del cliente,
# aseguramos que los métodos nuevos existan.
if not hasattr(client, "exclude_document") or not hasattr(client, "generate_economic_report"):
    client = PhoenixLegalClient(base_url=base_url or "http://localhost:8000")


def _download_doc_url(case_id: str, document_id: str, *, disposition: str) -> str:
    """
    Compatibilidad: si Streamlit conserva un cliente cacheado antiguo sin parámetro `disposition`,
    construimos la URL manualmente.
    """
    disp = (disposition or "attachment").strip().lower()
    if disp not in ("attachment", "inline"):
        disp = "attachment"
    try:
        sig = inspect.signature(client.download_document_url)
        if "disposition" in sig.parameters:
            return client.download_document_url(case_id, document_id, disposition=disp)  # type: ignore[arg-type]
    except Exception:
        pass
    base = getattr(client, "base_url", None) or (os.getenv("PHOENIX_API_BASE_URL") or "http://localhost:8000")
    return f"{str(base).rstrip('/')}/api/cases/{case_id}/documents/{document_id}/download?disposition={disp}"

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
cases = []
try:
    cases = client.list_cases()
    if cases:
        case_options = {
            f"{case['name']} ({case['case_id'][:8]}...)": case["case_id"] for case in cases
        }
        selected_label = st.sidebar.selectbox(
            "Selecciona un caso:", options=list(case_options.keys()), key="case_selector"
        )
        st.session_state["selected_case_id"] = case_options[selected_label]
    else:
        st.sidebar.info("No hay casos creados")
        st.session_state["selected_case_id"] = None
except Exception as e:
    st.sidebar.error(f"Error al cargar casos: {e}")
    st.session_state["selected_case_id"] = None
    cases = []

# =========================================
# PANTALLA PRINCIPAL
# =========================================

# Tabs principales
# Orden deseado: Datos justo detrás de Documentos
# NOTA: Mantenemos el binding de variables (tab3=Análisis, tab8=Datos) para no romper el resto del archivo.
tab1, tab2, tab8, tab3, tab4, tab5, tab9, tab10, tab6, tab7 = st.tabs(
    [
        "🆕 Gestión de Casos",
        "📤 Documentos",
        "📚 Datos",
        "📊 Análisis Financiero",
        "⚠️ Alertas",
        "📄 Informe Económico",
        "🏛️ Juzgado",
        "🧑‍⚖️ Administrador Concursal",
        "🔍 Duplicados",
        "🚨 Riesgos Culpabilidad",
    ]
)

# region agent log (debug-mode)
try:
    import time as _t
    _dbg_path = "/Users/irumabragado/Documents/procesos/202512_phoenix-legal/.cursor/debug.log"
    _labels = [
        "🆕 Gestión de Casos",
        "📤 Documentos",
        "📚 Datos",
        "📊 Análisis Financiero",
        "⚠️ Alertas",
        "📄 Informe Económico",
        "🏛️ Juzgado",
        "🧑‍⚖️ Administrador Concursal",
        "🔍 Duplicados",
        "🚨 Riesgos Culpabilidad",
    ]
    _mapping = {
        "tab1": _labels[0],
        "tab2": _labels[1],
        "tab3": _labels[3],
        "tab4": _labels[4],
        "tab5": _labels[5],
        "tab6": _labels[8],
        "tab7": _labels[9],
        "tab8": _labels[2],
        "tab9": _labels[6],
        "tab10": _labels[7],
    }
    with open(_dbg_path, "a", encoding="utf-8") as _f:
        _f.write(
            __import__("json").dumps(
                {
                    "sessionId": "debug-session",
                    "runId": "tab-order-post-reorder-v2",
                    "hypothesisId": "H_TABS_ORDER",
                    "location": "app/ui/streamlit_mvp.py:st.tabs(main)",
                    "message": "tabs_initialized",
                    "data": {"labels": _labels, "binding": _mapping},
                    "timestamp": int(_t.time() * 1000),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
except Exception:
    pass
# endregion agent log (debug-mode)

# =========================================
# DEFINICIÓN GLOBAL DE case_id
# =========================================
# Garantiza que case_id está definido en todos los tabs
case_id = st.session_state.get("selected_case_id")

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
                    st.session_state["selected_case_id"] = result["case_id"]
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
            st.info(
                f"📁 Caso: **{case_info['name']}** | 📊 Estado: **{case_info['analysis_status']}**"
            )
        except Exception as e:
            st.error(f"Error al cargar caso: {e}")

        st.markdown("---")

        # Subir documentos
        st.subheader("📤 Subir Documentos")
        uploaded_files = st.file_uploader(
            "Selecciona archivos (PDF, Excel, Word, TXT, CSV, Email, Imágenes)",
            type=[
                "pdf",
                "xlsx",
                "xls",
                "docx",
                "doc",
                "txt",
                "csv",
                "eml",
                "msg",
                "jpg",
                "jpeg",
                "png",
                "tiff",
                "tif",
            ],
            accept_multiple_files=True,
            key="file_uploader",
        )

        # Estado de confirmación para duplicados (persistente entre reruns)
        if "pending_upload_files" not in st.session_state:
            st.session_state["pending_upload_files"] = None
        if "pending_duplicates" not in st.session_state:
            st.session_state["pending_duplicates"] = None
        if "awaiting_upload_confirm" not in st.session_state:
            st.session_state["awaiting_upload_confirm"] = False

        def _reset_pending_upload():
            st.session_state["pending_upload_files"] = None
            st.session_state["pending_duplicates"] = None
            st.session_state["awaiting_upload_confirm"] = False

        # Paso 1: preparar bytes + check duplicados al pulsar "Subir Archivos"
        if uploaded_files and st.button("📤 Subir Archivos", type="primary"):
            try:
                files_data: list[tuple[str, bytes]] = []
                for f in uploaded_files:
                    f.seek(0)
                    content = f.read()
                    files_data.append((f.name, content))

                st.session_state["pending_upload_files"] = files_data

                with st.spinner("Verificando duplicados..."):
                    duplicates = client.check_duplicates_before_upload(case_id, files_data)

                duplicates_only = [d for d in (duplicates or []) if d.get("is_duplicate") is True]
                if duplicates_only:
                    st.session_state["pending_duplicates"] = duplicates_only
                    st.session_state["awaiting_upload_confirm"] = True
                else:
                    st.session_state["pending_duplicates"] = []
                    st.session_state["awaiting_upload_confirm"] = False

                st.rerun()
            except Exception as e:
                _reset_pending_upload()
                st.error(f"Error al subir documentos: {e}")

        # Paso 2: si hay duplicados, pedir confirmación (en un rerun separado)
        if st.session_state.get("awaiting_upload_confirm") and st.session_state.get(
            "pending_upload_files"
        ):
            duplicates_only = st.session_state.get("pending_duplicates") or []
            st.warning(
                f"⚠️ Se detectaron {len(duplicates_only)} archivo(s) duplicado(s) (binario exacto)"
            )
            for dup in duplicates_only:
                dup_of = dup.get("duplicate_of_filename") or dup.get("duplicate_of") or "N/A"
                dup_of_id = dup.get("duplicate_of_document_id")
                dup_type = dup.get("duplicate_type") or "unknown"
                suffix = f" ({str(dup_of_id)[:8]}...)" if dup_of_id else ""
                st.write(f"- **{dup['filename']}**: {dup_type} (duplica a: {dup_of}{suffix})")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Subir de todos modos", type="primary"):
                    try:
                        files_data = st.session_state["pending_upload_files"]
                        with st.spinner(f"Subiendo {len(files_data)} archivo(s)..."):
                            result = client.upload_documents(
                                case_id,
                                files_data,
                                force_upload=True,
                            )
                        _reset_pending_upload()
                        st.session_state["upload_confirmed"] = False
                        st.success(f"✅ {len(result) if isinstance(result, list) else 0} documento(s) subido(s)")
                        st.rerun()
                    except Exception as e:
                        _reset_pending_upload()
                        st.error(f"Error al subir documentos: {e}")
            with col2:
                if st.button("❌ Cancelar"):
                    _reset_pending_upload()
                    st.info("Subida cancelada")
                    st.stop()

        # Paso 3: si NO hay duplicados pendientes, subir directamente usando los mismos bytes chequeados
        if (
            not st.session_state.get("awaiting_upload_confirm")
            and st.session_state.get("pending_upload_files")
            and st.session_state.get("pending_duplicates") == []
        ):
            try:
                files_data = st.session_state["pending_upload_files"]
                with st.spinner(f"Subiendo {len(files_data)} archivo(s)..."):
                    result = client.upload_documents(case_id, files_data, force_upload=False)

                _reset_pending_upload()

                # El backend devuelve lista[DocumentSummary].
                if isinstance(result, list):
                    st.success(f"✅ {len(result)} documento(s) subido(s)")
                    failed = [
                        d
                        for d in result
                        if (d.get("status") in ("failed", "rejected")) or d.get("error_message")
                    ]
                    if failed:
                        st.warning(f"⚠️ {len(failed)} documento(s) con error/rechazado")
                        for d in failed:
                            st.error(f"- {d.get('filename')}: {d.get('error_message') or 'error'}")
                else:
                    st.success("✅ Subida completada")

                st.rerun()
            except Exception as e:
                _reset_pending_upload()
                st.error(f"Error al subir documentos: {e}")

        st.markdown("---")

        # Listar documentos existentes
        st.subheader("📚 Documentos del Caso")
        try:
            documents = client.list_documents(case_id)
            if documents:
                for doc in documents:
                    status_color = {"ingested": "🟢", "pending": "🟡", "failed": "🔴"}.get(
                        doc["status"], "⚪"
                    )

                    with st.expander(
                        f"{status_color} {doc['filename']} ({doc['document_id'][:8]}...)"
                    ):
                        st.write(f"**ID:** `{doc['document_id']}`")
                        st.write(f"**Estado:** {doc['status']}")
                        st.write(f"**Chunks:** {doc['chunks_count']}")
                        st.write(f"**Subido:** {doc['created_at']}")
                        if st.button("🗑️ Eliminar (soft delete)", key=f"del_{doc['document_id']}"):
                            client.exclude_document(
                                case_id=case_id,
                                document_id=doc["document_id"],
                                reason="Excluido manualmente desde UI (soft-delete).",
                                excluded_by="streamlit_ui",
                            )
                            st.rerun()
                        if doc["status"] == "failed":
                            st.error(f"Error: {doc['error_message']}")
            else:
                st.info("No hay documentos en este caso todavía")
        except Exception as e:
            st.error(f"Error al listar documentos: {e}")

        # ==========================================
        # GESTIÓN DE DUPLICADOS (REDIRIGIR A TAB DEDICADO)
        # ==========================================
        st.divider()
        st.subheader("🔍 Documentos Duplicados")

        try:
            # Mostrar solo resumen, gestión completa en Tab Duplicados
            all_duplicates = client.get_duplicate_pairs(case_id)

            # RESUMEN SIMPLE + REDIRECCIÓN AL TAB DEDICADO
            pendientes = len(
                [d for d in all_duplicates if not d.get("action") or d["action"] == "pending"]
            )
            resueltos = len(all_duplicates) - pendientes

            col_sum1, col_sum2, col_sum3 = st.columns(3)

            with col_sum1:
                st.metric("Total Pares", len(all_duplicates))
            with col_sum2:
                st.metric(
                    "Pendientes", pendientes, delta="Requieren atención" if pendientes > 0 else None
                )
            with col_sum3:
                st.metric("Resueltos", resueltos)

            if pendientes > 0:
                st.warning(f"⚠️ Hay {pendientes} par(es) de duplicados pendientes de revisión")
            else:
                st.success("✅ Todos los duplicados han sido revisados")

            st.info(
                "💡 **Para gestionar duplicados de forma completa**, ve a la pestaña "
                "**🔍 Gestión de Duplicados** donde encontrarás:\n"
                "- Vista comparativa lado a lado\n"
                "- Acciones en lote con simulación\n"
                "- Auditoría completa de decisiones\n"
                "- Control de versiones y rollback"
            )

        except Exception as e:
            st.error(f"Error al obtener duplicados: {e}")

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
                balance_dict = analysis_dict["balance"]
                profit_loss_dict = analysis_dict["profit_loss"]
                credits_dicts = analysis_dict["credit_classification"]
                total_debt = analysis_dict["total_debt"]
                ratios_dicts = analysis_dict["ratios"]
                insolvency_dict = analysis_dict["insolvency"]
                timeline_dicts = analysis_dict["timeline"]

                # Usar componentes para renderizar
                render_balance_block(balance_dict, profit_loss_dict)
                render_credits_block(credits_dicts, total_debt)
                render_ratios_block(ratios_dicts)
                render_insolvency_block(insolvency_dict)

                # ✅ Timeline con paginación backend (escalable)
                render_timeline_block_backend(case_id, client)

                # Patrones sospechosos (si existen analysis alerts)
                try:
                    alerts = client.get_analysis_alerts(case_id)
                    if alerts:
                        st.markdown("")
                        st.markdown("---")
                        render_suspicious_patterns(alerts)
                except Exception as e:
                    # Si falla la obtención de alerts, no bloqueamos el resto
                    st.warning(f"⚠️ No se pudieron cargar patrones sospechosos: {str(e)}")

            except CaseNotFoundError as e:
                st.error("❌ **Caso no encontrado**")
                st.write(str(e))
                st.info("💡 Verifica que el caso existe en la lista de casos del sidebar")

            except ValidationErrorAPI as e:
                st.error("❌ **Error de validación**")
                st.write(str(e))
                st.info(
                    "💡 Los documentos subidos pueden tener formato incorrecto o datos inválidos"
                )

            except ParsingError as e:
                st.error("❌ **Error al procesar documentos**")
                st.write(str(e))
                st.warning("⚠️ El servidor tuvo problemas al extraer datos de los documentos")
                st.info("💡 **Posibles soluciones:**")
                st.write("- Sube documentos con formato más estructurado (Excel, PDF con texto)")
                st.write("- Verifica que los PDFs no sean escaneados sin OCR")
                st.write("- Asegúrate de que los archivos no estén corruptos")

            except ServerError as e:
                st.error("❌ **Error interno del servidor**")
                st.write(str(e))
                st.warning("⚠️ Hubo un problema en el servidor al procesar la solicitud")
                st.info("💡 Intenta de nuevo en unos momentos o contacta al administrador")

            except PhoenixLegalAPIError as e:
                st.error("❌ **Error de API**")
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
                st.error("❌ **Error inesperado**")
                st.write(f"Tipo: `{type(e).__name__}`")
                st.write(f"Mensaje: {e}")
                import traceback

                with st.expander("🔍 Ver traza completa (para debugging)"):
                    st.code(traceback.format_exc())

# =========================================
# TAB 4: ALERTAS TÉCNICAS
# =========================================

with tab4:
    st.header("⚠️ Alertas (despacho)")

    if not st.session_state.get("selected_case_id"):
        st.warning("⚠️ Selecciona o crea un caso primero")
    else:
        case_id = st.session_state["selected_case_id"]

        sub_desk, sub_raw = st.tabs(["🧑‍⚖️ Alertas despacho", "🔎 Alertas técnicas (raw)"])

        with sub_desk:
            # -----------------------------
            # Styles (cards + sticky header)
            # -----------------------------
            st.markdown(
                """
                <style>
                  div.alertsHeader {
                    position: sticky;
                    top: 0;
                    z-index: 999;
                    background: rgba(255,255,255,0.92);
                    backdrop-filter: blur(6px);
                    padding: 0.6rem 0.75rem;
                    border-bottom: 1px solid rgba(0,0,0,0.08);
                    margin-bottom: 0.75rem;
                  }
                  @media (prefers-color-scheme: dark) {
                    div.alertsHeader {
                      background: rgba(14,17,23,0.92);
                      border-bottom: 1px solid rgba(255,255,255,0.10);
                    }
                  }
                  div.alertCard {
                    border: 1px solid rgba(0,0,0,0.08);
                    border-radius: 12px;
                    padding: 0.9rem 1rem;
                    margin: 0 0 0.8rem 0;
                    background: rgba(255,255,255,0.60);
                  }
                  @media (prefers-color-scheme: dark) {
                    div.alertCard {
                      border: 1px solid rgba(255,255,255,0.12);
                      background: rgba(14,17,23,0.35);
                    }
                  }
                  div.badge {
                    display: inline-block;
                    padding: 0.12rem 0.5rem;
                    border-radius: 999px;
                    font-size: 0.75rem;
                    border: 1px solid rgba(0,0,0,0.10);
                    margin-left: 0.35rem;
                    opacity: 0.9;
                  }
                  @media (prefers-color-scheme: dark) {
                    div.badge {
                      border: 1px solid rgba(255,255,255,0.12);
                    }
                  }
                </style>
                """,
                unsafe_allow_html=True,
            )

            def _relevance_rank(r: str) -> int:
                return {"ALTA": 0, "MEDIA": 1, "BAJA": 2}.get(str(r or "MEDIA"), 9)

            def _default_checklist(domain: str) -> list[str]:
                d = str(domain or "DOCS").upper()
                if d == "TGSS":
                    return [
                        "RNT/RLC de los meses afectados (y justificantes de pago si existen).",
                        "Certificado TGSS actualizado (deuda/estado).",
                        "Soporte de aplazamiento/fraccionamiento si existe.",
                        "Conciliación bancaria del periodo.",
                    ]
                if d == "BANCO":
                    return [
                        "Extractos completos del periodo (no solo resúmenes).",
                        "Conciliación bancaria y explicación de conceptos genéricos.",
                        "Contrato/soporte de los pagos (servicios, préstamos, etc.).",
                    ]
                if d == "CONTABILIDAD":
                    return [
                        "Factura + justificante + extracto bancario (conciliación).",
                        "Soporte y asiento del IVA (si aplica).",
                        "Confirmar si hubo rectificativa o pago posterior.",
                    ]
                if d == "VINCULADAS":
                    return [
                        "Contrato y entregables/soporte del servicio prestado.",
                        "Criterio de precios y relación con el grupo.",
                        "Conciliación bancaria de los pagos.",
                    ]
                return [
                    "Confirmar si la documentación existe y, si existe, incorporarla al expediente.",
                    "Aportar soporte adicional si este punto va a informe.",
                ]

            # Scroll restoration (best-effort)
            focus_id = st.session_state.pop("alerts_focus_id", None)
            if focus_id:
                components.html(
                    f"""
                    <script>
                      const el = parent.document.getElementById("alert-{focus_id}");
                      if (el) el.scrollIntoView({{behavior: "instant", block: "start"}});
                    </script>
                    """,
                    height=0,
                )

            # Data fetch
            if "alerts_refresh_token" not in st.session_state:
                st.session_state["alerts_refresh_token"] = 0

            @st.cache_data(ttl=30, show_spinner=False)
            def _list_alerts_cached(case_id: str, refresh_token: int):
                _ = refresh_token
                return client.list_case_alerts_desk(case_id)

            @st.cache_data(ttl=300, show_spinner=False)
            def _get_alert_detail_cached(alert_id: str, refresh_token: int):
                _ = refresh_token
                return client.get_alert_detail_desk(alert_id)

            # Header content
            try:
                case_info = client.get_case(case_id)
            except Exception:
                case_info = None

            alerts = []
            try:
                alerts = _list_alerts_cached(case_id, int(st.session_state["alerts_refresh_token"]))
            except Exception as e:
                st.error(f"No se pudieron cargar las alertas del despacho: {e}")
                alerts = []

            # Aggregates
            counts_rel = {"ALTA": 0, "MEDIA": 0, "BAJA": 0}
            counts_status = {"pendiente": 0, "revisada": 0, "descartada": 0, "para_informe": 0}
            counts_domain = {}
            any_changed = False
            for a in alerts or []:
                rel = str(a.get("relevance") or "MEDIA")
                stt = str(a.get("status") or "pendiente")
                dom = str(a.get("domain") or "DOCS")
                counts_rel[rel] = counts_rel.get(rel, 0) + 1
                counts_status[stt] = counts_status.get(stt, 0) + 1
                counts_domain[dom] = counts_domain.get(dom, 0) + 1
                any_changed = any_changed or bool(a.get("changed_since_last_review"))

            # Sticky header (case + state + export placeholder)
            header_left = f"📁 Caso: <b>{(case_info or {}).get('name','—')}</b> <span style='opacity:0.7'>({case_id})</span>"
            header_right = f"Alertas: <b>{len(alerts or [])}</b>"
            if any_changed:
                header_right += " · <b>cambios desde revisión</b>"
            st.markdown(
                f"<div class='alertsHeader'>{header_left}<div style='float:right'>{header_right}</div><div style='clear:both'></div></div>",
                unsafe_allow_html=True,
            )

            # Summary row + actions
            csum1, csum2, csum3, csum4 = st.columns([1.2, 1.2, 1.2, 1.4])
            with csum1:
                st.metric("🟥 Punto delicado", counts_rel.get("ALTA", 0))
            with csum2:
                st.metric("🟨 A revisar", counts_rel.get("MEDIA", 0))
            with csum3:
                st.metric("🟢 Detalles", counts_rel.get("BAJA", 0))
            with csum4:
                bcol1, bcol2 = st.columns([1.3, 1.1])
                with bcol1:
                    if st.button("🔄 Reanalizar", type="primary", key="alerts_desk_generate"):
                        try:
                            with st.spinner("Regenerando alertas despacho (persistidas)..."):
                                client.generate_case_alerts_desk(case_id)
                            st.session_state["alerts_refresh_token"] = int(
                                st.session_state["alerts_refresh_token"]
                            ) + 1
                            st.success("✅ Alertas regeneradas")
                            st.rerun()
                        except Exception as e:
                            st.error(f"No se pudo regenerar: {e}")
                with bcol2:
                    # Export solo si hay alertas validadas
                    can_export = any(
                        str(a.get("status") or "") in ("revisada", "para_informe") for a in (alerts or [])
                    )
                    if st.button("⬇️ Export", disabled=not can_export, key="alerts_desk_export"):
                        try:
                            with st.spinner("Generando export de alertas validadas..."):
                                exp = client.export_alerts_desk_validated(case_id)
                            dl = str(exp.get("download_url") or "")
                            if dl:
                                st.success("✅ Export generado")
                                st.link_button("Descargar informe (MD/PDF si aplica)", f"{client.base_url}{dl}")
                            else:
                                st.info("Export generado, pero no hay URL de descarga.")
                        except Exception as e:
                            st.error(f"No se pudo exportar: {e}")

            # Controls: mode + search + filters
            mode = st.radio(
                "Modo",
                options=["Modo lectura", "Modo trabajo"],
                horizontal=True,
                index=0,
                key="alerts_mode",
            )
            is_work_mode = mode == "Modo trabajo"

            colf1, colf2, colf3, colf4 = st.columns([1.4, 1.2, 1.2, 1.2])
            with colf1:
                q = st.text_input(
                    "Buscar",
                    value=st.session_state.get("alerts_search", ""),
                    key="alerts_search",
                    placeholder="Buscar por título o resumen…",
                    label_visibility="collapsed",
                )
            with colf2:
                domains = sorted(list(counts_domain.keys()))
                domain_filter = st.multiselect(
                    "Categoría",
                    options=domains,
                    default=st.session_state.get("alerts_domain_filter", domains),
                    key="alerts_domain_filter",
                )
            with colf3:
                rel_filter = st.multiselect(
                    "Severidad",
                    options=["ALTA", "MEDIA", "BAJA"],
                    default=st.session_state.get("alerts_rel_filter", ["ALTA", "MEDIA", "BAJA"]),
                    key="alerts_rel_filter",
                )
            with colf4:
                st_filter = st.multiselect(
                    "Estado",
                    options=["pendiente", "revisada", "para_informe", "descartada"],
                    default=st.session_state.get(
                        "alerts_status_filter", ["pendiente", "revisada", "para_informe", "descartada"]
                    ),
                    key="alerts_status_filter",
                )

            # Apply filters + sort
            qn = (q or "").strip().lower()
            filtered = []
            for a in alerts or []:
                dom = str(a.get("domain") or "DOCS")
                rel = str(a.get("relevance") or "MEDIA")
                stt = str(a.get("status") or "pendiente")
                blob = (str(a.get("title_human") or "") + " " + str(a.get("summary_human") or "")).lower()
                if domain_filter and dom not in domain_filter:
                    continue
                if rel_filter and rel not in rel_filter:
                    continue
                if st_filter and stt not in st_filter:
                    continue
                if qn and qn not in blob:
                    continue
                filtered.append(a)

            filtered.sort(
                key=lambda x: (_relevance_rank(x.get("relevance")), str(x.get("updated_at") or "")),
                reverse=False,
            )

            # Tags summary (categories)
            if counts_domain:
                tags_line = " · ".join([f"`{k}` ({v})" for k, v in sorted(counts_domain.items())])
                st.caption(f"Tags: {tags_line}")

            if not filtered:
                if not alerts:
                    st.info("No hay alertas despacho generadas todavía. Pulsa **Reanalizar**.")
                else:
                    st.info("No hay alertas que coincidan con los filtros actuales.")
            else:
                for a in filtered:
                    alert_id = str(a.get("alert_id"))
                    title = str(a.get("title_human") or "—")
                    domain = str(a.get("domain") or "DOCS")
                    rel = str(a.get("relevance") or "MEDIA")
                    status_txt = str(a.get("status") or "pendiente")
                    summary = str(a.get("summary_human") or "")
                    changed = bool(a.get("changed_since_last_review"))

                    badge = {"ALTA": "🟥", "MEDIA": "🟨", "BAJA": "🟢"}.get(rel, "🟨")
                    changed_txt = " · cambió desde revisión" if changed else ""

                    # Anchor for scroll restore
                    st.markdown(f"<div id='alert-{alert_id}'></div>", unsafe_allow_html=True)

                    st.markdown("<div class='alertCard'>", unsafe_allow_html=True)
                    st.markdown(
                        f"**{badge} {title}**  \n{domain} · {rel} · {status_txt}{changed_txt}",
                    )
                    st.write(summary)

                    # Quick actions
                    ac1, ac2, ac3, ac4 = st.columns([1.1, 1.3, 1.3, 2.3])
                    with ac1:
                        if st.button("✔️ Revisado", key=f"desk_review_{alert_id}"):
                            try:
                                client.update_alert_desk(
                                    alert_id,
                                    {"status": "revisada", "updated_by": "abogado"},
                                )
                                st.session_state["alerts_refresh_token"] = int(
                                    st.session_state["alerts_refresh_token"]
                                ) + 1
                                st.session_state["alerts_focus_id"] = alert_id
                                st.rerun()
                            except Exception as e:
                                st.error(f"No se pudo actualizar: {e}")
                    with ac2:
                        if st.button("⚠️ Para informe", key=f"desk_report_{alert_id}"):
                            try:
                                client.update_alert_desk(
                                    alert_id,
                                    {"para_informe": True, "updated_by": "abogado"},
                                )
                                st.session_state["alerts_refresh_token"] = int(
                                    st.session_state["alerts_refresh_token"]
                                ) + 1
                                st.session_state["alerts_focus_id"] = alert_id
                                st.rerun()
                            except Exception as e:
                                st.error(f"No se pudo actualizar: {e}")
                    with ac3:
                        if st.button("🚫 No relevante", key=f"desk_drop_{alert_id}"):
                            try:
                                client.update_alert_desk(
                                    alert_id,
                                    {"status": "descartada", "updated_by": "abogado"},
                                )
                                st.session_state["alerts_refresh_token"] = int(
                                    st.session_state["alerts_refresh_token"]
                                ) + 1
                                st.session_state["alerts_focus_id"] = alert_id
                                st.rerun()
                            except Exception as e:
                                st.error(f"No se pudo actualizar: {e}")
                    with ac4:
                        if is_work_mode:
                            note_key = f"desk_note_inline_{alert_id}"
                            if note_key not in st.session_state:
                                st.session_state[note_key] = str(a.get("lawyer_note") or "")
                            note_val = st.text_input(
                                "Nota rápida",
                                value=st.session_state.get(note_key, ""),
                                key=note_key,
                                placeholder="Nota breve…",
                                label_visibility="collapsed",
                            )
                            if st.button("💾 Guardar nota", key=f"desk_note_save_{alert_id}"):
                                try:
                                    client.update_alert_desk(
                                        alert_id,
                                        {"lawyer_note": note_val, "updated_by": "abogado"},
                                    )
                                    st.session_state["alerts_refresh_token"] = int(
                                        st.session_state["alerts_refresh_token"]
                                    ) + 1
                                    st.session_state["alerts_focus_id"] = alert_id
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"No se pudo guardar: {e}")
                        else:
                            st.caption("")

                    # Detail (lazy)
                    open_key = f"desk_open_{alert_id}"
                    show_detail = st.checkbox("Ver detalles ▾", value=False, key=open_key)
                    if show_detail:
                        try:
                            detail = _get_alert_detail_cached(
                                alert_id, int(st.session_state["alerts_refresh_token"])
                            )
                        except Exception as e:
                            detail = None
                            st.error(f"No se pudo cargar el detalle: {e}")

                        if detail:
                            if is_work_mode:
                                st.markdown("**📄 Evidencias**")
                                evidences = list(detail.get("evidences") or [])
                                if not evidences:
                                    st.info("No hay evidencias normalizadas para esta alerta.")
                                else:
                                    for idx, ev in enumerate(evidences, 1):
                                        fn = str(ev.get("filename") or "—")
                                        doc_id = ev.get("document_id")
                                        p1 = ev.get("page_start")
                                        p2 = ev.get("page_end")
                                        pages = ""
                                        if p1 is not None:
                                            pages = f"pág. {p1}" if (p2 is None or p2 == p1) else f"pág. {p1}-{p2}"
                                        st.markdown(f"- **{fn}** {pages}")
                                        snip = str(ev.get("snippet") or "").strip()
                                        if snip:
                                            st.caption(snip)
                                        sig = str(ev.get("signal") or "").strip()
                                        if sig:
                                            st.caption(sig)
                                        # Best-effort “clickable”: link to local file if available
                                        if doc_id:
                                            if st.button(
                                                "Abrir documento (best-effort)",
                                                key=f"desk_open_doc_{alert_id}_{idx}",
                                            ):
                                                try:
                                                    integ = client.get_document_integrity(case_id, str(doc_id))
                                                    if integ.get("file_exists") and integ.get("storage_path"):
                                                        st.link_button(
                                                            "Abrir archivo local",
                                                            f"file://{integ['storage_path']}",
                                                        )
                                                    else:
                                                        st.info("Archivo no disponible en disco (según integridad).")
                                                except Exception as e:
                                                    st.error(f"No se pudo resolver ruta del archivo: {e}")

                                st.markdown("")
                                st.markdown("**📌 Cosas que conviene aclarar**")
                                tc = list(detail.get("to_clarify") or [])
                                if tc:
                                    for it in tc[:10]:
                                        txt = str(it.get("item_text") or "").strip()
                                        why = str(it.get("why_needed") or "").strip()
                                        if why:
                                            st.write(f"- {txt} — {why}")
                                        else:
                                            st.write(f"- {txt}")
                                else:
                                    for it in _default_checklist(domain)[:10]:
                                        st.write(f"- {it}")

                                st.markdown("")
                                st.markdown("**🎯 Acciones sugeridas (priorizadas)**")
                                ra = list(detail.get("recommended_actions") or [])
                                if ra:
                                    for it in ra[:8]:
                                        pr = it.get("priority")
                                        txt = str(it.get("action_text") or "").strip()
                                        why = str(it.get("why") or "").strip()
                                        prefix = f"{pr}. " if pr else "- "
                                        st.write(prefix + txt)
                                        if why:
                                            st.caption(why)
                                else:
                                    for i, it in enumerate(_default_checklist(domain)[:5], 1):
                                        st.write(f"{i}. {it}")

                                st.markdown("")
                                st.markdown("**🧭 Nota legal (disclaimer)**")
                                st.caption(str(detail.get("disclaimer_detail") or ""))

                                st.markdown("")
                                st.markdown("**📝 Nota del abogado**")
                                note_area_key = f"desk_note_area_{alert_id}"
                                note_val2 = st.text_area(
                                    "Nota",
                                    value=str(detail.get("lawyer_note") or ""),
                                    key=note_area_key,
                                    label_visibility="collapsed",
                                    placeholder="Añade una nota breve (por qué importa, a quién pedirlo, etc.)",
                                )
                                if st.button("💾 Guardar nota", key=f"desk_note_area_save_{alert_id}"):
                                    try:
                                        client.update_alert_desk(
                                            alert_id,
                                            {"lawyer_note": note_val2, "updated_by": "abogado"},
                                        )
                                        st.session_state["alerts_refresh_token"] = int(
                                            st.session_state["alerts_refresh_token"]
                                        ) + 1
                                        st.session_state["alerts_focus_id"] = alert_id
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"No se pudo guardar nota: {e}")
                            else:
                                # Modo lectura: solo texto + disclaimer (consumo rápido)
                                st.markdown("**🧭 Nota legal (disclaimer)**")
                                st.caption(str(detail.get("disclaimer_detail") or ""))

                    st.markdown("</div>", unsafe_allow_html=True)

        with sub_raw:
            st.subheader("⚠️ Alertas técnicas (raw)")

            if st.button("🔍 Verificar Alertas", type="primary", key="alerts_raw_verify"):
                try:
                    with st.spinner("Analizando calidad de datos..."):
                        alerts = client.get_analysis_alerts(case_id)

                    # Agrupar por tipo (contrato real del backend: alert_type/description/evidence)
                    by_type = {}
                    for a in (alerts or []):
                        t = a.get("alert_type", "UNKNOWN")
                        by_type.setdefault(t, []).append(a)

                    def _section(title: str, types: list[str]):
                        items = []
                        for t in types:
                            items.extend(by_type.get(t, []))
                        st.subheader(title)
                        if not items:
                            st.success("✅ No hay")
                            return
                        st.warning(f"⚠️ {len(items)} alerta(s)")
                        for alert in items:
                            atype = alert.get("alert_type", "UNKNOWN")
                            emoji = {
                                "INCONSISTENT_DATA": "🔴",
                                "TEMPORAL_INCONSISTENCY": "🔴",
                                "SUSPICIOUS_PATTERN": "🕵️",
                                "MISSING_DATA": "🟡",
                                "DUPLICATED_DATA": "🟡",
                            }.get(atype, "⚪")
                            title_line = f"{emoji} {atype}"
                            with st.expander(title_line):
                                st.write(f"**Descripción:** {alert.get('description', '')}")
                                evidence = alert.get("evidence") or []
                                st.write(f"**Documentos implicados:** {len(evidence)}")
                                for ev in evidence[:5]:
                                    loc = ev.get("location") or {}
                                    pages = ""
                                    if loc.get("page_start") is not None:
                                        pages = f" pág. {loc.get('page_start')}-{loc.get('page_end')}"
                                    st.write(
                                        f"- **{ev.get('filename','?')}**{pages} "
                                        f"(doc_id: {str(ev.get('document_id',''))[:8]}..., "
                                        f"chunk_id: {str(ev.get('chunk_id',''))[:12]}...)"
                                    )
                                    content = (ev.get("content") or "").strip()
                                    if content:
                                        st.caption(content[:200])

                    st.info(f"Total alertas: {len(alerts or [])}")
                    _section(
                        "🕵️ Patrones sospechosos (posible fraude)",
                        ["SUSPICIOUS_PATTERN"],
                    )
                    _section(
                        "⏱️ Inconsistencias temporales",
                        ["TEMPORAL_INCONSISTENCY"],
                    )
                    _section(
                        "📄 Datos faltantes",
                        ["MISSING_DATA"],
                    )
                    _section(
                        "🧬 Datos duplicados",
                        ["DUPLICATED_DATA"],
                    )
                    _section(
                        "⚠️ Datos inconsistentes",
                        ["INCONSISTENT_DATA"],
                    )
                except Exception as e:
                    st.error(f"Error al verificar alertas: {e}")

# =========================================
# TAB 5: INFORME LEGAL
# =========================================

with tab5:
    st.header("📄 Informe de Situación Económica (Cliente)")

    if not st.session_state.get("selected_case_id"):
        st.warning("⚠️ Selecciona o crea un caso primero")
    else:
        case_id = st.session_state["selected_case_id"]

        # -------------------------
        # Estado (cabecera fija)
        # -------------------------
        status_data: dict = {}
        try:
            status_data = client.get_economic_report_status(case_id)
        except Exception as e:
            st.error(f"Error al cargar estado del informe: {e}")
            status_data = {"has_generated": False, "validation": {"status": "UNKNOWN"}, "mode": "BORRADOR"}

        case_name = status_data.get("case_name") or "—"
        has_generated = bool(status_data.get("has_generated"))
        generated_at = status_data.get("generated_at") or "—"
        validation = status_data.get("validation") or {}
        validation_status = validation.get("status") or "UNKNOWN"
        validated_at = validation.get("validated_at") or "—"
        mode = status_data.get("mode") or "BORRADOR"
        dirty = bool(status_data.get("dirty_since_last_validation"))
        lawyer_sig = status_data.get("lawyer_signature") or {}

        export_badge = "PASS ✅" if validation_status == "PASS" else ("BLOQUEADO ⛔" if validation_status == "FAIL" else "PENDIENTE")
        mode_badge = "PUBLICABLE" if mode == "PUBLICABLE" else "BORRADOR"

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown("**Caso**")
            st.caption(f"{case_name} ({case_id[:8]}...)")
        with c2:
            st.markdown("**Estado informe**")
            st.caption(("Generado" if has_generated else "No generado") + f" · {generated_at}")
        with c3:
            st.markdown("**Export cliente**")
            st.caption(f"{export_badge} · {validated_at}")
        with c4:
            st.markdown("**Modo**")
            st.caption(mode_badge + (" · cambios pendientes" if dirty else ""))

        st.markdown("---")

        # -------------------------
        # Barra de acciones rápidas (inline)
        # -------------------------
        can_export = bool(mode == "PUBLICABLE" and validation_status == "PASS" and not dirty)
        supports_disabled = "disabled" in inspect.signature(st.button).parameters

        a1, a2, a3, a4 = st.columns([1.2, 1.3, 1.2, 1.1])
        with a1:
            if st.button("📝 Generar borrador", type="primary", key="econ_generate_v2"):
                try:
                    with st.spinner("Generando informe..."):
                        client.generate_economic_report(case_id)
                    st.success("✅ Informe generado (BORRADOR)")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al generar informe: {e}")
        with a2:
            if st.button("✅ Generar con cambios (versión cliente)", key="econ_validate"):
                try:
                    with st.spinner("Generando versión cliente (con cambios) y preparando PDF..."):
                        res = client.validate_economic_report_client_export(case_id)
                    if res.get("validation_status") == "PASS":
                        st.success("✅ Versión cliente generada — informe PUBLICABLE")
                    else:
                        st.error("⛔ No se pudo generar versión cliente — revisa motivos")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al generar con cambios: {e}")
        with a3:
            # No deshabilitar: si está deshabilitado, el click no dispara y no se puede ejecutar
            # el flujo automático de “Generar con cambios” que es obligatorio para descargar.
            if st.button("⬇️ Descargar PDF cliente", key="econ_pdf_v2"):
                if not can_export:
                    st.warning("⚠️ Genera con cambios antes de descargar. Ejecutando…")
                    try:
                        client.validate_economic_report_client_export(case_id)
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo generar con cambios: {e}")
                else:
                    try:
                        with st.spinner("Preparando descarga..."):
                            pdf_content = client.download_economic_report_pdf(case_id, audience="client")
                        st.download_button(
                            label="📥 Descargar PDF económico (cliente)",
                            data=pdf_content,
                            file_name=f"informe_situacion_economica_{case_id[:8]}.pdf",
                            mime="application/pdf",
                            key="econ_pdf_dl_v2",
                        )
                    except Exception as e:
                        st.error(f"Error al descargar PDF: {e}")
        with a4:
            to_email_quick = st.text_input(
                "Email",
                placeholder="cliente@ejemplo.com",
                key="econ_to_email_quick",
                label_visibility="collapsed",
            )
            # Mismo criterio: permitir click y auto-validar si hace falta.
            if st.button("📨 Enviar email", key="econ_email_send_v2"):
                if not can_export:
                    st.warning("⚠️ Genera con cambios antes de enviar. Ejecutando…")
                    try:
                        client.validate_economic_report_client_export(case_id)
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo generar con cambios: {e}")
                else:
                    try:
                        with st.spinner("Enviando email..."):
                            client.email_economic_report(case_id, to_email=to_email_quick)
                        st.success("✅ Email enviado (PDF validado)")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error enviando email: {e}")

        st.markdown("---")

        # -------------------------
        # Subtabs internas
        # -------------------------
        tprev, tedit, tstruct = st.tabs(["👁️ Vista previa", "✍️ Edición del abogado (Adenda)", "🧩 Correcciones estructuradas"])

        # Panel derecho común
        def _render_right_panel(*, panel_key: str):
            v = status_data.get("validation") or {}
            v_status = v.get("status") or "UNKNOWN"
            if v_status == "PASS" and mode == "PUBLICABLE" and not dirty:
                st.success("✅ Exportación cliente: PASS (PUBLICABLE)")
            elif v_status == "FAIL":
                st.error("⛔ Exportación cliente: BLOQUEADA (BORRADOR)")
            else:
                st.warning("⚠️ Exportación cliente: sin validar / pendiente")

            reasons = v.get("reasons") or []
            with st.expander("Ver motivos (Rxx)"):
                if not reasons:
                    st.write("—")
                else:
                    for r in reasons[:20]:
                        st.write(f"- **{r.get('rule_id','R?')}** ({r.get('section','?')}): {r.get('message','')}")

            with st.expander("Firma del abogado (obligatoria para PDF cliente)", expanded=True):
                # Streamlit constraint: form keys must be unique across the whole page render.
                # This right panel is rendered in multiple subtabs, so suffix by panel_key.
                with st.form(f"econ_signature_form_{panel_key}"):
                    sig_name = st.text_input("Nombre y apellidos", value=str(lawyer_sig.get("lawyer_name") or ""))
                    sig_col = st.text_input("Nº colegiado", value=str(lawyer_sig.get("collegiate_number") or ""))
                    sig_bar = st.text_input("Colegio", value=str(lawyer_sig.get("bar_association") or ""))
                    sig_firm = st.text_input("Despacho *", value=str(lawyer_sig.get("law_firm") or ""))
                    sig_city = st.text_input("Ciudad", value=str(lawyer_sig.get("office_city") or ""))
                    sig_date = st.text_input(
                        "Fecha (YYYY-MM-DD) *",
                        value=str(lawyer_sig.get("signature_date") or ""),
                    )
                    sig_submit = st.form_submit_button("💾 Guardar firma")
                    if sig_submit:
                        try:
                            client.save_economic_report_signature(
                                case_id,
                                {
                                    "lawyer_name": sig_name,
                                    "collegiate_number": sig_col,
                                    "bar_association": sig_bar or None,
                                    "law_firm": sig_firm,
                                    "office_city": sig_city or None,
                                    "signature_date": sig_date,
                                    "edited_by": "abogado",
                                },
                            )
                            st.success("✅ Firma guardada. Ahora ejecuta “Generar con cambios”.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error guardando firma: {e}")

            with st.expander("Historial de cambios"):
                hist = status_data.get("history") or []
                if not hist:
                    st.write("—")
                else:
                    for h in reversed(hist[-30:]):
                        st.write(f"- {h.get('at','')} — **{h.get('action','')}**: {h.get('detail','')}")

        with tprev:
            col_main, col_side = st.columns([3.3, 1.2])
            with col_main:
                st.subheader("Vista previa por secciones (híbrida)")
                if not has_generated:
                    st.info("No hay informe generado todavía. Usa “Generar borrador”.")
                else:
                    # Si está PUBLICABLE, mostrar el PDF cliente validado (vista exacta)
                    if can_export:
                        try:
                            pdf_client = client.download_economic_report_pdf(case_id, audience="client")
                            st.download_button(
                                "📥 Descargar PDF cliente validado",
                                data=pdf_client,
                                file_name=f"informe_cliente_validado_{case_id[:8]}.pdf",
                                mime="application/pdf",
                                key="econ_pdf_client_validated_dl",
                            )
                        except Exception:
                            pass
                    else:
                        st.info("El PDF cliente solo se habilita tras validación PASS (modo PUBLICABLE).")
                    try:
                        preview = client.get_economic_report_sections(case_id)
                        for sec in preview.get("sections") or []:
                            title = sec.get("title") or sec.get("id")
                            content = sec.get("content_md") or "—"
                            with st.expander(title, expanded=(sec.get("id") in ("1", "5", "8"))):
                                st.markdown(content)
                    except Exception as e:
                        st.error(f"No se pudo cargar la vista previa: {e}")
            with col_side:
                _render_right_panel(panel_key="prev")

        with tedit:
            col_main, col_side = st.columns([3.3, 1.2])
            with col_main:
                st.subheader("Adenda del abogado (V1)")
                add = status_data.get("addendum") or {}
                default_text = add.get("text") or ""
                default_include = bool(add.get("include_in_pdf", True))
                default_place = add.get("placement") or "before_signature"

                include_in_pdf = st.checkbox("Incluir en PDF cliente", value=default_include, key="econ_add_include")
                placement = st.selectbox(
                    "Ubicación",
                    options=["before_signature", "after_block_8"],
                    format_func=lambda x: "Antes de firma (default)" if x == "before_signature" else "Tras bloque 8",
                    index=0 if default_place == "before_signature" else 1,
                    key="econ_add_place",
                )
                edited_by = st.text_input("Editado por", value="abogado", key="econ_add_by")
                add_text = st.text_area(
                    "Texto de la adenda",
                    value=default_text,
                    height=220,
                    key="econ_add_text",
                    placeholder="Añade matices jurídicos, advertencias o próximos pasos del despacho (sin inventar hechos).",
                )
                if st.button("💾 Guardar borrador", key="econ_add_save", type="primary"):
                    try:
                        client.save_economic_report_addendum(
                            case_id,
                            text=add_text,
                            include_in_pdf=include_in_pdf,
                            placement=placement,
                            edited_by=edited_by,
                        )
                        st.success("✅ Adenda guardada (BORRADOR)")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error guardando adenda: {e}")

                st.caption("Después de guardar, ejecuta “Generar con cambios (versión cliente)” para pasar a PUBLICABLE.")
            with col_side:
                _render_right_panel(panel_key="edit")

        with tstruct:
            col_main, col_side = st.columns([3.3, 1.2])
            with col_main:
                st.subheader("Correcciones estructuradas")
                if not has_generated:
                    st.info("Genera primero el informe para poder editar (deudas/hitos).")
                else:
                    try:
                        editables = client.get_economic_report_editables(case_id)
                        expected_version = int(editables.get("overrides_version") or 0)
                        debts = list(editables.get("debts") or [])
                        timeline = list(editables.get("timeline") or [])

                        st.caption(
                            "Regla: cualquier corrección exige **Evidencia/justificación** (mín. 10 caracteres). "
                            "Solo se aplican filas donde rellenes la columna “evidence”."
                        )

                        with st.expander("Deudas (editar campos clave)", expanded=True):
                            edited_debts = st.data_editor(
                                debts,
                                key="econ_debts_editor",
                                use_container_width=True,
                                num_rows="dynamic",
                                disabled=[
                                    "debt_id",
                                ],
                            )

                        with st.expander("Timeline / hitos (editar o excluir)", expanded=False):
                            edited_tl = st.data_editor(
                                timeline,
                                key="econ_timeline_editor",
                                use_container_width=True,
                                num_rows="dynamic",
                                disabled=[
                                    "event_key",
                                    "event_type",
                                ],
                            )

                        edited_by = st.text_input("Editado por", value="abogado", key="econ_overrides_by")

                        if st.button("✅ Aplicar cambios al borrador", key="econ_overrides_apply", type="primary"):
                            # Filtrar: solo filas con evidencia no vacía
                            debt_overrides = [r for r in (edited_debts or []) if str((r or {}).get("evidence") or "").strip()]
                            timeline_overrides = [r for r in (edited_tl or []) if str((r or {}).get("evidence") or "").strip()]
                            try:
                                client.apply_economic_report_overrides(
                                    case_id,
                                    expected_version=expected_version,
                                    edited_by=edited_by,
                                    debt_overrides=debt_overrides,
                                    timeline_overrides=timeline_overrides,
                                )
                                st.success("✅ Correcciones aplicadas (BORRADOR). Regenera/valida antes de exportar.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error aplicando correcciones: {e}")
                    except Exception as e:
                        st.error(f"No se pudieron cargar datos editables: {e}")
            with col_side:
                _render_right_panel(panel_key="struct")

# =========================================
# TAB 6: GESTIÓN DE DUPLICADOS (BLINDADA)
# =========================================

with tab6:
    st.header("🔍 Gestión de Duplicados")

    if not case_id:
        st.info("📌 Selecciona un caso para ver duplicados")
    else:
        try:
            pairs = client.get_duplicate_pairs(case_id)

            if not pairs:
                st.success("✅ No hay duplicados detectados en este caso")
            else:
                st.write(f"**Total de pares detectados:** {len(pairs)}")

                # Filtros
                filter_status = st.selectbox(
                    "Filtrar por estado", ["Todos", "Pendientes", "Resueltos"]
                )

                # Filtrar pares
                filtered_pairs = pairs
                if filter_status == "Pendientes":
                    filtered_pairs = [p for p in pairs if not p.get("action")]
                elif filter_status == "Resueltos":
                    filtered_pairs = [p for p in pairs if p.get("action")]

                st.write(f"**Mostrando:** {len(filtered_pairs)} par(es)")

                # BATCH ACTIONS
                st.markdown("---")
                st.subheader("⚡ Acciones en lote (CON SIMULACIÓN)")

                with st.expander("🚨 BATCH ACTIONS (usar con precaución)"):
                    st.warning(
                        "⚠️ Las acciones en lote requieren confirmación previa con simulación"
                    )

                    col_batch1, col_batch2 = st.columns([2, 1])

                    with col_batch1:
                        batch_action = st.selectbox(
                            "Acción común",
                            ["keep_both", "mark_duplicate", "exclude_from_analysis"],
                            key="batch_action_select",
                        )

                        batch_reason = st.text_area(
                            "Razón común (obligatoria)", key="batch_reason_input", height=80
                        )

                    with col_batch2:
                        # Selección de pares
                        selected_pairs = []
                        for idx, pair in enumerate(filtered_pairs):
                            if st.checkbox(f"Par {idx+1}", key=f"batch_select_{pair['pair_id']}"):
                                selected_pairs.append(pair["pair_id"])

                        st.write(f"✅ Seleccionados: {len(selected_pairs)}")

                    if st.button("🔍 SIMULAR (paso 1)", type="secondary"):
                        if not selected_pairs:
                            st.error("❌ No hay pares seleccionados")
                        elif not batch_reason or len(batch_reason) < 10:
                            st.error("❌ Razón muy corta (mínimo 10 chars)")
                        else:
                            try:
                                simulation = client.simulate_batch_duplicate_action(
                                    case_id=case_id,
                                    action=batch_action,
                                    reason=batch_reason,
                                    pair_ids=selected_pairs,
                                    user="streamlit_user",  # TODO: usuario real
                                )

                                st.json(simulation)

                                if simulation.get("safe_to_proceed"):
                                    st.success("✅ Simulación OK. Puedes aplicar.")

                                    if st.button("✅ APLICAR (paso 2)", type="primary"):
                                        st.info("🚧 Implementar apply batch real")
                                else:
                                    st.error("⚠️ Simulación con warnings. Revisa antes de aplicar.")
                                    for warning in simulation.get("warnings", []):
                                        st.warning(warning)

                            except Exception as e:
                                st.error(f"Error en simulación: {e}")

                # PARES INDIVIDUALES
                st.markdown("---")
                st.subheader("📋 Pares individuales")

                for idx, pair in enumerate(filtered_pairs):
                    with st.expander(
                        f"Par {idx+1}: {pair['original_filename']} ⇄ {pair['duplicate_filename']} "
                        f"(Similitud: {pair['similarity']:.2%})"
                    ):
                        # Metadata del par
                        st.markdown(f"**Pair ID:** `{pair['pair_id']}`")
                        st.markdown(f"**Versión actual:** {pair['expected_version']}")
                        st.markdown(f"**Tipo:** {pair['duplicate_type']}")

                        if pair.get("similarity_method"):
                            st.markdown(f"**Método similitud:** {pair['similarity_method']}")
                        if pair.get("similarity_model"):
                            st.markdown(f"**Modelo:** {pair['similarity_model']}")

                        # Warnings de preview
                        if pair.get("preview_warning"):
                            st.warning(pair["preview_warning"])

                        # Side-by-side comparison
                        col1, col2 = st.columns(2)

                        with col1:
                            st.markdown("### 📄 Original (A)")
                            st.markdown(f"**ID:** `{pair['original_id']}`")
                            st.markdown(f"**Archivo:** {pair['original_filename']}")
                            st.markdown(f"**Fecha:** {pair['original_date']}")
                            st.markdown(f"**Tamaño:** {pair['original_total_length']} chars")
                            st.markdown(f"**Preview desde:** {pair['original_preview_location']}")
                            st.text_area(
                                "Contenido preview",
                                pair["original_preview"],
                                height=200,
                                key=f"preview_orig_{idx}",
                            )

                        with col2:
                            st.markdown("### 📄 Duplicado (B)")
                            st.markdown(f"**ID:** `{pair['duplicate_id']}`")
                            st.markdown(f"**Archivo:** {pair['duplicate_filename']}")
                            st.markdown(f"**Fecha:** {pair['duplicate_date']}")
                            st.markdown(f"**Tamaño:** {pair['duplicate_total_length']} chars")
                            st.markdown(f"**Preview desde:** {pair['duplicate_preview_location']}")
                            st.text_area(
                                "Contenido preview",
                                pair["duplicate_preview"],
                                height=200,
                                key=f"preview_dup_{idx}",
                            )

                        # Estado actual
                        if pair.get("action"):
                            st.info(
                                f"✅ **Decisión:** {pair['action']} "
                                f"por {pair.get('action_by', 'unknown')} "
                                f"el {pair.get('action_at')}"
                            )
                            if pair.get("action_reason"):
                                st.markdown(f"**Razón:** {pair['action_reason']}")
                        else:
                            st.warning("⏳ **Pendiente de decisión**")

                        # Formulario de decisión
                        st.markdown("---")
                        st.markdown("### 🎯 Tomar decisión")

                        with st.form(key=f"resolve_form_{pair['pair_id']}"):
                            action = st.selectbox(
                                "Acción",
                                ["keep_both", "mark_duplicate", "exclude_from_analysis"],
                                key=f"action_{idx}",
                            )

                            reason = st.text_area(
                                "Razón (obligatoria para legal)", key=f"reason_{idx}", height=80
                            )

                            decided_by = st.text_input(
                                "Decidido por (email/usuario)",
                                value="streamlit_user",
                                key=f"user_{idx}",
                            )

                            submitted = st.form_submit_button("✅ Confirmar decisión")

                            if submitted:
                                if not reason or len(reason) < 10:
                                    st.error(
                                        "❌ La razón debe tener al menos 10 caracteres (auditoría legal)"
                                    )
                                else:
                                    try:
                                        # ✅ RECIBIR RESPONSE COMPLETO con decision_version
                                        result = client.resolve_duplicate_action(
                                            case_id=case_id,
                                            document_id=pair["duplicate_id"],
                                            action=action,
                                            reason=reason,
                                            decided_by=decided_by,
                                            expected_version=pair["expected_version"],
                                        )
                                        st.success(
                                            f"✅ Decisión registrada: {action}\n\n"
                                            f"📌 Nueva versión: {result['decision_version']}\n"
                                            f"🔗 Par ID: {result['pair_id']}"
                                        )
                                        st.rerun()

                                    except Exception as e:
                                        error_msg = str(e)
                                        if (
                                            "409" in error_msg
                                            or "CONCURRENT_MODIFICATION" in error_msg
                                        ):
                                            st.error(
                                                "⚠️ **CONFLICTO DE CONCURRENCIA**\n\n"
                                                "Otro usuario modificó este par mientras lo editabas.\n"
                                                "**Recarga la página** y vuelve a intentarlo."
                                            )
                                        else:
                                            st.error(f"Error: {e}")


# Cierre del try principal del TAB 6 (Duplicados)
        except Exception as e:
            st.error(f"Error al cargar duplicados: {e}")


# =========================================
# TAB 9: JUZGADO (filesystem-only; NO API)
# =========================================
with tab9:
    import zipfile
    # (sin instrumentación debug)

    st.header("🏛️ Juzgado")

    # region agent log (debug-mode)
    def _dbg_log_tab9(hypothesis_id: str, location: str, message: str, data: dict) -> None:
        try:
            _path = "/Users/irumabragado/Documents/procesos/202512_phoenix-legal/.cursor/debug.log"
            payload = {
                "sessionId": "debug-session",
                "runId": "post-fix-justificante-v2",
                "hypothesisId": hypothesis_id,
                "location": location,
                "message": message,
                "data": data,
                "timestamp": int(time.time() * 1000),
            }
            with open(_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # endregion agent log (debug-mode)

    if not case_id:
        st.error("No hay caso activo seleccionado.")
    else:
        # Permitir que el caso activo sea una ruta absoluta (filesystem-only)
        _case_id_raw = str(case_id)
        _as_path = Path(_case_id_raw)
        if _as_path.is_absolute() and _as_path.exists():
            case_root = _as_path
            # Para artefactos internos, usamos el nombre de carpeta como id legible
            case_id = case_root.name
        else:
            case_root = Path("clients_data/cases") / str(case_id)
        paths = court_pack_service.ensure_court_pack_dirs(case_root)
        _dbg_log_tab9(
            "H1",
            "app/ui/streamlit_mvp.py:tab9",
            "tab9_paths_resolved",
            {
                "case_id": str(case_id),
                "case_root": str(case_root),
                "submissions_dir": str(paths.get("submissions_dir")) if isinstance(paths, dict) else None,
            },
        )

        state: Optional[CourtPackState] = None
        state_err: Optional[str] = None
        try:
            state = court_pack_service.load_state(case_root)
        except Exception as e:
            state_err = str(e)
            # No inventamos debtor_flags: mostramos guía clara y no bloqueamos el flujo.
            if "Missing debtor_flags in inputs/*.json" in state_err:
                st.error(
                    "Faltan `debtor_flags` en `court_pack/inputs/*.json`, por lo que NO se puede inicializar "
                    "`court_pack/state.json` (no se inventan flags)."
                )
                st.caption(
                    "Añade `debtor_flags` manualmente en (recomendado) "
                    f"`{paths['inputs_formulario_overrides']}` con este formato:"
                )
                st.code(
                    '{\n'
                    '  "debtor_flags": {\n'
                    '    "debtor_type": "juridica",\n'
                    '    "has_workers": false,\n'
                    '    "requires_audit": false,\n'
                    '    "accounting_obligation": false,\n'
                    '    "has_procurador": false\n'
                    "  }\n"
                    "}\n"
                )
            else:
                st.error(f"No se pudo cargar/crear `court_pack/state.json`: {e}")

        # Overrides (UI-only)
        overrides = {}
        try:
            overrides = json.loads(paths["inputs_formulario_overrides"].read_text(encoding="utf-8") or "{}")
            if not isinstance(overrides, dict):
                overrides = {}
        except Exception as e:
            overrides = {}
            st.error(f"`court_pack/inputs/formulario_overrides.json` no es JSON válido: {e}")

        has_overrides = bool(overrides)
        pack_status = getattr(getattr(state, "pack_status", None), "value", None) if state else None
        manual_overrides_count = int(getattr(state, "manual_overrides_count", 0) if state else len(overrides))

        # -------------------------------------------------
        # Wizard + mapeo manual PDF (persistidos por caso)
        # -------------------------------------------------
        try:
            wizard_def = json.loads(paths["inputs_wizard"].read_text(encoding="utf-8") or "{}")
            if not isinstance(wizard_def, dict):
                wizard_def = {}
        except Exception:
            wizard_def = {}

        try:
            wizard_answers = json.loads(paths.get("inputs_wizard_answers", paths["inputs_dir"] / "wizard_answers.json").read_text(encoding="utf-8") or "{}")
            if not isinstance(wizard_answers, dict):
                wizard_answers = {}
        except Exception:
            wizard_answers = {}

        try:
            fm_effective = json.loads(paths["inputs_field_map_effective"].read_text(encoding="utf-8") or "{}")
            if not isinstance(fm_effective, dict):
                fm_effective = {}
        except Exception:
            fm_effective = {}

        # Si están vacíos, precargar la definición del usuario (sin IA en el propio JSON; IA se usa vía wizard)
        if not wizard_def:
            wizard_def = {
                "wizard_id": "solicitud_concurso_pj_v1",
                "sections": [
                    {
                        "id": "A7",
                        "label": "Modificación del domicilio social en los últimos seis meses",
                        "type": "radio",
                        "required": True,
                        "options": [{"value": "si", "label": "Sí"}, {"value": "no", "label": "No"}],
                    },
                    {
                        "id": "B",
                        "label": "Representación procesal · Apoderamiento",
                        "type": "radio",
                        "required": True,
                        "options": [
                            {"value": "previamente_otorgado", "label": "Previamente otorgado"},
                            {"value": "apud_acta", "label": "Solicita otorgamiento apud acta"},
                        ],
                    },
                    {
                        "id": "C",
                        "label": "Datos de la insolvencia",
                        "fields": [
                            {
                                "id": "C1_insolvency_class",
                                "label": "Clase de insolvencia",
                                "type": "radio",
                                "required": True,
                                "options": [
                                    {"value": "actual", "label": "Actual"},
                                    {"value": "inminente", "label": "Inminente"},
                                ],
                            },
                            {
                                "id": "C2_insolvency_facts_text",
                                "label": "Hechos de los que deriva la situación de insolvencia",
                                "type": "textarea",
                                "required": True,
                                "max_chars": 500,
                                "llm": {"enabled": True, "prompt_id": "C2_HECHOS_INSOLVENCIA_500"},
                            },
                            {
                                "id": "C3_activity_ceased",
                                "label": "¿Ha cesado su actividad?",
                                "type": "radio",
                                "required": True,
                                "options": [{"value": "si", "label": "Sí"}, {"value": "no", "label": "No"}],
                            },
                            {"id": "C4_workers_count", "label": "Número de trabajadores", "type": "number", "required": True, "min": 0},
                            {"id": "C5_asset_value_eur", "label": "Valoración del activo (euros)", "type": "number", "required": True, "min": 0},
                            {"id": "C6_cash_eur", "label": "Tesorería (euros)", "type": "number", "required": True, "min": 0},
                            {"id": "C7_passive_amount_eur", "label": "Cuantía del pasivo (euros)", "type": "number", "required": True, "min": 0},
                            {"id": "C8_creditors_count", "label": "Número de acreedores", "type": "number", "required": True, "min": 0},
                            {
                                "id": "C9_fees",
                                "label": "Honorarios recibidos / Provisión de fondos",
                                "type": "group",
                                "fields": [
                                    {"id": "C9_fee_abogado_eur", "label": "Abogado/a (euros)", "type": "number", "min": 0},
                                    {"id": "C9_fee_procurador_eur", "label": "Procurador/a (euros)", "type": "number", "min": 0},
                                ],
                            },
                        ],
                    },
                    {
                        "id": "D",
                        "label": "Solución del concurso",
                        "type": "radio",
                        "required": True,
                        "options": [
                            {"value": "propuesta_anticipada_convenio", "label": "Propuesta anticipada de convenio"},
                            {"value": "convenio", "label": "Convenio"},
                            {"value": "liquidacion", "label": "Liquidación"},
                            {
                                "value": "plan_liquidacion_con_propuesta_vinculante_unidad_productiva",
                                "label": "Plan de liquidación con propuesta vinculante de compra de unidad productiva",
                            },
                        ],
                    },
                    {
                        "id": "E",
                        "label": "Declaración y conclusión por insuficiencia de masa activa",
                        "fields": [
                            {
                                "id": "E1_insufficiency_mass",
                                "label": "¿Se solicita insuficiencia de masa activa?",
                                "type": "radio",
                                "required": True,
                                "options": [{"value": "si", "label": "Sí"}, {"value": "no", "label": "No"}],
                            },
                            {
                                "id": "E2_insufficiency_justification_text",
                                "label": "Justificación",
                                "type": "textarea",
                                "required_if": {"field": "E1_insufficiency_mass", "equals": "si"},
                                "max_chars": 500,
                                "llm": {"enabled": True, "prompt_id": "E_INSUFICIENCIA_MASA_500"},
                            },
                        ],
                    },
                    {
                        "id": "F",
                        "label": "Documentación que acompaña a la solicitud",
                        "type": "checkbox_group",
                        "items": [
                            {"id": "doc1_poder_especial", "label": "Poder especial"},
                            {"id": "doc2_memoria_economica_y_juridica", "label": "Memoria económica y jurídica"},
                            {"id": "doc3_inventario_bienes_y_derechos", "label": "Inventario de bienes y derechos"},
                            {"id": "doc4_relacion_de_acreedores", "label": "Relación de acreedores"},
                            {"id": "doc5_plantilla_de_trabajadores", "label": "Plantilla de trabajadores"},
                            {"id": "doc61_cuentas_anuales_individuales", "label": "Cuentas anuales individuales", "years": ["year_1", "year_2", "year_3"]},
                            {"id": "doc62_cuentas_anuales_consolidadas", "label": "Cuentas anuales consolidadas", "years": ["year_1", "year_2", "year_3"]},
                            {"id": "doc7_estados_financieros", "label": "Estados financieros"},
                            {"id": "doc8_balance_de_situacion", "label": "Balance de situación"},
                            {"id": "doc9_memoria_cambios_significativos", "label": "Memoria de cambios significativos"},
                            {"id": "doc10_memoria_operaciones_extraordinarias", "label": "Memoria de operaciones extraordinarias"},
                            {"id": "doc11_propuesta_anticipada_de_convenio", "label": "Propuesta anticipada de convenio"},
                            {"id": "doc12_adhesiones", "label": "Adhesiones"},
                            {"id": "doc13_plan_de_liquidacion", "label": "Plan de liquidación"},
                        ],
                    },
                    {
                        "id": "G",
                        "label": "Observaciones",
                        "type": "textarea",
                        "required": False,
                        "max_chars": 500,
                        "llm": {"enabled": True, "prompt_id": "G_OBSERVACIONES_500"},
                    },
                ],
            }
            paths["inputs_wizard"].write_text(json.dumps(wizard_def, ensure_ascii=False, indent=2), encoding="utf-8")

        if not fm_effective:
            fm_effective = {
                "template_id": "concurso_voluntario_pj_20200521",
                "sections": [
                    
                ],
            }
            paths["inputs_field_map_effective"].write_text(json.dumps(fm_effective, ensure_ascii=False, indent=2), encoding="utf-8")

        # A) Header
        h1, h2, h3 = st.columns([1.2, 1, 1])
        with h1:
            st.write(f"**case_id:** `{case_id}`")
        with h2:
            st.write(f"**pack_status:** `{pack_status or '—'}`")
        with h3:
            st.write(f"**manual_overrides_count:** `{manual_overrides_count}`")

        # B) 1) Solicitud de concurso
        st.markdown("## Solicitud de concurso")
        # Mensaje eliminado por requerimiento de UI

        b1, b2, b3 = st.columns([1, 1, 1])
        with b1:
            do_generate = st.button("⚡ Generar solicitud de concurso", width="stretch")
        with b2:
            st.session_state.setdefault("juzgado_attach_panel", False)
            do_toggle_attach = st.button("📦 Preparar expediente", width="stretch")
            if do_toggle_attach:
                st.session_state["juzgado_attach_panel"] = not st.session_state.get("juzgado_attach_panel", False)
        with b3:
            doc0_path = paths["generated_doc0"]
            if doc0_path.exists():
                st.download_button(
                    "✉️ Enviar al portal del juzgado",
                    data=doc0_path.read_bytes(),
                    file_name=doc0_path.name,
                    mime="application/pdf",
                    width="stretch",
                )
            else:
                st.button("✉️ Enviar al portal del juzgado", disabled=True, width="stretch")

        if do_generate:
            # Autorrelleno C2 (insolvency.facts) al generar, si está vacío.
            # Objetivo: no depender del botón de autorrelleno; debe ocurrir al pulsar "Generar solicitud".
            try:
                _selected_raw = str(st.session_state.get("selected_case_id") or "")
                _is_abs_case = Path(_selected_raw).is_absolute()
            except Exception:
                _is_abs_case = False

            try:
                _dbg_log_tab9(
                    "H_C2_GEN",
                    "app/ui/streamlit_mvp.py:do_generate",
                    "generate_clicked",
                    {"case_id": str(case_id), "is_abs_case": bool(_is_abs_case)},
                )
            except Exception:
                pass

            def _sanitize_c2_text(raw: str) -> str:
                # Quitar citas/ruido; quedarnos con el cuerpo útil.
                if not raw:
                    return ""
                txt = str(raw)
                if "\n\n================================================================================" in txt:
                    txt = txt.split("\n\n================================================================================", 1)[0]
                # Quitar cabeceras de “wrap_response_with_evidence_notice”
                for prefix in (
                    "⚠️⚠️ Respuesta con nivel de confianza BAJO",
                    "⚠️ Respuesta con nivel de confianza medio",
                    "Respuesta fundamentada en",
                ):
                    if txt.lstrip().startswith(prefix):
                        # recortar primer bloque hasta doble salto si existe
                        parts = txt.split("\n\n", 2)
                        if len(parts) >= 2:
                            txt = parts[-1]
                return txt.strip()

            def _looks_auto_generated_c2(txt: str) -> bool:
                """
                Heurística para detectar C2 auto-generado (para poder regenerar si es mediocre).
                Evita pisar textos claramente redactados manualmente por el abogado.
                """
                if not txt:
                    return False
                t = str(txt).strip().lower()
                needles = [
                    "consta pasivo exigible",
                    "factura(s) pendiente(s)",
                    "acreedor(es) identificado(s)",
                    "ej.: factura pendiente",
                    "a rellenar por el abogado",
                ]
                return any(n in t for n in needles)

            try:
                # Si ya hay insolvency.facts en overrides, no tocar.
                try:
                    _overrides_now = json.loads(paths["inputs_formulario_overrides"].read_text(encoding="utf-8") or "{}")
                    if not isinstance(_overrides_now, dict):
                        _overrides_now = {}
                except Exception:
                    _overrides_now = {}

                _facts_existing = str(_overrides_now.get("insolvency.facts") or "").strip()
                _dbg_log_tab9(
                    "H_C2_GEN",
                    "app/ui/streamlit_mvp.py:do_generate",
                    "c2_before",
                    {"case_id": str(case_id), "facts_existing_len": len(_facts_existing)},
                )

                # -------------------------------------------------
                # Autofill estructurado C3–C8 desde BD (y RAG solo si falta)
                # -------------------------------------------------
                try:
                    client = get_api_client()
                    kpis = client.get_situation_kpis(str(case_id)) or {}
                except Exception:
                    kpis = {}
                try:
                    editables = client.get_economic_report_editables(str(case_id)) if (not _is_abs_case) else {}
                except Exception:
                    editables = {}
                try:
                    raw_auto = json.loads(paths["inputs_formulario_auto"].read_text(encoding="utf-8") or "{}")
                except Exception:
                    raw_auto = {}
                try:
                    fin = client.get_financial_analysis(str(case_id))
                except Exception:
                    fin = None

                def _get_val(x: Any) -> Any:
                    if x is None:
                        return None
                    if isinstance(x, dict):
                        return x.get("value")
                    return getattr(x, "value", None)

                def _parse_number_from_text(txt: str) -> Optional[float]:
                    if not txt:
                        return None
                    s = str(txt)
                    # buscar primer número (tolerar separadores y coma decimal)
                    m = re.search(r"(-?\d[\d\.\s]*\,?\d*)", s)
                    if not m:
                        return None
                    raw = m.group(1).strip().replace(" ", "")
                    # normalizar: "1.234,56" -> "1234.56" ; "1234,56" -> "1234.56"
                    if "," in raw and "." in raw:
                        raw = raw.replace(".", "").replace(",", ".")
                    elif "," in raw:
                        raw = raw.replace(",", ".")
                    try:
                        return float(raw)
                    except Exception:
                        return None

                def _is_blank(v: Any) -> bool:
                    if v is None:
                        return True
                    if isinstance(v, str):
                        return not v.strip()
                    return False

                # C3 company.ceased_activity (SI/NO) — si no hay dato estructurado, dejamos al wizard.
                # C4 workers.count — si no hay dato estructurado, intentar RAG; si falla, fallback 0 (pero trazado).
                if _is_blank(_overrides_now.get("workers.count")):
                    # 1) Intentar desde economic-report/editables (si algún día lo trae)
                    maybe_workers = None
                    try:
                        maybe_workers = (editables or {}).get("workers_count") or (editables or {}).get("employees_count")
                    except Exception:
                        maybe_workers = None
                    if isinstance(maybe_workers, (int, float)):
                        _overrides_now["workers.count"] = int(float(maybe_workers))
                    else:
                        # 2) RAG: pedir solo un número (o NO_CONSTA)
                        try:
                            respw = client.rag_ask(
                                str(case_id),
                                "¿Cuántos trabajadores tiene la empresa? Responde SOLO con un número entero (0 si no tiene). "
                                "Si NO CONSTA en los documentos, responde exactamente: NO_CONSTA.",
                                top_k=8,
                            )
                            rt = str(respw.get("response_type") or "").strip()
                            ans = str(respw.get("answer") or "").strip()
                            n = _parse_number_from_text(ans)
                            # #region agent log
                            _dbg_log_tab9(
                                "H_CX_GEN",
                                "app/ui/streamlit_mvp.py:do_generate",
                                "workers_rag_probe",
                                {"case_id": str(case_id), "response_type": rt, "answer_len": len(ans), "parsed": n is not None},
                            )
                            # #endregion
                            if rt in ("RESPUESTA_CON_EVIDENCIA", "INFORMACION_PARCIAL_NO_CONCLUYENTE") and isinstance(n, (int, float)):
                                _overrides_now["workers.count"] = int(max(0, round(float(n))))
                        except Exception:
                            pass
                    # 3) Fallback último
                    if _is_blank(_overrides_now.get("workers.count")):
                        _overrides_now["workers.count"] = 0

                # Totales: preferir Balance (financial-analysis) para activo/pasivo; complementar con KPIs/editables.
                bal = getattr(fin, "balance", None) if fin is not None else None
                activo_total = _get_val(getattr(bal, "activo_total", None)) if bal is not None else None
                pasivo_total = _get_val(getattr(bal, "pasivo_total", None)) if bal is not None else None

                # C7 pasivo (EUR): usar pasivo_total si existe; si no, KPIs.
                cur_pasivo = _overrides_now.get("totals.passive_amount")
                if isinstance(pasivo_total, (int, float)):
                    try:
                        cur_num = float(cur_pasivo) if isinstance(cur_pasivo, (int, float)) else None
                    except Exception:
                        cur_num = None
                    # si estaba vacío o era un "pasivo parcial" (muy inferior), preferir balance
                    if cur_num is None or cur_num <= 0 or (cur_num > 0 and cur_num < float(pasivo_total) * 0.5):
                        _overrides_now["totals.passive_amount"] = float(pasivo_total)
                elif _is_blank(cur_pasivo) and isinstance(kpis.get("total_pasivo"), (int, float)):
                    _overrides_now["totals.passive_amount"] = float(kpis["total_pasivo"])

                # C5 activo (EUR): usar activo_total si existe; si no, intentar activos del cuadro de situación.
                if _is_blank(_overrides_now.get("totals.asset_value")) and isinstance(activo_total, (int, float)):
                    _overrides_now["totals.asset_value"] = float(activo_total)

                # Tesorería y activo: si no existe, intentar derivar de editables (si el reporte lo trae) o dejar vacío.
                # (No inventamos: si no hay, no hay.)
                if _is_blank(_overrides_now.get("totals.cash")):
                    try:
                        maybe_cash = (editables or {}).get("cash_total") or (editables or {}).get("totals", {}).get("cash")
                    except Exception:
                        maybe_cash = None
                    if isinstance(maybe_cash, (int, float)):
                        _overrides_now["totals.cash"] = float(maybe_cash)
                    else:
                        # RAG: intentar extraer cifra de tesorería si consta (solo si hay evidencia).
                        try:
                            respc = client.rag_ask(
                                str(case_id),
                                "Indica el importe de tesorería/efectivo en euros. Responde SOLO con un número (EUR). "
                                "Si NO CONSTA en los documentos, responde exactamente: NO_CONSTA.",
                                top_k=8,
                            )
                            rt = str(respc.get("response_type") or "").strip()
                            ans = str(respc.get("answer") or "").strip()
                            n = _parse_number_from_text(ans)
                            # #region agent log
                            _dbg_log_tab9(
                                "H_CX_GEN",
                                "app/ui/streamlit_mvp.py:do_generate",
                                "cash_rag_probe",
                                {"case_id": str(case_id), "response_type": rt, "answer_len": len(ans), "parsed": n is not None},
                            )
                            # #endregion
                            if rt in ("RESPUESTA_CON_EVIDENCIA", "INFORMACION_PARCIAL_NO_CONCLUYENTE") and isinstance(n, (int, float)):
                                _overrides_now["totals.cash"] = float(max(0.0, float(n)))
                        except Exception:
                            pass

                if _is_blank(_overrides_now.get("totals.asset_value")):
                    try:
                        maybe_asset = (editables or {}).get("asset_total") or (editables or {}).get("totals", {}).get("asset_value")
                    except Exception:
                        maybe_asset = None
                    if isinstance(maybe_asset, (int, float)):
                        _overrides_now["totals.asset_value"] = float(maybe_asset)
                    else:
                        # Fallback BD: sumar activos del cuadro de situación si existe endpoint /situation/assets
                        try:
                            assets = client.list_situation_assets(
                                str(case_id), page=1, page_size=200, include_history=False
                            )
                            items = (assets or {}).get("items") or []
                        except Exception:
                            items = []
                        total_assets = 0.0
                        used = 0
                        for it in items:
                            if not isinstance(it, dict):
                                continue
                            data = it.get("data") or {}
                            # tolerar distintos nombres de clave
                            for key in ("value_ext", "value_eur", "valuation_eur", "amount_eur", "value"):
                                v = data.get(key)
                                if isinstance(v, (int, float)) and float(v) >= 0:
                                    total_assets += float(v)
                                    used += 1
                                    break
                        if used > 0:
                            _overrides_now["totals.asset_value"] = float(total_assets)
                        _dbg_log_tab9(
                            "H_CX_GEN",
                            "app/ui/streamlit_mvp.py:do_generate",
                            "assets_sum_probe",
                            {"case_id": str(case_id), "assets_items": len(items), "used": used, "sum": total_assets},
                        )

                # C8 nº acreedores: derivar desde economic-report/editables (debts) y, si hace falta, formulario_auto.
                try:
                    debts = (editables or {}).get("debts") or []
                except Exception:
                    debts = []
                uniq_creditors = set()
                if isinstance(debts, list):
                    for d in debts:
                        if not isinstance(d, dict):
                            continue
                        name = str(d.get("creditor_name") or "").strip().lower()
                        if name:
                            uniq_creditors.add(name)
                derived_creditors = len(uniq_creditors)
                kpi_creditors = kpis.get("num_acreedores") if isinstance(kpis, dict) else None
                auto_creditors = raw_auto.get("creditors.count") if isinstance(raw_auto, dict) else None
                cur_creditors = _overrides_now.get("totals.creditors_count")
                cur_c = None
                try:
                    if isinstance(cur_creditors, (int, float)):
                        cur_c = int(float(cur_creditors))
                except Exception:
                    cur_c = None
                # Selección: si el actual está vacío/0, usar el máximo informado por (debts/editables, formulario_auto, KPIs)
                candidate = 0
                for v in (derived_creditors, auto_creditors, kpi_creditors):
                    try:
                        if isinstance(v, (int, float)) and int(v) > candidate:
                            candidate = int(v)
                    except Exception:
                        pass
                if cur_c is None or cur_c <= 0:
                    if candidate > 0:
                        _overrides_now["totals.creditors_count"] = int(candidate)
                # #region agent log
                _dbg_log_tab9(
                    "H_CX_GEN",
                    "app/ui/streamlit_mvp.py:do_generate",
                    "creditors_derived_probe",
                    {
                        "case_id": str(case_id),
                        "debts_len": len(debts) if isinstance(debts, list) else -1,
                        "derived_creditors": derived_creditors,
                        "auto_creditors": auto_creditors,
                        "kpi_creditors": kpi_creditors,
                        "final": _overrides_now.get("totals.creditors_count"),
                    },
                )
                # #endregion

                _dbg_log_tab9(
                    "H_CX_GEN",
                    "app/ui/streamlit_mvp.py:do_generate",
                    "structured_fill_snapshot",
                    {
                        "case_id": str(case_id),
                        "kpis_keys": sorted(list(kpis.keys()))[:25] if isinstance(kpis, dict) else [],
                        "has_total_pasivo": isinstance(kpis.get("total_pasivo"), (int, float)) if isinstance(kpis, dict) else False,
                        "has_num_acreedores": isinstance(kpis.get("num_acreedores"), int) if isinstance(kpis, dict) else False,
                        "auto_creditors_count": raw_auto.get("creditors.count") if isinstance(raw_auto, dict) else None,
                        "fa_has_balance": bool(bal is not None),
                        "fa_activo_total": activo_total,
                        "fa_pasivo_total": pasivo_total,
                        "totals.passive_amount": _overrides_now.get("totals.passive_amount"),
                        "totals.creditors_count": _overrides_now.get("totals.creditors_count"),
                        "workers.count": _overrides_now.get("workers.count"),
                        "totals.cash": _overrides_now.get("totals.cash"),
                        "totals.asset_value": _overrides_now.get("totals.asset_value"),
                    },
                )

                # Persistir si hemos añadido algo nuevo (sin pisar si ya venía)
                paths["inputs_formulario_overrides"].write_text(
                    json.dumps(_overrides_now, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                # C2: regenerar si está vacío o si parece auto-generado/insuficiente.
                _regen_c2 = (not _is_abs_case) and (
                    (not _facts_existing)
                    or (len(_facts_existing) < 140)
                    or _looks_auto_generated_c2(_facts_existing)
                )
                try:
                    _dbg_log_tab9(
                        "H_C2_GEN",
                        "app/ui/streamlit_mvp.py:do_generate",
                        "c2_regen_decision",
                        {
                            "case_id": str(case_id),
                            "regen": bool(_regen_c2),
                            "existing_len": len(_facts_existing),
                            "looks_auto": bool(_looks_auto_generated_c2(_facts_existing)),
                        },
                    )
                except Exception:
                    pass

                if _regen_c2:
                    # Intentar generar C2 con RAG/LLM del backend (si hay evidencia).
                    try:
                        client = get_api_client()
                        resp = client.rag_ask(
                            str(case_id),
                            "Redacta en español un texto (máx 500 caracteres) de hechos que derivan la insolvencia, "
                            "basado solo en la documentación del caso. Sin conclusiones legales.",
                            top_k=8,
                        )
                        rt = str(resp.get("response_type") or "").strip()
                        ans_raw = str(resp.get("answer") or "").strip()
                        _dbg_log_tab9(
                            "H_C2_GEN",
                            "app/ui/streamlit_mvp.py:do_generate",
                            "c2_rag_result",
                            {"case_id": str(case_id), "response_type": rt, "answer_len": len(ans_raw)},
                        )

                        c2_txt = ""
                        if rt in ("RESPUESTA_CON_EVIDENCIA", "INFORMACION_PARCIAL_NO_CONCLUYENTE"):
                            c2_txt = _sanitize_c2_text(ans_raw)[:500]

                        # Fallback: si RAG no puede (EVIDENCIA_INSUFICIENTE / SISTEMA...), construir C2 desde datos estructurados.
                        if not c2_txt:
                            parts: list[str] = []
                            # Preferir balance (financial-analysis) si existe; si no, KPIs.
                            try:
                                if isinstance(activo_total, (int, float)) and isinstance(pasivo_total, (int, float)):
                                    parts.append(
                                        f"Del balance analizado se desprende un activo total aprox. {float(activo_total):.2f} EUR "
                                        f"y un pasivo total aprox. {float(pasivo_total):.2f} EUR."
                                    )
                                    if float(pasivo_total) > float(activo_total) and float(activo_total) > 0:
                                        parts.append("El pasivo total supera al activo total.")
                            except Exception:
                                pass

                            # Acreedores / deudas (economic-report/editables)
                            try:
                                if isinstance(derived_creditors, int) and derived_creditors > 0:
                                    parts.append(f"Consta relación de deudas con {int(derived_creditors)} acreedor(es).")
                            except Exception:
                                pass
                            try:
                                total_debts = 0.0
                                for d in debts if isinstance(debts, list) else []:
                                    if not isinstance(d, dict):
                                        continue
                                    amt = d.get("amount_eur")
                                    if isinstance(amt, (int, float)) and float(amt) > 0:
                                        total_debts += float(amt)
                                if total_debts > 0:
                                    parts.append(f"Importe total de deudas inventariadas aprox. {float(total_debts):.2f} EUR.")
                            except Exception:
                                pass

                            # Facturas pendientes (KPIs)
                            try:
                                num_facturas = kpis.get("num_facturas") if isinstance(kpis, dict) else None
                                if isinstance(num_facturas, int) and num_facturas > 0:
                                    parts.append(f"Constan {int(num_facturas)} factura(s) pendiente(s) de pago.")
                            except Exception:
                                pass

                            # Si hay facturas, añadir un ejemplo (proveedor + importe) para mayor concreción.
                            try:
                                inv = client.list_situation_invoices(
                                    str(case_id), page=1, page_size=1, include_history=False
                                )
                                items = (inv or {}).get("items") or []
                                if items and isinstance(items, list) and isinstance(items[0], dict):
                                    data0 = items[0].get("data") or {}
                                    supplier = data0.get("supplier") or data0.get("proveedor")
                                    amt = (
                                        data0.get("amount_eur")
                                        or data0.get("amount")
                                        or data0.get("total_eur")
                                        or data0.get("total")
                                    )
                                    if supplier and isinstance(amt, (int, float)) and float(amt) > 0:
                                        parts.append(f"Ej.: factura pendiente con {supplier} por {float(amt):.2f} EUR.")
                            except Exception:
                                pass

                            if parts:
                                c2_txt = " ".join(parts).strip()[:500]
                                _dbg_log_tab9(
                                    "H_C2_GEN",
                                    "app/ui/streamlit_mvp.py:do_generate",
                                    "c2_structured_built_v2",
                                    {
                                        "case_id": str(case_id),
                                        "parts": len(parts),
                                        "text_len": len(c2_txt),
                                        "fa_has_balance": bool(bal is not None),
                                        "fa_activo_total": activo_total,
                                        "fa_pasivo_total": pasivo_total,
                                        "derived_creditors": derived_creditors,
                                    },
                                )
                            else:
                                _dbg_log_tab9(
                                    "H_C2_GEN",
                                    "app/ui/streamlit_mvp.py:do_generate",
                                    "c2_structured_empty",
                                    {"case_id": str(case_id), "response_type": rt},
                                )

                        # Si tras todo tenemos texto, escribirlo en overrides y reflejarlo en UI.
                        if c2_txt:
                            _overrides_now["insolvency.facts"] = c2_txt
                            paths["inputs_formulario_overrides"].write_text(
                                json.dumps(_overrides_now, ensure_ascii=False, indent=2),
                                encoding="utf-8",
                            )
                            # Reflejar también en UI (wizard_state + widget key) para que se vea tras el rerun.
                            try:
                                _ws = st.session_state.setdefault(f"juzgado_wizard_state__{case_id}", {})
                                if isinstance(_ws, dict):
                                    _ws["C2"] = c2_txt
                            except Exception:
                                pass
                            _dbg_log_tab9(
                                "H_C2_GEN",
                                "app/ui/streamlit_mvp.py:do_generate",
                                "c2_written",
                                {"case_id": str(case_id), "written_len": len(c2_txt)},
                            )
                        else:
                            _dbg_log_tab9(
                                "H_C2_GEN",
                                "app/ui/streamlit_mvp.py:do_generate",
                                "c2_skipped_no_text",
                                {"case_id": str(case_id), "response_type": rt},
                            )
                    except Exception as e:
                        _dbg_log_tab9(
                            "H_C2_GEN",
                            "app/ui/streamlit_mvp.py:do_generate",
                            "c2_rag_error",
                            {"case_id": str(case_id), "err": str(type(e).__name__)},
                        )

                # -------------------------------------------------
                # Autorrelleno E2 (insufficiency.justification) al generar
                # -------------------------------------------------
                try:
                    _e1_req = str(_overrides_now.get("insufficiency.requested") or "").strip().lower()
                except Exception:
                    _e1_req = ""
                if not _e1_req:
                    try:
                        _e1_req = str((wizard_answers.get("answers") or {}).get("E1") or "").strip().lower()
                    except Exception:
                        _e1_req = ""
                try:
                    _e2_existing = str(_overrides_now.get("insufficiency.justification") or "").strip()
                except Exception:
                    _e2_existing = ""

                _dbg_log_tab9(
                    "H_E2_GEN",
                    "app/ui/streamlit_mvp.py:do_generate",
                    "e2_before",
                    {"case_id": str(case_id), "requested": _e1_req, "e2_existing_len": len(_e2_existing)},
                )

                if (_e1_req == "si") and (not _e2_existing) and (not _is_abs_case):
                    try:
                        client = get_api_client()
                        resp = client.rag_ask(
                            str(case_id),
                            "Redacta una justificación (máx 500 caracteres) para solicitud de insuficiencia de masa activa "
                            "basada solo en documentación del caso. Sin conclusiones legales.",
                            top_k=8,
                        )
                        rt = str(resp.get("response_type") or "").strip()
                        ans_raw = str(resp.get("answer") or "").strip()
                        _dbg_log_tab9(
                            "H_E2_GEN",
                            "app/ui/streamlit_mvp.py:do_generate",
                            "e2_rag_result",
                            {"case_id": str(case_id), "response_type": rt, "answer_len": len(ans_raw)},
                        )

                        e2_txt = ""
                        if rt in ("RESPUESTA_CON_EVIDENCIA", "INFORMACION_PARCIAL_NO_CONCLUYENTE"):
                            e2_txt = _sanitize_c2_text(ans_raw)[:500]

                        if not e2_txt:
                            # Fallback estructurado basado en KPIs
                            try:
                                kpis = client.get_situation_kpis(str(case_id)) or {}
                            except Exception:
                                kpis = {}
                            total_pasivo = kpis.get("total_pasivo")
                            num_bienes = kpis.get("num_bienes")
                            num_facturas = kpis.get("num_facturas")
                            parts: list[str] = []
                            try:
                                if isinstance(num_bienes, int) and num_bienes == 0:
                                    parts.append("No constan bienes/derechos identificados en el expediente (cuadro de situación).")
                            except Exception:
                                pass
                            try:
                                if isinstance(num_facturas, int) and num_facturas > 0:
                                    parts.append(f"Constan {int(num_facturas)} factura(s) pendiente(s) de pago.")
                            except Exception:
                                pass
                            try:
                                if isinstance(total_pasivo, (int, float)) and float(total_pasivo) > 0:
                                    parts.append(f"Consta pasivo exigible aproximado de {float(total_pasivo):.2f} EUR.")
                            except Exception:
                                pass
                            if parts:
                                e2_txt = " ".join(parts).strip()[:500]
                                _dbg_log_tab9(
                                    "H_E2_GEN",
                                    "app/ui/streamlit_mvp.py:do_generate",
                                    "e2_structured_built",
                                    {"case_id": str(case_id), "parts": len(parts), "text_len": len(e2_txt)},
                                )

                        if e2_txt:
                            # Asegurar que E1 queda persistido si venía del wizard
                            if _e1_req in ("si", "no") and not str(_overrides_now.get("insufficiency.requested") or "").strip():
                                _overrides_now["insufficiency.requested"] = _e1_req
                            _overrides_now["insufficiency.justification"] = e2_txt
                            paths["inputs_formulario_overrides"].write_text(
                                json.dumps(_overrides_now, ensure_ascii=False, indent=2),
                                encoding="utf-8",
                            )
                            try:
                                _ws = st.session_state.setdefault(f"juzgado_wizard_state__{case_id}", {})
                                if isinstance(_ws, dict):
                                    _ws["E2"] = e2_txt
                            except Exception:
                                pass
                            _dbg_log_tab9(
                                "H_E2_GEN",
                                "app/ui/streamlit_mvp.py:do_generate",
                                "e2_written",
                                {"case_id": str(case_id), "written_len": len(e2_txt)},
                            )
                        else:
                            _dbg_log_tab9(
                                "H_E2_GEN",
                                "app/ui/streamlit_mvp.py:do_generate",
                                "e2_skipped_no_text",
                                {"case_id": str(case_id), "response_type": rt},
                            )
                    except Exception as e:
                        _dbg_log_tab9(
                            "H_E2_GEN",
                            "app/ui/streamlit_mvp.py:do_generate",
                            "e2_error",
                            {"case_id": str(case_id), "err": str(type(e).__name__)},
                        )
            except Exception:
                pass

            # 0) Snapshot DB → FS (case_profile.json) para pre-rellenar con datos estructurados ya ingeridos.
            # Si el caso activo es una ruta absoluta (filesystem-only), evitamos llamar a API por case_id.
            if not (Path(str(st.session_state.get("selected_case_id") or "")).is_absolute()):
                try:
                    client = get_api_client()
                    _ = client.snapshot_court_case_profile(str(case_id))
                except Exception as e:
                    st.error(f"No se pudo preparar datos del caso (snapshot): {e}")

            # Intentar inicializar state desde inputs si aún no existe (sin inventar debtor_flags).
            if state is None:
                try:
                    raw_final = json.loads(paths["inputs_formulario_final"].read_text(encoding="utf-8") or "{}")
                except Exception:
                    raw_final = {}
                try:
                    raw_over = json.loads(paths["inputs_formulario_overrides"].read_text(encoding="utf-8") or "{}")
                except Exception:
                    raw_over = {}
                try:
                    raw_auto = json.loads(paths["inputs_formulario_auto"].read_text(encoding="utf-8") or "{}")
                except Exception:
                    raw_auto = {}

                flags_obj = None
                for src in (raw_final, raw_over, raw_auto):
                    if isinstance(src, dict) and isinstance(src.get("debtor_flags"), dict):
                        flags_obj = src.get("debtor_flags")
                        break
                if flags_obj is not None:
                    try:
                        flags = DebtorFlags.model_validate(flags_obj)
                        state = court_pack_service.init_state(case_root, str(case_id), flags)
                        court_pack_service.save_state(case_root, state)
                    except Exception as e:
                        state = None

            if state is None:
                st.error("No hay CourtPackState (faltan debtor_flags en inputs).")
            else:
                try:
                    # Plantilla base obligatoria
                    pdf_form_filler.TEMPLATE_PDF_PATH = Path(
                        "judicial_forms/concurso_voluntario/personas_juridicas/"
                        "20200521 Procedimientos concursales - Formulario para la solicitud de concurso voluntario pers. jur..pdf"
                    )
                    pdf_form_filler.FIELD_MAP_PATH = Path(
                        "judicial_forms/concurso_voluntario/personas_juridicas/field_map.json"
                    )
                    _ = pdf_form_filler.generate_document_0(case_root, state, user_id="ui")
                    # Reflejar resultado real (p.ej. no_acroform) sin decir "Documento 0"
                    try:
                        state2 = court_pack_service.load_state(case_root)
                        doc0 = None
                        for d in state2.documents:
                            if d.doc_type == "doc0_formulario":
                                doc0 = d
                                break
                        if doc0 and int(doc0.errors_count or 0) > 0:
                            msg = None
                            try:
                                if doc0.issues:
                                    msg = doc0.issues[0].message
                            except Exception:
                                msg = None
                            st.error(f"No se pudo rellenar la solicitud: {msg or 'error'}")
                        else:
                            st.success("✅ Solicitud generada.")
                    except Exception:
                        st.success("✅ Solicitud generada.")
                    # Auto-abrir editor tras generar
                    st.session_state["juzgado_review_panel"] = True
                    st.rerun()
                except FileNotFoundError as e:
                    st.error(
                        f"Falta recurso obligatorio: {e}.\n"
                        "Revisa template PDF y/o field_map.json (placeholder permitido)."
                    )
                except Exception as e:
                    st.error(f"Error generando la solicitud: {e}")

        # Vista previa del PDF (DESACTIVADA): el usuario no quiere el bloque/iframe bajo los botones.
        doc0_path = paths["generated_doc0"]

        # Revisión/edición de campos (solo UI; requiere field_map)
        st.session_state.setdefault("juzgado_review_panel", False)
        # (Botón "Lupita · Revisar" eliminado por requerimiento de UI)

        if st.session_state.get("juzgado_review_panel", False):
            # Preferir field_map_effective.json (semántico) si existe; si no, usar RAW del caso; si no, el del repo.
            try:
                case_effective = paths["inputs_dir"] / "field_map_effective.json"
                case_raw = paths["inputs_dir"] / "field_map_raw.json"
                if case_effective.exists():
                    fm_path = case_effective
                elif case_raw.exists():
                    fm_path = case_raw
                else:
                    fm_path = Path("judicial_forms/concurso_voluntario/personas_juridicas/field_map.json")
                fm = pdf_form_filler.load_field_map(fm_path)
                sections = fm.get("sections") or []
            except Exception as e:
                st.error(f"field_map.json inválido: {e}")
                sections = []

            # Si no hay field_map_effective, ofrecer UI de mapeo semántico→PDF para poder rellenar desde DB.
            case_effective = paths["inputs_dir"] / "field_map_effective.json"
            case_raw = paths["inputs_dir"] / "field_map_raw.json"
            if not case_effective.exists() and case_raw.exists():
                # Bloque eliminado por UX: no mostrar mapeo semántico→PDF ni lista de keys (debtor.*, insolvency.*, totals.*).
                # Si se necesita reactivar en el futuro, debe hacerse en una pantalla/toggle separado, no aquí.
                pass

            # Leer final (base) y overrides (editable)
            try:
                final_vals = json.loads(paths["inputs_formulario_final"].read_text(encoding="utf-8") or "{}")
                if not isinstance(final_vals, dict):
                    final_vals = {}
            except Exception:
                final_vals = {}

            try:
                current_overrides = json.loads(paths["inputs_formulario_overrides"].read_text(encoding="utf-8") or "{}")
                if not isinstance(current_overrides, dict):
                    current_overrides = {}
            except Exception:
                current_overrides = {}

            # -------------------------------------------
            # Wizard A7/B/C/D/E/F (persistido por caso)
            # -------------------------------------------
            st.markdown("---")
            st.caption("Responde en orden. Debajo verás una recomendación(en rojo).")

            wizard_state: dict[str, Any] = st.session_state.setdefault(f"juzgado_wizard_state__{case_id}", {})
            if not wizard_state and isinstance(wizard_answers.get("answers"), dict):
                wizard_state.update(wizard_answers.get("answers"))

            # Seed desde overrides (fuente de verdad) para que C2/E2 se vean rellenados en UI
            # incluso si wizard_answers.json tiene "" o la sesión es nueva.
            try:
                _seed_c2 = str((current_overrides or {}).get("insolvency.facts") or "").strip()
            except Exception:
                _seed_c2 = ""
            try:
                _seed_e2 = str((current_overrides or {}).get("insufficiency.justification") or "").strip()
            except Exception:
                _seed_e2 = ""
            # Seed C3–C8 desde BD/overrides (valores estructurados)
            try:
                _seed_c3 = str((current_overrides or {}).get("company.ceased_activity") or "").strip()
            except Exception:
                _seed_c3 = ""
            try:
                _seed_c4 = (current_overrides or {}).get("workers.count")
            except Exception:
                _seed_c4 = None
            try:
                _seed_c5 = (current_overrides or {}).get("totals.asset_value")
            except Exception:
                _seed_c5 = None
            try:
                _seed_c6 = (current_overrides or {}).get("totals.cash")
            except Exception:
                _seed_c6 = None
            try:
                _seed_c7 = (current_overrides or {}).get("totals.passive_amount")
            except Exception:
                _seed_c7 = None
            try:
                _seed_c8 = (current_overrides or {}).get("totals.creditors_count")
            except Exception:
                _seed_c8 = None
            if _seed_c2 and (not str(wizard_state.get("C2") or "").strip()):
                wizard_state["C2"] = _seed_c2[:500]
                try:
                    _dbg_log_tab9(
                        "H_SEED_WIZ",
                        "app/ui/streamlit_mvp.py:wizard_seed",
                        "seeded_c2_from_overrides",
                        {"case_id": str(case_id), "seed_len": len(_seed_c2)},
                    )
                except Exception:
                    pass
            if _seed_e2 and (not str(wizard_state.get("E2") or "").strip()):
                wizard_state["E2"] = _seed_e2[:500]
                try:
                    _dbg_log_tab9(
                        "H_SEED_WIZ",
                        "app/ui/streamlit_mvp.py:wizard_seed",
                        "seeded_e2_from_overrides",
                        {"case_id": str(case_id), "seed_len": len(_seed_e2)},
                    )
                except Exception:
                    pass
            if _seed_c3 and (not str(wizard_state.get("C3") or "").strip()):
                # Normalizar a si/no
                _v = _seed_c3.lower()
                if _v in ("si", "no"):
                    wizard_state["C3"] = _v
            if _seed_c4 is not None and wizard_state.get("C4") in (None, "", 0):
                try:
                    wizard_state["C4"] = int(float(_seed_c4) if _seed_c4 is not None else 0)
                except Exception:
                    pass
            if _seed_c5 is not None and wizard_state.get("C5") in (None, "", 0.0):
                try:
                    wizard_state["C5"] = float(_seed_c5)
                except Exception:
                    pass
            if _seed_c6 is not None and wizard_state.get("C6") in (None, "", 0.0):
                try:
                    wizard_state["C6"] = float(_seed_c6)
                except Exception:
                    pass
            if _seed_c7 is not None and wizard_state.get("C7") in (None, "", 0.0):
                try:
                    wizard_state["C7"] = float(_seed_c7)
                except Exception:
                    pass
            if _seed_c8 is not None and wizard_state.get("C8") in (None, "", 0):
                try:
                    wizard_state["C8"] = int(float(_seed_c8))
                except Exception:
                    pass
            # #region agent log
            try:
                _dbg_log_tab9(
                    "H_SEED_WIZ",
                    "app/ui/streamlit_mvp.py:wizard_seed",
                    "seeded_c4_c8_from_overrides",
                    {
                        "case_id": str(case_id),
                        "seed_c4": _seed_c4,
                        "seed_c5": _seed_c5,
                        "seed_c6": _seed_c6,
                        "seed_c7": _seed_c7,
                        "seed_c8": _seed_c8,
                    },
                )
            except Exception:
                pass
            # #endregion
            _client = None
            try:
                _client = get_api_client()
            except Exception:
                _client = None

            # region agent log (debug-mode)
            def _dbg_log_wizard(hypothesis_id: str, location: str, message: str, data: dict) -> None:
                try:
                    _path = "/Users/irumabragado/Documents/procesos/202512_phoenix-legal/.cursor/debug.log"
                    payload = {
                        "sessionId": "debug-session",
                        "runId": "ui-wizard-compact-v1",
                        "hypothesisId": hypothesis_id,
                        "location": location,
                        "message": message,
                        "data": data,
                        "timestamp": int(__import__("time").time() * 1000),
                    }
                    with open(_path, "a", encoding="utf-8") as f:
                        f.write(__import__("json").dumps(payload, ensure_ascii=False) + "\n")
                except Exception:
                    pass

            # endregion agent log (debug-mode)

            def _rag_recommend(key: str, question: str) -> Optional[str]:
                if _client is None:
                    return None
                cache_key = f"juzgado_rag__{case_id}__{key}"
                if cache_key in st.session_state:
                    return st.session_state.get(cache_key)
                try:
                    resp = _client.rag_ask(str(case_id), question, top_k=8)
                    raw_answer = str(resp.get("answer") or "").strip()
                    response_type = str(resp.get("response_type") or "").strip()

                    # Modo compacto SOLO para "recomendaciones" visuales del wizard (no para autorrellenos C2/E2)
                    compact_key = key in ("A7", "B", "C1", "D")
                    if compact_key:
                        if response_type == "EVIDENCIA_INSUFICIENTE":
                            shown = "A rellenar por el Abogado."
                        else:
                            shown = "Respuesta recomendada. Revisar"
                        st.session_state[cache_key] = shown
                        # Guardar también la respuesta cruda por si se necesita auditar/debug
                        st.session_state[f"{cache_key}__raw"] = raw_answer
                        _dbg_log_wizard(
                            "H_UI_WIZ",
                            "app/ui/streamlit_mvp.py:_rag_recommend",
                            "rag_compact_applied",
                            {
                                "case_id": str(case_id),
                                "key": str(key),
                                "response_type": response_type,
                                "raw_len": len(raw_answer),
                                "shown": shown,
                            },
                        )
                        return shown

                    # Para C2/E2 y otros usos (autorrellenar), devolver la respuesta real
                    st.session_state[cache_key] = raw_answer
                    _dbg_log_wizard(
                        "H_UI_WIZ",
                        "app/ui/streamlit_mvp.py:_rag_recommend",
                        "rag_raw_used",
                        {
                            "case_id": str(case_id),
                            "key": str(key),
                            "response_type": response_type,
                            "raw_len": len(raw_answer),
                        },
                    )
                    return raw_answer
                except Exception as e:
                    st.session_state[cache_key] = None
                    # UX: no mostrar el error crudo al usuario final (se registra en logs si aplica).
                    return "(RAG no disponible)"

            def _save_wizard_fs() -> None:
                try:
                    paths.get("inputs_wizard_answers", paths["inputs_dir"] / "wizard_answers.json").write_text(
                        json.dumps({"wizard_id": wizard_def.get("wizard_id"), "answers": wizard_state}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception as e:
                    st.error(f"No se pudo guardar wizard.json: {e}")

            def _apply_wizard_into_overrides(cur: dict[str, Any]) -> dict[str, Any]:
                out = dict(cur or {})
                # Map wizard answers into known field_ids used by PDF mapping / template values
                if wizard_state.get("C1") in ("actual", "inminente"):
                    out["insolvency.kind"] = wizard_state.get("C1")
                if isinstance(wizard_state.get("C2"), str) and wizard_state.get("C2").strip():
                    out["insolvency.facts"] = wizard_state.get("C2").strip()[:500]
                if wizard_state.get("C3") in ("si", "no"):
                    out["company.ceased_activity"] = wizard_state.get("C3")
                try:
                    out["workers.count"] = int(wizard_state.get("C4") or 0)
                except Exception:
                    pass
                for k_src, k_dst in (
                    ("C5", "totals.asset_value"),
                    ("C6", "totals.cash"),
                    ("C7", "totals.passive_amount"),
                ):
                    try:
                        out[k_dst] = float(wizard_state.get(k_src) or 0.0)
                    except Exception:
                        pass
                try:
                    out["totals.creditors_count"] = int(wizard_state.get("C8") or 0)
                except Exception:
                    pass
                if wizard_state.get("D"):
                    out["solution.type"] = wizard_state.get("D")
                if wizard_state.get("E1") in ("si", "no"):
                    out["insufficiency.requested"] = wizard_state.get("E1")
                if isinstance(wizard_state.get("E2"), str) and wizard_state.get("E2").strip():
                    out["insufficiency.justification"] = wizard_state.get("E2").strip()[:500]
                return out

            def _wiz_title(text: str) -> None:
                # Título grande y en negrita, con poco margen para mantenerlo pegado al widget.
                st.markdown(
                    f'<div style="font-size:1.15rem; font-weight:800; margin:0.35rem 0 0.10rem 0;">{text}</div>',
                    unsafe_allow_html=True,
                )

            # A7
            _wiz_title("A7) Modificación del domicilio social (últimos 6 meses)")
            a7 = st.radio(
                "A7",
                options=["si", "no"],
                index=(0 if wizard_state.get("A7") == "si" else 1) if wizard_state.get("A7") in ("si", "no") else 1,
                key=f"wiz_A7__{case_id}",
                horizontal=True,
                label_visibility="collapsed",
            )
            wizard_state["A7"] = a7
            a7_rec = _rag_recommend(
                "A7",
                "Recomienda SI/NO para: ¿Modificación del domicilio social en los últimos 6 meses? "
                "Responde muy breve y sin conclusiones legales, indicando qué revisar.",
            )
            if a7_rec:
                # Reducir espacio vertical para que la nota quede “pegada” al radio
                st.markdown(
                    f'<div style="color:#b00020; margin-top:-0.75rem; line-height:1.2;">{a7_rec}</div>',
                    unsafe_allow_html=True,
                )
                _dbg_log_wizard(
                    "H_UI_WIZ",
                    "app/ui/streamlit_mvp.py:wizard_render",
                    "rendered_wizard_note",
                    {"case_id": str(case_id), "key": "A7", "shown": str(a7_rec)},
                )

            # B
            _wiz_title("B) Representación procesal · Apoderamiento")
            b = st.radio(
                "B",
                options=["previamente_otorgado", "apud_acta"],
                index=0 if wizard_state.get("B") == "previamente_otorgado" else 1 if wizard_state.get("B") == "apud_acta" else 0,
                key=f"wiz_B__{case_id}",
                horizontal=True,
                label_visibility="collapsed",
            )
            wizard_state["B"] = b
            b_rec = _rag_recommend(
                "B",
                "Recomienda opción para representación procesal (previamente_otorgado vs apud_acta). "
                "Responde breve, basado en documentación del caso, e indica qué documento lo soporta.",
            )
            if b_rec:
                st.markdown(
                    f'<div style="color:#b00020; margin-top:-0.75rem; line-height:1.2;">{b_rec}</div>',
                    unsafe_allow_html=True,
                )
                _dbg_log_wizard(
                    "H_UI_WIZ",
                    "app/ui/streamlit_mvp.py:wizard_render",
                    "rendered_wizard_note",
                    {"case_id": str(case_id), "key": "B", "shown": str(b_rec)},
                )

            # C
            _wiz_title("C1) Clase de insolvencia")
            c1 = st.radio(
                "C1",
                options=["actual", "inminente"],
                index=0 if wizard_state.get("C1") == "actual" else 1 if wizard_state.get("C1") == "inminente" else 0,
                key=f"wiz_C1__{case_id}",
                horizontal=True,
                label_visibility="collapsed",
            )
            wizard_state["C1"] = c1
            c_rec = _rag_recommend(
                "C1",
                "Según la documentación del caso, ¿la insolvencia parece ACTUAL o INMINENTE? "
                "Responde breve y sin conclusiones, solo describe indicios y qué falta por confirmar.",
            )
            if c_rec:
                st.markdown(
                    f'<div style="color:#b00020; margin-top:-0.75rem; line-height:1.2;">{c_rec}</div>',
                    unsafe_allow_html=True,
                )
                _dbg_log_wizard(
                    "H_UI_WIZ",
                    "app/ui/streamlit_mvp.py:wizard_render",
                    "rendered_wizard_note",
                    {"case_id": str(case_id), "key": "C1", "shown": str(c_rec)},
                )

            # Prefill on next rerun (Streamlit forbids mutating widget-key session_state after instantiation)
            _prefill_c2_key = f"juzgado_prefill_C2__{case_id}"
            if _prefill_c2_key in st.session_state:
                _dbg_log_wizard(
                    "H_UI_WIZ_C2",
                    "app/ui/streamlit_mvp.py:wizard_C2",
                    "prefill_key_present",
                    {
                        "case_id": str(case_id),
                        "prefill_len": len(str(st.session_state.get(_prefill_c2_key) or "")),
                    },
                )
                try:
                    wizard_state["C2"] = str(st.session_state.get(_prefill_c2_key) or "")[:500]
                except Exception:
                    wizard_state["C2"] = ""
                try:
                    del st.session_state[_prefill_c2_key]
                except Exception:
                    pass

            _wiz_title("C2) Hechos de los que deriva la insolvencia (máx 500)")
            _c2_widget_key = f"wiz_C2__{case_id}"
            _c2_default = str(wizard_state.get("C2") or "")
            # FIX_C2_INDENT (agent): evitar bloque if/else colgando por sangría
            # Evitar warning de Streamlit: si el widget key ya existe en session_state, no pasar 'value='.
            if _c2_widget_key in st.session_state:
                _dbg_log_wizard(
                    "H_UI_WIZ_C2",
                    "app/ui/streamlit_mvp.py:wizard_C2",
                    "c2_widget_key_exists",
                    {"case_id": str(case_id), "key": _c2_widget_key, "default_len": len(_c2_default)},
                )
                c2 = st.text_area(
                    "C2",
                    max_chars=500,
                    key=_c2_widget_key,
                    label_visibility="collapsed",
                )
            else:
                _dbg_log_wizard(
                    "H_UI_WIZ_C2",
                    "app/ui/streamlit_mvp.py:wizard_C2",
                    "c2_widget_key_missing",
                    {"case_id": str(case_id), "key": _c2_widget_key, "default_len": len(_c2_default)},
                )
                c2 = st.text_area(
                    "C2",
                    value=_c2_default,
                    max_chars=500,
                    key=_c2_widget_key,
                    label_visibility="collapsed",
                )
            wizard_state["C2"] = c2
            if st.button("⚡ Generar (IA)", key=f"wiz_C2_fill__{case_id}"):
                _dbg_log_wizard(
                    "H_UI_WIZ_C2",
                    "app/ui/streamlit_mvp.py:wizard_C2",
                    "fill_button_clicked",
                    {
                        "case_id": str(case_id),
                        "c2_current_len": len(str(wizard_state.get("C2") or "")),
                    },
                )
                rec = _rag_recommend(
                    "C2",
                    "Redacta en español un texto (máx 500 caracteres) de hechos que derivan la insolvencia, "
                    "basado solo en la documentación del caso. Sin conclusiones legales.",
                )
                _dbg_log_wizard(
                    "H_UI_WIZ_C2",
                    "app/ui/streamlit_mvp.py:wizard_C2",
                    "fill_rag_returned",
                    {
                        "case_id": str(case_id),
                        "rec_is_none": rec is None,
                        "rec_len": len(str(rec or "")),
                    },
                )
                if rec:
                    st.session_state[_prefill_c2_key] = rec[:500]
                    _dbg_log_wizard(
                        "H_UI_WIZ_C2",
                        "app/ui/streamlit_mvp.py:wizard_C2",
                        "prefill_key_set",
                        {"case_id": str(case_id), "prefill_len": len(str(rec[:500]))},
                    )
                    st.rerun()

            _wiz_title("C3) ¿Ha cesado su actividad?")
            c3 = st.radio(
                "C3",
                options=["si", "no"],
                index=0 if wizard_state.get("C3") == "si" else 1 if wizard_state.get("C3") == "no" else 1,
                key=f"wiz_C3__{case_id}",
                horizontal=True,
                label_visibility="collapsed",
            )
            wizard_state["C3"] = c3

            _wiz_title("C4) Nº trabajadores")
            c4 = st.number_input(
                "C4",
                min_value=0,
                value=int(wizard_state.get("C4") or 0),
                step=1,
                key=f"wiz_C4__{case_id}",
                label_visibility="collapsed",
            )
            wizard_state["C4"] = int(c4)

            _wiz_title("C5) Valoración activo (EUR)")
            c5 = st.number_input(
                "C5",
                min_value=0.0,
                value=float(wizard_state.get("C5") or 0.0),
                step=100.0,
                key=f"wiz_C5__{case_id}",
                label_visibility="collapsed",
            )
            wizard_state["C5"] = float(c5)

            _wiz_title("C6) Tesorería (EUR)")
            c6 = st.number_input(
                "C6",
                min_value=0.0,
                value=float(wizard_state.get("C6") or 0.0),
                step=100.0,
                key=f"wiz_C6__{case_id}",
                label_visibility="collapsed",
            )
            wizard_state["C6"] = float(c6)

            _wiz_title("C7) Cuantía pasivo (EUR)")
            c7 = st.number_input(
                "C7",
                min_value=0.0,
                value=float(wizard_state.get("C7") or 0.0),
                step=100.0,
                key=f"wiz_C7__{case_id}",
                label_visibility="collapsed",
            )
            wizard_state["C7"] = float(c7)

            _wiz_title("C8) Nº acreedores")
            c8 = st.number_input(
                "C8",
                min_value=0,
                value=int(wizard_state.get("C8") or 0),
                step=1,
                key=f"wiz_C8__{case_id}",
                label_visibility="collapsed",
            )
            wizard_state["C8"] = int(c8)

            # D
            _wiz_title("D) Solución del concurso")
            d = st.radio(
                "D",
                options=[
                    "propuesta_anticipada_convenio",
                    "convenio",
                    "liquidacion",
                    "plan_liquidacion_con_propuesta_vinculante_unidad_productiva",
                ],
                index=0,
                key=f"wiz_D__{case_id}",
                label_visibility="collapsed",
            )
            wizard_state["D"] = d
            d_rec = _rag_recommend(
                "D",
                "Recomienda la opción de solución del concurso (convenio/liquidación/otros) según documentación del caso. "
                "Responde breve y prudente; indica incertidumbres.",
            )
            if d_rec:
                st.markdown(
                    f'<div style="color:#b00020; margin-top:-0.75rem; line-height:1.2;">{d_rec}</div>',
                    unsafe_allow_html=True,
                )
                _dbg_log_wizard(
                    "H_UI_WIZ",
                    "app/ui/streamlit_mvp.py:wizard_render",
                    "rendered_wizard_note",
                    {"case_id": str(case_id), "key": "D", "shown": str(d_rec)},
                )

            # E
            _wiz_title("E1) ¿Se solicita insuficiencia de masa activa?")
            e1 = st.radio(
                "E1",
                options=["si", "no"],
                index=0 if wizard_state.get("E1") == "si" else 1 if wizard_state.get("E1") == "no" else 1,
                key=f"wiz_E1__{case_id}",
                horizontal=True,
                label_visibility="collapsed",
            )
            wizard_state["E1"] = e1
            _prefill_e2_key = f"juzgado_prefill_E2__{case_id}"
            if _prefill_e2_key in st.session_state:
                try:
                    wizard_state["E2"] = str(st.session_state.get(_prefill_e2_key) or "")[:500]
                except Exception:
                    wizard_state["E2"] = ""
                try:
                    del st.session_state[_prefill_e2_key]
                except Exception:
                    pass

            _wiz_title("E2) Justificación (si aplica, máx 500)")
            e2 = st.text_area(
                "E2",
                value=str(wizard_state.get("E2") or ""),
                max_chars=500,
                key=f"wiz_E2__{case_id}",
                label_visibility="collapsed",
            )
            wizard_state["E2"] = e2
            if st.button("⚡ Generar (IA)", key=f"wiz_E2_fill__{case_id}"):
                rec = _rag_recommend(
                    "E2",
                    "Redacta una justificación (máx 500 caracteres) para solicitud de insuficiencia de masa activa "
                    "basada solo en documentación del caso. Sin conclusiones legales.",
                )
                if rec:
                    st.session_state[_prefill_e2_key] = rec[:500]
                    st.rerun()

            # F (checkbox group)
            _wiz_title("F) Documentación (marca lo que acompañará a la solicitud)")
            st.caption("Al pulsar **💾 Guardar y generar documentos** se crearán los ficheros de los ítems marcados y aparecerán abajo en **Documentación Solicitada**.")
            f_items = wizard_def.get("sections", [])[-2].get("items", []) if isinstance(wizard_def.get("sections"), list) else []
            selected_f: list[str] = []
            for it in f_items:
                if not isinstance(it, dict):
                    continue
                _id = it.get("id")
                _lbl = it.get("label")
                if not _id or not _lbl:
                    continue
                checked = bool(wizard_state.get(f"F::{_id}", False))
                new_checked = st.checkbox(str(_lbl), value=checked, key=f"wiz_F__{case_id}__{_id}")
                wizard_state[f"F::{_id}"] = bool(new_checked)
                if new_checked:
                    selected_f.append(str(_id))

            # Guardar wizard
            if st.button("💾 Guardar y generar documentos", key=f"wiz_save__{case_id}"):
                try:
                    _dbg_log_tab9(
                        "H_WIZ_SAVE",
                        "app/ui/streamlit_mvp.py:wiz_save",
                        "clicked",
                        {"case_id": str(case_id), "selected_f": list(selected_f), "count": len(selected_f)},
                    )
                except Exception:
                    pass
                _save_wizard_fs()
                try:
                    merged = _apply_wizard_into_overrides(current_overrides)
                    # Persistir selección F (doc*) en overrides para que el PDF marque los checkboxes
                    try:
                        # Normalizar: poner True a los marcados; poner False a los no marcados (solo para los que existan en wizard_def)
                        all_doc_ids = [str(it.get("id")) for it in (f_items or []) if isinstance(it, dict) and it.get("id")]
                        selected_set = set(selected_f or [])
                        for did in all_doc_ids:
                            merged[did] = bool(did in selected_set)
                    except Exception:
                        pass
                    paths["inputs_formulario_overrides"].write_text(
                        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                except Exception as e:
                    st.error(f"No se pudo aplicar wizard a overrides: {e}")

                # Regenerar solicitud para reflejar cambios del wizard
                if state is not None:
                    try:
                        _ = pdf_form_filler.generate_document_0(case_root, state, user_id="ui")
                    except Exception as e:
                        st.error(f"Error regenerando la solicitud: {e}")

                # -------------------------------------------------
                # Auto-generar adjuntos reales según F (doc2/doc3/doc4/...) al guardar
                # Objetivo: que aparezcan automáticamente en "Documentación Solicitada"
                # con 👁️ (vista previa bajo demanda) y 🗑️ (eliminar).
                # -------------------------------------------------
                try:
                    _dbg_log_tab9(
                        "H_F_DOCS",
                        "app/ui/streamlit_mvp.py:wiz_save",
                        "wizard_f_selected",
                        {"case_id": str(case_id), "selected_f": list(selected_f), "count": len(selected_f)},
                    )
                except Exception:
                    pass

                def _remove_existing_by_doc_key(doc_key: str) -> None:
                    try:
                        att_dir = paths["attachments_dir"]
                        for p in list(att_dir.glob(f"*__{doc_key}__*")):
                            try:
                                p.unlink()
                            except Exception:
                                pass
                    except Exception:
                        pass

                def _add_attachment_generated(*, doc_key: str, filename: str, content: bytes, kind: str = "otro") -> None:
                    _remove_existing_by_doc_key(doc_key)
                    try:
                        _ = court_pack_service.add_attachment(
                            case_root,
                            content,
                            filename=f"{doc_key}__{filename}",
                            kind=kind,
                        )
                    except Exception:
                        # fallback raw write (sin state)
                        try:
                            out = paths["attachments_dir"] / f"{doc_key}__{filename}"
                            out.write_bytes(content)
                        except Exception:
                            pass

                def _autogen_from_wizard_f(ids: list[str]) -> None:
                    # Solo en modo API (si el caso es ruta absoluta, no podemos llamar a backend)
                    try:
                        raw_sel = str(st.session_state.get("selected_case_id") or "")
                        if Path(raw_sel).is_absolute():
                            return
                    except Exception:
                        pass

                    try:
                        api = get_api_client()
                    except Exception:
                        api = None
                    if api is None:
                        return

                    results: list[dict[str, Any]] = []

                    for doc_id in ids:
                        try:
                            # Memoria económica y jurídica → PDF informe económico cliente (si existe)
                            if doc_id == "doc2_memoria_economica_y_juridica":
                                pdf_bytes = b""
                                try:
                                    pdf_bytes = api.download_economic_report_pdf(str(case_id), audience="client")
                                except Exception:
                                    pdf_bytes = api.download_economic_report_pdf(str(case_id), audience="internal")
                                if pdf_bytes:
                                    _add_attachment_generated(
                                        doc_key="memoria",
                                        filename="memoria_economica_y_juridica.pdf",
                                        content=pdf_bytes,
                                        kind="otro",
                                    )
                                    results.append({"doc_id": doc_id, "ok": True, "bytes": len(pdf_bytes)})
                                else:
                                    results.append({"doc_id": doc_id, "ok": False, "err": "empty_pdf"})
                                continue

                            # Inventario bienes y derechos → Excel (bienes)
                            if doc_id == "doc3_inventario_bienes_y_derechos":
                                xls = api.download_situation_assets_excel(str(case_id))
                                if xls:
                                    _add_attachment_generated(
                                        doc_key="inventario",
                                        filename="inventario_bienes_y_derechos.xlsx",
                                        content=xls,
                                        kind="otro",
                                    )
                                    results.append({"doc_id": doc_id, "ok": True, "bytes": len(xls)})
                                else:
                                    results.append({"doc_id": doc_id, "ok": False, "err": "empty_xlsx"})
                                continue

                            # Relación de acreedores → CSV (desde editables.debts; fallback a Excel export)
                            if doc_id == "doc4_relacion_de_acreedores":
                                try:
                                    edit = api.get_economic_report_editables(str(case_id)) or {}
                                except Exception:
                                    edit = {}
                                debts = (edit or {}).get("debts") or []
                                rows: list[str] = ["creditor_name,creditor_type,amount_eur,trlc_bucket"]
                                if isinstance(debts, list):
                                    for d in debts:
                                        if not isinstance(d, dict):
                                            continue
                                        name = str(d.get("creditor_name") or "").replace(",", " ").strip()
                                        ctype = str(d.get("creditor_type") or "").replace(",", " ").strip()
                                        amt = d.get("amount_eur")
                                        bucket = str(d.get("proposed_trlc_bucket") or "").replace(",", " ").strip()
                                        rows.append(f"{name},{ctype},{amt if isinstance(amt,(int,float)) else ''},{bucket}")
                                csv_bytes = ("\n".join(rows) + "\n").encode("utf-8")
                                _add_attachment_generated(
                                    doc_key="acreedores",
                                    filename="relacion_acreedores.csv",
                                    content=csv_bytes,
                                    kind="otro",
                                )
                                results.append({"doc_id": doc_id, "ok": True, "bytes": len(csv_bytes), "rows": len(rows) - 1})
                                continue

                            # Plantilla trabajadores → TXT (desde overrides/workers.count)
                            if doc_id == "doc5_plantilla_de_trabajadores":
                                try:
                                    over = json.loads(paths["inputs_formulario_overrides"].read_text(encoding="utf-8") or "{}")
                                except Exception:
                                    over = {}
                                wc = over.get("workers.count")
                                txt = f"Nº trabajadores (estimación): {wc if isinstance(wc,(int,float)) else 'NO CONSTA'}\n"
                                _add_attachment_generated(
                                    doc_key="trabajadores",
                                    filename="plantilla_trabajadores.txt",
                                    content=txt.encode("utf-8"),
                                    kind="otro",
                                )
                                results.append({"doc_id": doc_id, "ok": True, "bytes": len(txt)})
                                continue

                            # Cuentas anuales → Excel export (todo)
                            if doc_id in ("doc61_cuentas_anuales_individuales", "doc62_cuentas_anuales_consolidadas"):
                                xls = api.download_situation_export_excel(str(case_id))
                                if xls:
                                    _add_attachment_generated(
                                        doc_key="cuentas",
                                        filename="export_situacion.xlsx",
                                        content=xls,
                                        kind="cuentas_anuales",
                                    )
                                    results.append({"doc_id": doc_id, "ok": True, "bytes": len(xls)})
                                else:
                                    results.append({"doc_id": doc_id, "ok": False, "err": "empty_xlsx"})
                                continue

                            # Poder especial → placeholder (no sabemos cuál; queda para adjuntar manual)
                            if doc_id == "doc1_poder_especial":
                                results.append({"doc_id": doc_id, "ok": False, "err": "manual_required"})
                                continue

                            # Default: no-op (queda para adjuntar manual / borrador)
                            results.append({"doc_id": doc_id, "ok": False, "err": "not_mapped"})
                        except Exception as e:
                            results.append({"doc_id": doc_id, "ok": False, "err": str(type(e).__name__)})

                    try:
                        _dbg_log_tab9(
                            "H_F_DOCS",
                            "app/ui/streamlit_mvp.py:wiz_save",
                            "wizard_f_autogen_results",
                            {"case_id": str(case_id), "results": results[:30], "count": len(results)},
                        )
                    except Exception:
                        pass

                try:
                    _autogen_from_wizard_f(list(selected_f))
                except Exception:
                    pass
                try:
                    att_files = []
                    for p in sorted(paths["attachments_dir"].rglob("*")):
                        if p.is_file():
                            att_files.append({"name": p.name, "size": int(p.stat().st_size)})
                    _dbg_log_tab9(
                        "H_WIZ_SAVE",
                        "app/ui/streamlit_mvp.py:wiz_save",
                        "attachments_snapshot",
                        {"case_id": str(case_id), "count": len(att_files), "files": att_files[:20]},
                    )
                except Exception:
                    pass

                st.success("✅ Wizard guardado")
                # Trigger autorun in docs panel (best-effort)
                st.session_state[f"juzgado_docs_autorun__{case_id}"] = True
                st.rerun()

            # UX: eliminado el editor genérico de campos (`debtor.*`, `insolvency.*`, `totals.*`)
            # porque mostraba una pantalla técnica con muchas “cajas” debajo del wizard.
            # El wizard y el guardado siguen siendo el flujo de edición.

        if st.session_state.get("juzgado_attach_panel", False):
            st.markdown("### 📎 Documentación del expediente")

            attach_dir = paths["attachments_dir"]
            gen_dir = paths["generated_dir"]

            # Document source folder (filesystem-only)
            docs_dir = None
            for cand in (case_root / "documents", case_root / "documentos"):
                try:
                    if cand.exists() and cand.is_dir():
                        docs_dir = cand
                        break
                except Exception:
                    continue
            if docs_dir is None:
                st.warning("No existe carpeta `documents/` (ni `documentos/`) en este caso. No se puede buscar/adjuntar automáticamente.")
                # En modo case_id (API), podemos crearla e importar los originales desde la BD.
                try:
                    raw_sel = str(st.session_state.get("selected_case_id") or "")
                    is_abs = Path(raw_sel).is_absolute()
                except Exception:
                    is_abs = False
                if not is_abs:
                    if st.button("📥 Importar documentos del caso (API → documents/)", key=f"juzgado_import_docs__{case_id}"):
                        try:
                            client = get_api_client()
                            docs_dir = case_root / "documents"
                            docs_dir.mkdir(parents=True, exist_ok=True)
                            items = client.list_documents(str(case_id))
                            imported = 0
                            for it in items[:500]:
                                doc_id = it.get("document_id")
                                fn = it.get("filename") or f"{doc_id}.bin"
                                if not doc_id:
                                    continue
                                try:
                                    b = client.download_document_original_bytes(str(case_id), str(doc_id))
                                    out = docs_dir / str(fn)
                                    out.write_bytes(b)
                                    imported += 1
                                except Exception as e:
                                    continue
                            st.success(f"✅ Importados {imported} documentos en `{docs_dir}`")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error importando documentos: {e}")
            else:
                st.caption(f"Origen búsqueda: `{docs_dir}`")

            def _active_for(doc_key: str) -> Optional[Path]:
                # Convención fija (sin heurística): <tipo>_<original_filename>
                # Soportar:
                # - legacy: {doc_key}_*
                # - add_attachment: {sha}__{doc_key}__*
                matches = sorted(list(attach_dir.glob(f"{doc_key}_*")))
                matches += sorted(list(attach_dir.glob(f"*__{doc_key}__*")))
                return matches[0] if matches else None

            def _find_candidates(keywords_any: list[str]) -> list[Path]:
                if docs_dir is None:
                    return []
                out: list[Path] = []
                for p in sorted(docs_dir.iterdir()):
                    if not p.is_file():
                        continue
                    name = p.name.lower()
                    if any((kw or "").lower() in name for kw in (keywords_any or [])):
                        out.append(p)
                return out

            def _attach_from_path(doc_key: str, src: Path) -> None:
                # replace previous (best-effort, filesystem-only)
                for old in list(attach_dir.glob(f"{doc_key}_*")) + list(attach_dir.glob(f"*__{doc_key}__*")):
                    try:
                        old.unlink()
                    except Exception:
                        pass
                # Use service add_attachment so state.json can track it when available
                try:
                    _ = court_pack_service.add_attachment(
                        case_root,
                        src.read_bytes(),
                        filename=f"{doc_key}__{src.name}",
                        kind="otro",
                    )
                except Exception:
                    # Fallback: raw copy
                    out = attach_dir / f"{doc_key}_{src.name}"
                    out.write_bytes(src.read_bytes())

            def _draft_path(doc_key: str) -> Path:
                return gen_dir / f"{doc_key}.md"

            def _load_case_profile_text() -> str:
                try:
                    p = paths["inputs_dir"] / "case_profile.json"
                    if not p.exists():
                        # Try to create snapshot from DB when running with case_id mode
                        try:
                            raw_sel = str(st.session_state.get("selected_case_id") or "")
                            if not Path(raw_sel).is_absolute():
                                client = get_api_client()
                                _ = client.snapshot_court_case_profile(str(case_id))
                        except Exception:
                            pass
                    if p.exists():
                        return p.read_text(encoding="utf-8")[:20000]
                except Exception:
                    pass
                return ""

            def _load_client_report_text() -> str:
                # Prefer reports/latest.txt (if exists) → PDF filename
                try:
                    reports_dir = case_root / "reports"
                    latest = reports_dir / "latest.txt"
                    if not latest.exists():
                        return ""
                    pdf_name = (latest.read_text(encoding="utf-8") or "").strip()
                    if not pdf_name:
                        return ""
                    pdf_path = reports_dir / pdf_name
                    if not pdf_path.exists():
                        return ""
                    try:
                        from pypdf import PdfReader

                        r = PdfReader(str(pdf_path))
                        chunks = []
                        for page in r.pages[:25]:
                            try:
                                chunks.append(page.extract_text() or "")
                            except Exception:
                                continue
                        return "\n\n".join(chunks)[:30000]
                    except Exception:
                        return ""
                except Exception:
                    return ""

            def _llm_draft(*, title: str, context_text: str, instructions: str, max_chars: int = 4000) -> str:
                try:
                    from app.services.llm_executor import execute_llm
                except Exception:
                    return f"# {title}\n\n(V1) No disponible: llm_executor.\n"

                sys = (
                    "Eres un asistente para redactar documentación concursal. "
                    "No inventes datos. Si falta información, deja un placeholder claro [PENDIENTE] y enumera qué falta.\n"
                    "No incluyas conclusiones legales ni asesoramiento; solo redacción factual y checklist."
                )
                user = (
                    f"CONTEXTO DISPONIBLE (única fuente):\n{context_text}\n\n"
                    f"---\n"
                    f"TAREA: redacta un borrador para: {title}\n"
                    f"INSTRUCCIONES:\n{instructions}\n"
                    f"Salida: Markdown.\n"
                )
                res = execute_llm(
                    task_name="courtpack_doc_draft",
                    prompt_system=sys,
                    prompt_user=user,
                    max_tokens=800,
                    timeout_seconds=20,
                )
                txt = res.output_text or ""
                if not txt.strip():
                    return f"# {title}\n\n[PENDIENTE] No se pudo generar borrador automáticamente.\n"
                return txt.strip()[:max_chars]

            def _rag_draft(*, question: str) -> Optional[str]:
                # Only if we have a real API case_id (not absolute-path mode)
                try:
                    raw_sel = str(st.session_state.get("selected_case_id") or "")
                    if Path(raw_sel).is_absolute():
                        return None
                except Exception:
                    pass
                try:
                    client = get_api_client()
                except Exception:
                    return None
                try:
                    resp = client.rag_ask(str(case_id), question, top_k=10)
                    ans = str(resp.get("answer") or "").strip()
                    # If RAG indicates insufficient evidence, treat as no-answer
                    if "No hay evidencia suficiente" in ans:
                        return None
                    return ans
                except Exception:
                    return None

            def _generate_doc_content(doc_key: str, title: str) -> str:
                # Priority: RAG → client report pdf (only for creditors) → DB/wizard via direct LLM
                wiz_json = ""
                try:
                    wiz_json = paths.get("inputs_wizard_answers", paths["inputs_dir"] / "wizard_answers.json").read_text(encoding="utf-8")[:10000]
                except Exception:
                    wiz_json = ""
                profile_txt = _load_case_profile_text()
                # Add DB structured KPIs (situation_*) when available
                kpis_txt = ""
                try:
                    raw_sel = str(st.session_state.get("selected_case_id") or "")
                    if not Path(raw_sel).is_absolute():
                        client = get_api_client()
                        kpis = client.get_situation_kpis(str(case_id))
                        kpis_txt = json.dumps(kpis, ensure_ascii=False, indent=2)[:15000]
                except Exception:
                    kpis_txt = ""

                if doc_key.startswith("acreedores"):
                    # Prefer client report PDF context if exists
                    rep = _load_client_report_text()
                    if rep.strip():
                        return _llm_draft(
                            title=title,
                            context_text=rep,
                            instructions="Extrae y lista acreedores (nombre, importe si aparece, tipo) en formato tabla. "
                            "Si no se ve, deja [PENDIENTE].",
                        )

                rag_q = (
                    f"Redacta un borrador breve y estructurado de: {title}. "
                    "Usa solo evidencia del caso. Si faltan datos, marca [PENDIENTE]. "
                    "Salida en Markdown."
                )
                rag_txt = _rag_draft(question=rag_q)
                if rag_txt:
                    return rag_txt

                # DB+IA fallback: use wizard answers + case_profile snapshot if available
                ctx = "\n\n".join([x for x in [profile_txt, kpis_txt, wiz_json] if x.strip()])
                if not ctx.strip():
                    ctx = "(Sin contexto estructurado disponible en el caso.)"
                return _llm_draft(
                    title=title,
                    context_text=ctx,
                    instructions="Genera un borrador coherente con el contexto y el wizard. "
                    "No inventes cifras; usa [PENDIENTE] si no están.",
                )

            # Base docs (siempre listados)
            base_docs = [
                {"doc_key": "memoria", "title": "📄 Memoria económica y jurídica", "keywords": ["memoria"]},
                {"doc_key": "inventario", "title": "📄 Inventario de bienes y derechos", "keywords": ["inventario"]},
                {"doc_key": "acreedores", "title": "📄 Relación de acreedores", "keywords": ["acreedor"]},
                {"doc_key": "cuentas", "title": "📄 Cuentas anuales", "keywords": ["cuentas"]},
                {"doc_key": "trabajadores", "title": "📄 Plantilla de trabajadores", "keywords": ["trabajador"]},
            ]

            # Extras: los marcados por el abogado en F (wizard)
            wiz_state = st.session_state.get(f"juzgado_wizard_state__{case_id}", {}) or {}
            extras_ids = [k.split("F::", 1)[1] for k, v in wiz_state.items() if k.startswith("F::") and v]
            # Build extras dynamically from wizard definition (id+label)
            extra_docs = []
            try:
                wdef = json.loads(paths["inputs_wizard"].read_text(encoding="utf-8") or "{}")
            except Exception:
                wdef = {}
            f_items = []
            if isinstance(wdef, dict):
                for sec in wdef.get("sections") or []:
                    if isinstance(sec, dict) and sec.get("id") == "F" and isinstance(sec.get("items"), list):
                        f_items = sec.get("items") or []
                        break
            label_by_id = {it.get("id"): it.get("label") for it in f_items if isinstance(it, dict)}
            for eid in extras_ids:
                lbl = label_by_id.get(eid) or eid
                # keywords from label words (rough but deterministic)
                kws = [w.lower() for w in str(lbl).replace("·", " ").replace("/", " ").split() if len(w) >= 4][:6]
                if not kws:
                    kws = [eid.replace("doc", "").lower()]
                extra_docs.append({"doc_key": f"extra_{eid}", "title": f"📄 {lbl}", "keywords": kws})

            docs_all = base_docs + extra_docs

            attached = sum(1 for d in docs_all if _active_for(d["doc_key"]) is not None)
            st.write(f"Progreso documentación: {attached}/{len(docs_all)}")
            st.progress(attached / max(1, len(docs_all)))

            st.caption("✔️ Se generan UNO A UNO · ✔️ Cada documento es independiente · ✔️ Exactamente como lo espera el juzgado")

            for d in docs_all:
                doc_key = d["doc_key"]
                title = d["title"]
                active = _active_for(doc_key)
                draft = _draft_path(doc_key)

                st.write(title)
                if active is not None:
                    st.write("✅ Adjuntado")
                elif draft.exists():
                    st.write("📝 Borrador generado (editable)")
                else:
                    st.write("⚠️ Pendiente")

                c1, c2, c3 = st.columns([2, 1, 1])
                with c1:
                    if active is None and not draft.exists():
                        cands = _find_candidates(d["keywords"])
                        if cands:
                            opt = st.selectbox(
                                "Encontrado en documents/",
                                options=[str(p) for p in cands],
                                key=f"juzgado_doc_pick__{case_id}__{doc_key}",
                            )
                            if st.button("📎 Adjuntar", key=f"juzgado_doc_attach__{case_id}__{doc_key}"):
                                try:
                                    _attach_from_path(doc_key, Path(opt))
                                    st.success("✅ Adjuntado.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error adjuntando: {e}")
                        else:
                            st.warning("No encontrado en documents/.")
                            if st.button("📝 Crear borrador", key=f"juzgado_doc_draft__{case_id}__{doc_key}"):
                                try:
                                    content = _generate_doc_content(doc_key, title)
                                    draft.write_text(content, encoding="utf-8")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error creando borrador: {e}")

                # Autorun: tras Guardar wizard, intenta adjuntar/generar 1-a-1 automáticamente
                if st.session_state.get(f"juzgado_docs_autorun__{case_id}", False):
                    try:
                        if active is None and not draft.exists():
                            cands = _find_candidates(d["keywords"])
                            if len(cands) == 1:
                                _attach_from_path(doc_key, cands[0])
                            elif len(cands) == 0:
                                draft.write_text(_generate_doc_content(doc_key, title), encoding="utf-8")
                            else:
                                pass
                    except Exception as e:
                        pass
            if st.session_state.get(f"juzgado_docs_autorun__{case_id}", False):
                st.session_state[f"juzgado_docs_autorun__{case_id}"] = False
                st.rerun()
                with c2:
                    if active is not None:
                        try:
                            st.download_button(
                                "⬇️ Descargar",
                                data=active.read_bytes(),
                                file_name=active.name,
                                mime="application/octet-stream",
                                key=f"juzgado_doc_dl__{case_id}__{doc_key}",
                            )
                        except Exception:
                            pass
                with c3:
                    if draft.exists():
                        if st.button("👁️ Revisar", key=f"juzgado_doc_review__{case_id}__{doc_key}"):
                            st.session_state[f"juzgado_doc_open__{case_id}__{doc_key}"] = True

                if st.session_state.get(f"juzgado_doc_open__{case_id}__{doc_key}", False) and draft.exists():
                    txt = draft.read_text(encoding="utf-8")
                    new_txt = st.text_area(
                        "Editar borrador",
                        value=txt,
                        height=220,
                        key=f"juzgado_doc_edit__{case_id}__{doc_key}",
                    )
                    bsave, bcancel = st.columns([1, 1])
                    with bsave:
                        if st.button("✅ Guardar", key=f"juzgado_doc_save__{case_id}__{doc_key}"):
                            draft.write_text(new_txt, encoding="utf-8")
                            st.success("✅ Guardado.")
                            st.session_state[f"juzgado_doc_open__{case_id}__{doc_key}"] = False
                            st.rerun()
                    with bcancel:
                        if st.button("Cerrar", key=f"juzgado_doc_close__{case_id}__{doc_key}"):
                            st.session_state[f"juzgado_doc_open__{case_id}__{doc_key}"] = False
                            st.rerun()

        # D) 3) Generar expediente (mostrado antes que el paso 2 por requerimiento de UI)
        st.markdown("###  Documentación Solicitada")
        # Lista de ficheros (adjuntos + generados) con visor bajo demanda.
        # (ZIP descargable eliminado por requerimiento de UI)
        items: list[dict[str, Any]] = []
        try:
            for p in sorted(paths["attachments_dir"].rglob("*")):
                if p.is_file():
                    items.append({"role": "attachment", "rel_path": str(p.relative_to(paths["court_pack"])), "size_bytes": p.stat().st_size})
            for p in sorted(paths["generated_dir"].rglob("*")):
                if p.is_file():
                    items.append({"role": "generated", "rel_path": str(p.relative_to(paths["court_pack"])), "size_bytes": p.stat().st_size})
        except Exception as e:
            st.error(f"Error listando documentación: {e}")

        st.session_state.setdefault(f"juzgado_doc_preview_rel__{case_id}", None)
        st.session_state.setdefault(f"juzgado_doc_preview_open__{case_id}", False)

        if items:
            # Render table-like list with view buttons
            for it in items:
                rel = str(it.get("rel_path") or "")
                role = str(it.get("role") or "")
                size_b = int(it.get("size_bytes") or 0)
                c1, c2, c3, c4 = st.columns([6, 1, 1, 1])
                with c1:
                    st.write(f"- `{rel}`  ({role}, {size_b} bytes)")
                with c2:
                    if st.button("👁️", key=f"juzgado_preview_btn__{case_id}__{rel}"):
                        st.session_state[f"juzgado_doc_preview_rel__{case_id}"] = rel
                        st.session_state[f"juzgado_doc_preview_open__{case_id}"] = True
                        st.rerun()
                with c3:
                    # Quick download
                    try:
                        fp = paths["court_pack"] / rel
                        if fp.exists():
                            st.download_button(
                                "⬇️",
                                data=fp.read_bytes(),
                                file_name=fp.name,
                                mime="application/octet-stream",
                                key=f"juzgado_preview_dl__{case_id}__{rel}",
                            )
                    except Exception:
                        pass
                with c4:
                    # Delete (attachments + generated)
                    if st.button("🗑️", key=f"juzgado_item_del__{case_id}__{rel}"):
                        try:
                            # if previewing this file, close it
                            if st.session_state.get(f"juzgado_doc_preview_rel__{case_id}") == rel:
                                st.session_state[f"juzgado_doc_preview_open__{case_id}"] = False

                            if role == "attachment" and rel.startswith("attachments/"):
                                try:
                                    basename = Path(rel).name
                                    attachment_id = basename.split("__", 1)[0] if "__" in basename else None
                                except Exception:
                                    attachment_id = None
                                if not attachment_id:
                                    st.error("No se pudo determinar attachment_id.")
                                else:
                                    court_pack_service.remove_attachment(case_root, attachment_id)
                                    st.rerun()
                            elif role == "generated" and rel.startswith("generated/"):
                                fp = (paths["court_pack"] / rel)
                                if fp.exists() and fp.is_file():
                                    fp.unlink()
                                st.rerun()
                            else:
                                st.error("No se puede borrar este elemento.")
                        except Exception as e:
                            st.error(f"Error borrando: {e}")

            # Inline preview below list (only when user clicks 👁️)
            if st.session_state.get(f"juzgado_doc_preview_open__{case_id}", False):
                rel = st.session_state.get(f"juzgado_doc_preview_rel__{case_id}")
                if rel:
                    fp = paths["court_pack"] / str(rel)
                    st.markdown("---")
                    st.write(f"**Vista previa:** `{rel}`")
                    if not fp.exists():
                        st.error("No se encontró el fichero en disco.")
                    else:
                        suffix = fp.suffix.lower()
                        try:
                            if suffix == ".pdf":
                                # Prefer URL via API (mejor que data: URIs para PDFs grandes)
                                url = None
                                try:
                                    api = get_api_client()
                                    url = api.court_pack_file_url(case_id=str(case_id), rel_path=str(rel))
                                except Exception:
                                    url = None
                                if url:
                                    components.html(
                                        f'<iframe src="{url}" width="100%" height="720" style="border:0;"></iframe>',
                                        height=740,
                                    )
                                else:
                                    st.info("Vista previa PDF no disponible. Usa descargar.")
                            elif suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                                st.image(fp.read_bytes())
                            elif suffix in (".txt", ".md", ".json", ".csv"):
                                st.text_area(
                                    "Contenido",
                                    value=fp.read_text(encoding="utf-8", errors="replace"),
                                    height=260,
                                )
                            else:
                                st.info("Previsualización no disponible para este tipo. Usa descargar.")
                        except Exception as e:
                            st.error(f"No se pudo previsualizar: {e}")
                if st.button("Cerrar vista previa", key=f"juzgado_preview_close__{case_id}"):
                    st.session_state[f"juzgado_doc_preview_open__{case_id}"] = False
                    st.rerun()
        else:
            st.info("Aún no hay ficheros en `attachments/` ni en `generated/`.")

        # C) 2) Adjuntar extras
        st.markdown("##### Adjuntar manual")
        st.session_state.setdefault("juzgado_attach_uploader_ver", 0)
        _uver = int(st.session_state.get("juzgado_attach_uploader_ver") or 0)
        up = st.file_uploader("Subir adjunto", key=f"juzgado_attach_uploader__{_uver}")
        if st.button("Guardar adjunto", width="stretch", key=f"juzgado_attach_save__{_uver}"):
            if not up:
                st.error("Falta archivo.")
            else:
                try:
                    _ = court_pack_service.add_attachment(case_root, up.getvalue(), up.name, "otro")
                    st.success("✅ Adjunto guardado.")
                    st.session_state["juzgado_attach_uploader_ver"] = _uver + 1
                    st.rerun()
                except Exception as e:
                    st.error(f"Error guardando adjunto: {e}")
        st.caption("Los adjuntos aparecen arriba en **Documentación Solicitada** (con 👁️ vista previa).")

        # E) 4) rellenar documento oficial
        st.markdown("### Rellenar documento oficial")
        # State-driven label/style based on the generated official PDF.
        doc0_out = paths["generated_dir"] / pdf_form_filler.OUTPUT_PDF_NAME
        doc0_exists = bool(doc0_out.exists())
        doc0_errors: Optional[int] = None
        try:
            st_check = court_pack_service.load_state(case_root)
            for d in st_check.documents:
                if d.doc_type == "doc0_formulario":
                    doc0_errors = int(d.errors_count or 0)
                    break
        except Exception:
            doc0_errors = None
        doc0_completed = bool(doc0_exists and (doc0_errors is None or doc0_errors == 0))

        btn_label = "✅ Completado" if doc0_completed else "✏️ Completar"
        btn_type = "primary" if doc0_completed else "secondary"
        if st.button(btn_label, width="stretch", type=btn_type, key=f"juzgado_doc0_completar__{case_id}"):
            # Completar = generar el PDF oficial rellenado con los datos actuales (auto + overrides).
            # No inventa debtor_flags; si faltan, se muestra error.
            template_pdf = Path(
                # IMPORTANTE: usar la plantilla que SÍ tiene campos rellenables (AcroForm).
                # La variante `formulario_oficial_v2020_05_21.pdf` no expone campos y no se puede rellenar.
                "judicial_forms/concurso_voluntario/personas_juridicas/"
                "20200521 Procedimientos concursales - Formulario para la solicitud de concurso voluntario pers. jur..pdf"
            )
            field_map = Path("judicial_forms/concurso_voluntario/personas_juridicas/field_map.json")
            try:
                # region agent log (debug-mode)
                try:
                    _dbg_log_tab9(
                        "H_DOC0",
                        "app/ui/streamlit_mvp.py:juzgado_doc0_completar",
                        "click",
                        {
                            "case_id": str(case_id),
                            "template_exists": bool(template_pdf.exists()),
                            "field_map_exists": bool(field_map.exists()),
                            "state_present": bool(state is not None),
                            "doc0_out_exists_before": bool(doc0_out.exists()),
                        },
                    )
                except Exception:
                    pass
                # endregion agent log (debug-mode)

                # Ensure state exists (best-effort; no inventar)
                if state is None:
                    try:
                        state = court_pack_service.load_state(case_root)
                    except Exception:
                        state = None

                if state is None:
                    st.error("No hay CourtPackState (faltan debtor_flags en inputs).")
                else:
                    # Force official template/map for this action
                    pdf_form_filler.TEMPLATE_PDF_PATH = template_pdf
                    pdf_form_filler.FIELD_MAP_PATH = field_map

                    outp = pdf_form_filler.generate_document_0(case_root, state, user_id="ui")

                    # Reload state to reflect issues/errors_count
                    try:
                        st2 = court_pack_service.load_state(case_root)
                        doc0 = None
                        for d in st2.documents:
                            if d.doc_type == "doc0_formulario":
                                doc0 = d
                                break
                        if doc0 and int(doc0.errors_count or 0) > 0:
                            msg = None
                            try:
                                if doc0.issues:
                                    msg = doc0.issues[0].message
                            except Exception:
                                msg = None
                            st.error(f"No se pudo rellenar el documento oficial: {msg or 'error'}")
                        else:
                            st.success("✅ Documento oficial completado.")
                    except Exception as e:
                        st.success("✅ Documento oficial completado.")

                    # region agent log (debug-mode)
                    try:
                        doc0_err = None
                        try:
                            st2 = court_pack_service.load_state(case_root)
                            for d in st2.documents:
                                if d.doc_type == "doc0_formulario":
                                    doc0_err = int(d.errors_count or 0)
                                    break
                        except Exception:
                            doc0_err = None
                        _dbg_log_tab9(
                            "H_DOC0",
                            "app/ui/streamlit_mvp.py:juzgado_doc0_completar",
                            "result",
                            {
                                "case_id": str(case_id),
                                "doc0_out_exists_after": bool(doc0_out.exists()),
                                "doc0_out_size": int(doc0_out.stat().st_size) if doc0_out.exists() else 0,
                                "doc0_errors": doc0_err,
                            },
                        )
                    except Exception:
                        pass
                    # endregion agent log (debug-mode)

                    st.rerun()
            except FileNotFoundError as e:
                st.error(f"Falta recurso obligatorio: {e}")
            except Exception as e:
                # region agent log (debug-mode)
                try:
                    _dbg_log_tab9(
                        "H_DOC0",
                        "app/ui/streamlit_mvp.py:juzgado_doc0_completar",
                        "exception",
                        {"case_id": str(case_id), "err": str(type(e).__name__)},
                    )
                except Exception:
                    pass
                # endregion agent log (debug-mode)
                st.error(f"Error completando documento oficial: {e}")
        # E) 5) rellenar documento oficial
        st.markdown("---")
        with st.container(border=True):
            st.markdown("### Paso final (opcional): Enviar justificante")
            st.caption("Este bloque es opcional y está pensado como cierre del proceso (adjuntar justificante y guardar la notificación).")

            # region agent log (debug-mode)
            def _dbg_log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
                try:
                    _path = "/Users/irumabragado/Documents/procesos/202512_phoenix-legal/.cursor/debug.log"
                    payload = {
                        "sessionId": "debug-session",
                        "runId": "post-fix-justificante-v1",
                        "hypothesisId": hypothesis_id,
                        "location": location,
                        "message": message,
                        "data": data,
                        "timestamp": int(time.time() * 1000),
                    }
                    with open(_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
                except Exception:
                    # Nunca romper la UI por logging
                    pass

            # endregion agent log (debug-mode)

        just = st.file_uploader("Justificante (opcional)", key="juzgado_justificante")
        _dbg_log(
            "H1",
            "app/ui/streamlit_mvp.py:enviar_justificante",
            "uploader_state",
            {
                "case_id": str(case_id),
                "just_present": bool(just),
                "just_name": getattr(just, "name", None) if just else None,
                "just_size": len(just.getvalue()) if just else 0,
            },
        )
        if just:
            st.info("El justificante se guardará cuando pulses **Guardar notificación**.")

        email_despacho = st.text_input("Email despacho", key="juzgado_email_despacho")
        email_cliente = st.text_input("Email cliente", key="juzgado_email_cliente")
        email_extra = st.text_input("Email extra", key="juzgado_email_extra")
        if st.button("Guardar notificación", type="primary", width="stretch"):
            _dbg_log(
                "H1",
                "app/ui/streamlit_mvp.py:enviar_justificante",
                "guardar_notificacion_clicked",
                {
                    "case_id": str(case_id),
                    "just_present": bool(just),
                    "submissions_dir": str(paths.get("submissions_dir")) if isinstance(paths, dict) else None,
                },
            )
            ts = int(time.time())
            justificante_rel = None
            justificante_saved = False
            if just:
                try:
                    # Guardar el fichero subido junto con la notificación (evita pérdida silenciosa).
                    raw_name = getattr(just, "name", "") or "justificante"
                    safe_name = Path(raw_name).name.replace("/", "_").replace("\\", "_")
                    safe_name = safe_name.replace("..", ".")[:200]
                    out = paths["submissions_dir"] / f"justificante__{ts}__{safe_name}"
                    out.write_bytes(just.getvalue())
                    justificante_rel = out.name
                    justificante_saved = True
                    st.success(f"✅ Justificante guardado: `{out}`")
                    _dbg_log(
                        "H3",
                        "app/ui/streamlit_mvp.py:enviar_justificante",
                        "justificante_saved",
                        {
                            "case_id": str(case_id),
                            "path": str(out),
                            "size": len(just.getvalue()),
                        },
                    )
                except Exception as e:
                    st.error(f"No se pudo guardar el justificante: {type(e).__name__}")
                    _dbg_log(
                        "H4",
                        "app/ui/streamlit_mvp.py:enviar_justificante",
                        "justificante_save_error",
                        {"case_id": str(case_id), "error_type": type(e).__name__},
                    )
            payload = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "case_id": str(case_id),
                # No loguear emails (PII); persistimos como parte del payload.
                "emails": {"despacho": email_despacho, "cliente": email_cliente, "extra": email_extra},
                # Referencia al fichero guardado (si aplica)
                "justificante_file": justificante_rel,
            }
            p = paths["submissions_dir"] / f"notification_{ts}.json"
            p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            st.success(f"✅ Notificación guardada: `{p}`")
            _dbg_log(
                "H3",
                "app/ui/streamlit_mvp.py:enviar_justificante",
                "notification_saved",
                {
                    "case_id": str(case_id),
                    "notification_path": str(p),
                    "just_present": bool(just),
                    "just_saved": justificante_saved,
                    "just_rel": justificante_rel,
                },
            )
            if just and not justificante_saved:
                _dbg_log(
                    "H1",
                    "app/ui/streamlit_mvp.py:enviar_justificante",
                    "just_present_but_save_failed",
                    {"case_id": str(case_id), "just_name": getattr(just, "name", None)},
                )

# =========================================
# TAB 7: RIESGOS DE CULPABILIDAD
# =========================================

with tab7:
    st.header("🚨 Riesgos de Culpabilidad Concursal")

    if not case_id:
        st.info("📌 Selecciona un caso para ver el análisis de riesgos")
    else:
        try:
            # Obtener alertas del backend
            alerts = client.get_analysis_alerts(case_id)

            if not alerts:
                st.success("✅ No se han detectado riesgos de culpabilidad significativos")
            else:
                # Calcular score global
                total_score = sum(alert.get("severity_score", 0) for alert in alerts)
                avg_score = total_score / len(alerts) if alerts else 0

                # Nivel de riesgo global
                if avg_score >= 75:
                    nivel_riesgo = "🔴 CRÍTICO"
                    color_riesgo = "red"
                elif avg_score >= 50:
                    nivel_riesgo = "🟠 ALTO"
                    color_riesgo = "orange"
                elif avg_score >= 25:
                    nivel_riesgo = "🟡 MEDIO"
                    color_riesgo = "yellow"
                else:
                    nivel_riesgo = "🟢 BAJO"
                    color_riesgo = "green"

                # Resumen ejecutivo
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric(
                        "Score Global",
                        f"{avg_score:.1f}/100",
                        help="Promedio ponderado de todos los riesgos detectados",
                    )

                with col2:
                    st.metric("Nivel de Riesgo", nivel_riesgo)

                with col3:
                    st.metric("Riesgos Detectados", len(alerts))

                st.markdown("---")

                # Filtros
                st.subheader("🔍 Filtros")
                col_f1, col_f2, col_f3 = st.columns(3)

                with col_f1:
                    severity_filter = st.selectbox(
                        "Severidad",
                        ["Todas", "CRITICAL", "HIGH", "MEDIUM", "LOW"],
                        key="severity_filter",
                    )

                with col_f2:
                    confidence_filter = st.selectbox(
                        "Confianza", ["Todas", "HIGH", "MEDIUM", "LOW"], key="confidence_filter"
                    )

                with col_f3:
                    category_filter = st.selectbox(
                        "Categoría",
                        [
                            "Todas",
                            "ocultacion_bienes",
                            "salida_recursos",
                            "contrataciones_lesivas",
                            "operaciones_vinculados",
                        ],
                        key="category_filter",
                    )

                # Aplicar filtros
                filtered_alerts = alerts
                if severity_filter != "Todas":
                    filtered_alerts = [
                        a for a in filtered_alerts if a.get("severity") == severity_filter
                    ]
                if confidence_filter != "Todas":
                    filtered_alerts = [
                        a for a in filtered_alerts if a.get("confidence") == confidence_filter
                    ]
                if category_filter != "Todas":
                    filtered_alerts = [
                        a for a in filtered_alerts if a.get("category") == category_filter
                    ]

                st.write(f"**Mostrando {len(filtered_alerts)} de {len(alerts)} riesgos**")

                # Agrupar por categoría
                st.markdown("---")
                st.subheader("📊 Riesgos por Categoría")

                categories = {}
                for alert in filtered_alerts:
                    cat = alert.get("category", "otros")
                    if cat not in categories:
                        categories[cat] = []
                    categories[cat].append(alert)

                # Mapeo de nombres legibles
                cat_names = {
                    "ocultacion_bienes": "🔒 Ocultación de Bienes",
                    "salida_recursos": "💸 Salida de Recursos",
                    "contrataciones_lesivas": "📝 Contrataciones Lesivas",
                    "operaciones_vinculados": "👥 Operaciones con Vinculados",
                }

                for cat, cat_alerts in categories.items():
                    cat_name = cat_names.get(cat, cat.replace("_", " ").title())

                    with st.expander(f"{cat_name} ({len(cat_alerts)} riesgos)", expanded=True):
                        for idx, alert in enumerate(cat_alerts, 1):
                            # Severidad con emoji
                            severity_emoji = {
                                "CRITICAL": "🔴",
                                "HIGH": "🟠",
                                "MEDIUM": "🟡",
                                "LOW": "🟢",
                            }.get(alert.get("severity", "MEDIUM"), "⚪")

                            st.markdown(
                                f"### {severity_emoji} Riesgo {idx}: {alert.get('title', 'Sin título')}"
                            )

                            # Métricas del riesgo
                            col_r1, col_r2, col_r3 = st.columns(3)

                            with col_r1:
                                st.metric("Score", f"{alert.get('severity_score', 0)}/100")

                            with col_r2:
                                st.metric("Severidad", alert.get("severity", "N/A"))

                            with col_r3:
                                st.metric("Confianza", alert.get("confidence", "N/A"))

                            # Descripción
                            if alert.get("description"):
                                st.write("**Descripción:**")
                                st.write(alert["description"])

                            # Base legal
                            if alert.get("legal_basis"):
                                st.write("**Base Legal:**")
                                for basis in alert["legal_basis"]:
                                    st.write(f"- {basis}")

                            # Evidencias
                            evidence_list = alert.get("evidence", [])
                            if evidence_list:
                                st.write(f"**Evidencias:** {len(evidence_list)} documento(s)")
                                st.markdown("")

                                # Renderizar evidencias con función dedicada
                                render_alert_evidence_list(
                                    evidence_list=evidence_list,
                                    alert_id=alert.get("alert_id", f"{cat}_{idx}"),
                                )

                            st.markdown("---")

        except Exception as e:
            st.error(f"Error al cargar riesgos: {e}")
            st.write("Verifica que el backend esté disponible y el análisis se haya completado")

# =========================================
# TAB 8: CUADRO DE SITUACIÓN (MVP: BUSCADOR)
# =========================================

with tab8:
    st.header("📚 Datos")

    if not case_id:
        st.info("📌 Selecciona un caso para usar el buscador y el cuadro de situación")
    else:
        # Identidad de usuario para auditoría/evidencia (compartida entre sub-tabs)
        created_by_default = st.session_state.get("situation_created_by", "abogado")
        st.text_input(
            "Usuario (cuadro/evidencia)",
            value=created_by_default,
            key="situation_created_by",
            help="Se registra en auditoría/evidencia. Ej: abogado@despacho.com",
        )

        sub_a, sub_b, sub_c = st.tabs(["🔎 Buscador documental", "🗃️ Base de datos (Datos)", "⚖️ Pliegos (Juzgado/AC)"])

        with sub_a:
            st.subheader("🔎 Buscador (global) — documentos + datos")

            # Estado UI
            if "doc_search_category" not in st.session_state:
                # Default: buscar en TODO (sin filtro por doc_type/categoría)
                st.session_state["doc_search_category"] = ""

            # Nota: el usuario (added_by) se define arriba (compartido entre sub-tabs)

            # Categorías rápidas
            st.write("**Filtros rápidos:**")
            c0, c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns(10)
            if c0.button("📚 Todos", use_container_width=True):
                st.session_state["doc_search_category"] = ""
            if c1.button("🏛️ Juzgado", use_container_width=True):
                st.session_state["doc_search_category"] = "JUZGADO"
            if c2.button("🧾 Facturas", use_container_width=True):
                st.session_state["doc_search_category"] = "FACTURAS"
            if c3.button("🏦 Bancos", use_container_width=True):
                st.session_state["doc_search_category"] = "BANCOS"
            if c4.button("🏛️ AEAT", use_container_width=True):
                st.session_state["doc_search_category"] = "AEAT"
            if c5.button("👷 TGSS", use_container_width=True):
                st.session_state["doc_search_category"] = "TGSS"
            if c6.button("📊 Contabilidad", use_container_width=True):
                st.session_state["doc_search_category"] = "CONTABILIDAD"
            if c7.button("🏠 Activos", use_container_width=True):
                st.session_state["doc_search_category"] = "ACTIVOS"
            if c8.button("⚖️ Concursal", use_container_width=True):
                st.session_state["doc_search_category"] = "CONCURSAL"
            if c9.button("📄 Otros", use_container_width=True):
                st.session_state["doc_search_category"] = "OTROS"

            st.markdown("---")

            # Filtros avanzados
            col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 1, 1])
            with col_f1:
                q = st.text_input(
                    "Buscar texto (filename / contenido)",
                    value=st.session_state.get("doc_search_q", ""),
                    key="doc_search_q",
                    placeholder="Ej: escritura, burofax, modelo 303, embargo…",
                )
            with col_f2:
                try:
                    from app.core.doc_types import DOC_TYPES

                    all_types = list(DOC_TYPES)
                except Exception:
                    all_types = []

                selected_types = st.multiselect(
                    "Filtrar por doc_type (opcional)",
                    options=all_types,
                    default=[],
                    key="doc_search_types",
                )
            with col_f3:
                page_size = st.selectbox("Tamaño", [10, 20, 50, 100], index=1, key="doc_search_page_size")
            with col_f4:
                page = st.number_input("Página", min_value=1, value=1, step=1, key="doc_search_page")

            category = st.session_state.get("doc_search_category", "")
            st.caption(
                f"Categoría activa: **{(category or 'TODOS')}** (se ignora si eliges doc_types)"
            )

            st.markdown("**Ámbito de búsqueda:**")
            col_s1, col_s2, col_s3 = st.columns([1.2, 1.2, 1])
            with col_s1:
                search_docs = st.checkbox("Documentos", value=True, key="global_search_docs")
            with col_s2:
                search_situation = st.checkbox("Datos", value=True, key="global_search_situation")
            with col_s3:
                include_history = st.checkbox("Incluir histórico", value=False, key="global_search_include_history")

            run = st.button("🔎 Buscar", type="primary")
            if run:
                try:
                    if not (search_docs or search_situation):
                        st.warning("Activa al menos un ámbito: Documentos y/o Datos.")
                        raise RuntimeError("No search scope selected")

                    doc_items = []
                    doc_total = 0
                    if search_docs:
                        resp = client.search_documents(
                            case_id,
                            q=q or None,
                            category=(category or None) if not selected_types else None,
                            doc_types=selected_types or None,
                            include_chunk_id=True,
                            page=int(page),
                            page_size=int(page_size),
                        )
                        doc_items = resp.get("items", []) or []
                        doc_total = int(resp.get("total", 0) or 0)

                    sit = {}
                    if search_situation and (q or "").strip():
                        sit = client.search_situation(
                            case_id,
                            q=str(q).strip(),
                            include_history=bool(include_history),
                            page=int(page),
                            page_size=int(page_size),
                        )

                    st.success(
                        f"✅ Documentos: {len(doc_items)} (total: {doc_total}) · "
                        f"Cuadro: {sum(int((g or {}).get('total', 0) or 0) for g in (sit.get('groups') or {}).values())}"
                    )

                    # ----------------------------
                    # Resultados: Documentos
                    # ----------------------------
                    if search_docs:
                        st.markdown("### Documentos")
                        if doc_items:
                            rows = []
                            for it in doc_items:
                                rows.append(
                                    {
                                        "filename": it.get("filename"),
                                        "doc_type": it.get("doc_type"),
                                        "created_at": it.get("created_at"),
                                        "page": it.get("page"),
                                        "confidence": it.get("confidence"),
                                        "chunk_id": it.get("chunk_id"),
                                        "document_id": it.get("document_id"),
                                    }
                                )
                            st.dataframe(rows, use_container_width=True, hide_index=True)

                            st.markdown("---")
                            st.subheader("👁️ Vista rápida (snippets)")
                            for it in doc_items[:25]:
                                label = f"{it.get('filename')} — {it.get('doc_type')} (pág. {it.get('page') or '—'})"
                                with st.expander(label, expanded=False):
                                    doc_id = it.get("document_id")
                                    st.write(f"**Document ID:** `{doc_id}`")
                                    if it.get("chunk_id"):
                                        st.write(f"**Chunk ID:** `{it.get('chunk_id')}`")
                                    st.write(f"**Confianza:** {it.get('confidence')}")
                                    sn = it.get("snippet")
                                    if sn:
                                        st.write(sn)
                                    else:
                                        st.info("Sin snippet disponible (no hay chunks o contenido vacío).")

                                    if doc_id:
                                        url_view = _download_doc_url(case_id, doc_id, disposition="inline")
                                        url_dl = _download_doc_url(case_id, doc_id, disposition="attachment")
                                        st.markdown(f"[🔎 Ver]({url_view}) · [⬇️ Descargar]({url_dl})")
                        else:
                            st.info("Sin resultados en Documentos con esos filtros.")

                    # ----------------------------
                    # Resultados: Datos
                    # ----------------------------
                    if search_situation:
                        st.markdown("### Datos")
                        groups = sit.get("groups") or {}
                        if not groups:
                            st.info("Sin resultados en Datos.")
                        else:
                            def _render_group(title: str, key: str, cols: list[str]):
                                g = groups.get(key) or {}
                                items2 = g.get("items") or []
                                total2 = int(g.get("total", 0) or 0)
                                st.subheader(f"{title} — {len(items2)} (total: {total2})")
                                if not items2:
                                    st.write("—")
                                    return
                                # Tabla
                                st.dataframe(
                                    [
                                        {
                                            **{c: (it.get("data", {}) or {}).get(c) for c in cols},
                                            "evidence": it.get("evidence_ref"),
                                            "record_id": it.get("record_id"),
                                        }
                                        for it in items2
                                    ],
                                    use_container_width=True,
                                    hide_index=True,
                                )
                                # Drilldown
                                for it in items2[:20]:
                                    with st.expander(it.get("label") or it.get("record_id"), expanded=False):
                                        rid = it.get("record_id")
                                        ent = it.get("entity")
                                        st.write(f"**record_id:** `{rid}` · **entity:** `{ent}`")
                                        if rid and ent:
                                            try:
                                                ev = client.list_situation_record_evidence(case_id, entity=ent, record_id=rid)
                                                ev_items = ev.get("items", []) or []
                                                if ev_items:
                                                    st.dataframe(ev_items, use_container_width=True, hide_index=True)
                                                    for evi in ev_items:
                                                        doc_id2 = evi.get("document_id")
                                                        if doc_id2:
                                                            url2_view = _download_doc_url(case_id, doc_id2, disposition="inline")
                                                            url2_dl = _download_doc_url(case_id, doc_id2, disposition="attachment")
                                                            st.markdown(f"- [🔎 Ver]({url2_view}) · [⬇️ Descargar]({url2_dl})")
                                                else:
                                                    st.info("Sin evidencia enlazada.")
                                            except Exception as e:
                                                st.error(f"Error cargando evidencia: {e}")

                            _render_group(
                                "🧾 Facturas",
                                "invoice",
                                ["supplier", "invoice_number", "issue_date", "due_date", "paid_date", "amount_total", "status", "currency"],
                            )
                            _render_group(
                                "💳 Créditos",
                                "credit",
                                ["creditor", "contract_ref", "amount_total", "currency", "maturity_date", "secured"],
                            )
                            _render_group(
                                "🏛️ Deuda pública",
                                "public_debt",
                                ["authority", "concept", "reference", "period_start", "period_end", "amount_total", "status", "currency"],
                            )
                            _render_group(
                                "🏛️ Juzgado",
                                "court",
                                ["court", "procedure_number", "autos_ref", "claimant", "amount_claimed", "status", "stage", "currency"],
                            )

                except Exception as e:
                    st.error(f"Error en búsqueda: {e}")

        with sub_b:
            st.subheader("🗃️ Base de datos (Datos)")
            st.caption(
                "Reglas: **alta/edición requiere evidencia y motivo**; edición = **nueva versión (append-only)**."
            )

            # KPIs rápidos (server-side)
            try:
                kpis = client.get_situation_kpis(case_id)
            except Exception:
                kpis = None
            if kpis:
                st.markdown("### 📊 KPIs (vigentes)")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Pasivo total", f"{float(kpis.get('total_pasivo') or 0.0):.2f}")
                c2.metric("Deuda pública", f"{float(kpis.get('total_deuda_publica') or 0.0):.2f}")
                c3.metric("Acreedores", str(int(kpis.get("num_acreedores") or 0)))
                c4.metric("Facturas", str(int(kpis.get("num_facturas") or 0)))
                st.caption(
                    f"Créditos: {int(kpis.get('num_creditos') or 0)} | "
                    f"Bienes: {int(kpis.get('num_bienes') or 0)} | "
                    f"Actuaciones: {int(kpis.get('num_actuaciones') or 0)}"
                )
                if kpis.get("by_currency"):
                    st.dataframe(kpis["by_currency"], use_container_width=True, hide_index=True)

            if st.button("⬇️ Exportar TODO (Excel, 5 pestañas)", key="export_situation_all_excel"):
                try:
                    data = client.download_situation_export_excel(case_id)
                    st.download_button(
                        "Descargar Excel del caso",
                        data=data,
                        file_name=f"situation_{case_id}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_situation_all_excel",
                    )
                except Exception as e:
                    st.error(f"Error exportando Excel: {e}")

            # Documentos disponibles para evidencia
            try:
                docs = client.list_documents(case_id)
            except Exception:
                docs = []

            doc_options = {}
            for d in docs or []:
                label = f"{d.get('filename')} ({(d.get('document_id') or '')[:8]}…)"
                doc_options[label] = d.get("document_id")

            if not doc_options:
                st.warning(
                    "No hay documentos disponibles para evidencia. "
                    "Sube documentos primero (Tab Documentos) para poder crear/editar registros."
                )

            def _evidence_inputs(prefix: str):
                col_ev1, col_ev2 = st.columns([2, 1])
                with col_ev1:
                    doc_label = st.selectbox(
                        "Documento (evidencia)",
                        options=list(doc_options.keys()) if doc_options else [],
                        key=f"{prefix}_ev_doc",
                    )
                    doc_id = doc_options.get(doc_label) if doc_label else None
                with col_ev2:
                    page = st.number_input(
                        "Página (opcional)",
                        min_value=1,
                        value=1,
                        step=1,
                        key=f"{prefix}_ev_page",
                    )
                note = st.text_area(
                    "Nota/justificación (obligatoria)",
                    key=f"{prefix}_ev_note",
                    placeholder="Ej: Extracto donde consta el saldo/impago; o página donde figura la deuda/contrato…",
                )
                if not doc_id:
                    return None
                return [{"document_id": doc_id, "page": int(page) if page else None, "note": note}]

            created_by = st.session_state.get("situation_created_by", "abogado")

            tab_inv, tab_cred, tab_assets, tab_pub, tab_court = st.tabs(
                ["🧾 Facturas", "💳 Créditos", "🏠 Bienes", "🏛️ Deuda pública", "🏛️ Juzgado"]
            )

            # ----------------------------
            # FACTURAS
            # ----------------------------
            with tab_inv:
                st.subheader("🧾 Facturas")
                col_fa1, col_fa2, col_fa3, col_fa4, col_fa5 = st.columns([2, 1, 1, 1, 1])
                with col_fa1:
                    inv_supplier_filter = st.text_input(
                        "Proveedor contiene (opcional)",
                        key="inv_filter_supplier",
                        placeholder="Ej: Iberdrola, Vodafone…",
                    )
                with col_fa2:
                    inv_status_filter = st.text_input(
                        "Estado contiene (opcional)",
                        key="inv_filter_status",
                        placeholder="pendiente/impagada…",
                    )
                with col_fa3:
                    inv_page_size = st.selectbox("Tamaño", [10, 20, 50, 100], index=1, key="inv_filter_page_size")
                with col_fa4:
                    inv_page = st.number_input("Página", min_value=1, value=1, step=1, key="inv_filter_page")
                with col_fa5:
                    inv_include_history = st.checkbox(
                        "Histórico (todas)",
                        value=False,
                        key="inv_filter_include_history",
                        help="Si se activa, muestra todas las versiones. Si no, solo vigentes.",
                    )
                try:
                    resp = client.list_situation_invoices(
                        case_id,
                        include_history=bool(inv_include_history),
                        supplier=inv_supplier_filter or None,
                        status=inv_status_filter or None,
                        page=int(inv_page),
                        page_size=int(inv_page_size),
                    )
                    items = resp.get("items", [])
                    total = int(resp.get("total", 0) or 0)
                except Exception as e:
                    st.error(f"Error cargando facturas: {e}")
                    items = []
                    total = 0

                if st.button("⬇️ Exportar facturas (Excel)", key="export_invoices_excel"):
                    try:
                        data = client.download_situation_invoices_excel(case_id)
                        st.download_button(
                            "Descargar Excel",
                            data=data,
                            file_name=f"situation_invoices_{case_id}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_invoices_excel",
                        )
                    except Exception as e:
                        st.error(f"Error exportando Excel: {e}")

                with st.expander("➕ Añadir factura", expanded=False):
                    supplier = st.text_input("Proveedor/Acreedor", key="inv_supplier")
                    supplier_tax_id = st.text_input("NIF proveedor (opcional)", key="inv_supplier_tax_id")
                    invoice_number = st.text_input("Nº factura (opcional)", key="inv_number")
                    contract_ref = st.text_input("Ref. contrato/pedido (opcional)", key="inv_contract_ref")
                    issue_date = st.text_input("Fecha emisión (YYYY-MM-DD, opcional)", key="inv_issue")
                    due_date = st.text_input("Vencimiento (YYYY-MM-DD, opcional)", key="inv_due")
                    amount_total = st.number_input("Importe total", min_value=0.0, value=0.0, key="inv_amount")
                    status_txt = st.text_input("Estado (pendiente/pagada/impagada, opcional)", key="inv_status")
                    notes = st.text_area("Notas (opcional)", key="inv_notes")
                    reason = st.text_area(
                        "Motivo (obligatorio)",
                        key="inv_reason",
                        placeholder="Ej: Alta por revisión de factura aportada por el cliente.",
                    )
                    evidence = _evidence_inputs("inv_create")

                    if st.button("💾 Crear factura", type="primary", disabled=not bool(doc_options)):
                        try:
                            payload = {
                                "created_by": created_by,
                                "reason": reason,
                                "evidence": evidence or [],
                                "supplier": supplier,
                                "supplier_tax_id": supplier_tax_id or None,
                                "invoice_number": invoice_number or None,
                                "contract_ref": contract_ref or None,
                                "issue_date": issue_date or None,
                                "due_date": due_date or None,
                                "amount_total": float(amount_total),
                                "status": status_txt or None,
                                "notes": notes or None,
                            }
                            client.create_situation_invoice(case_id, payload)
                            st.success("✅ Factura creada")
                            # Invalidate cache of link-targets after creating/updating records
                            st.session_state["evidence_link_cache"] = {}
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error creando factura: {e}")

                if items:
                    st.write(f"Mostrando **{len(items)}** de **{total}** factura(s).")
                    st.dataframe(
                        [
                            {
                                "supplier": it["data"].get("supplier"),
                                "amount_total": it["data"].get("amount_total"),
                                "due_date": it["data"].get("due_date"),
                                "status": it["data"].get("status"),
                                "version": it.get("version"),
                                "evidence": it.get("evidence_count"),
                                "logical_id": it.get("logical_id"),
                            }
                            for it in items
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.markdown("---")
                    st.subheader("✏️ Editar (crea nueva versión)")
                    for it in items:
                        data = it.get("data", {}) or {}
                        exp_label = f"{data.get('supplier')} — {data.get('amount_total')} {data.get('currency','EUR')} (v{it.get('version')})"
                        with st.expander(exp_label, expanded=False):
                            # Evidencia + auditoría (por registro)
                            col_meta1, col_meta2 = st.columns([1, 1])
                            with col_meta1:
                                if st.button(
                                    "📎 Ver evidencia",
                                    key=f"inv_view_evidence_{it['record_id']}",
                                ):
                                    try:
                                        ev_resp = client.list_situation_record_evidence(
                                            case_id, entity="INVOICE", record_id=it["record_id"]
                                        )
                                        ev_items = ev_resp.get("items", [])
                                        if not ev_items:
                                            st.info("Sin evidencia (no esperado en MVP).")
                                        else:
                                            st.dataframe(ev_items, use_container_width=True, hide_index=True)
                                    except Exception as e:
                                        st.error(f"Error cargando evidencia: {e}")
                            with col_meta2:
                                if st.button(
                                    "🧾 Ver auditoría",
                                    key=f"inv_view_audit_{it['record_id']}",
                                ):
                                    try:
                                        au_resp = client.list_situation_audit(
                                            case_id, entity="INVOICE", logical_id=it["logical_id"]
                                        )
                                        au_items = au_resp.get("items", [])
                                        if not au_items:
                                            st.info("Sin auditoría.")
                                        else:
                                            st.dataframe(au_items, use_container_width=True, hide_index=True)
                                    except Exception as e:
                                        st.error(f"Error cargando auditoría: {e}")

                            with st.expander("➕ Añadir evidencia (sin crear versión)", expanded=False):
                                ev_reason_add = st.text_area(
                                    "Motivo (obligatorio)",
                                    key=f"inv_add_ev_reason_{it['record_id']}",
                                    placeholder="Ej: Se incorpora documento adicional que acredita el importe/vencimiento.",
                                )
                                ev_add = _evidence_inputs(f"inv_add_ev_{it['record_id']}")
                                if st.button(
                                    "💾 Añadir evidencia",
                                    key=f"inv_add_ev_btn_{it['record_id']}",
                                    disabled=not bool(doc_options),
                                ):
                                    try:
                                        payload = {
                                            "created_by": created_by,
                                            "reason": ev_reason_add,
                                            "evidence": ev_add or [],
                                        }
                                        client.add_situation_record_evidence(
                                            case_id,
                                            entity="INVOICE",
                                            record_id=it["record_id"],
                                            payload=payload,
                                        )
                                        st.success("✅ Evidencia añadida")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error añadiendo evidencia: {e}")

                            supplier_u = st.text_input(
                                "Proveedor/Acreedor",
                                value=data.get("supplier") or "",
                                key=f"inv_u_supplier_{it['record_id']}",
                            )
                            supplier_tax_id_u = st.text_input(
                                "NIF proveedor (opcional)",
                                value=data.get("supplier_tax_id") or "",
                                key=f"inv_u_supplier_tax_id_{it['record_id']}",
                            )
                            invoice_number_u = st.text_input(
                                "Nº factura (opcional)",
                                value=data.get("invoice_number") or "",
                                key=f"inv_u_number_{it['record_id']}",
                            )
                            contract_ref_u = st.text_input(
                                "Ref. contrato/pedido (opcional)",
                                value=data.get("contract_ref") or "",
                                key=f"inv_u_contract_ref_{it['record_id']}",
                            )
                            issue_date_u = st.text_input(
                                "Fecha emisión (YYYY-MM-DD, opcional)",
                                value=data.get("issue_date") or "",
                                key=f"inv_u_issue_{it['record_id']}",
                            )
                            amount_u = st.number_input(
                                "Importe total",
                                min_value=0.0,
                                value=float(data.get("amount_total") or 0.0),
                                key=f"inv_u_amount_{it['record_id']}",
                            )
                            due_u = st.text_input(
                                "Vencimiento (YYYY-MM-DD, opcional)",
                                value=data.get("due_date") or "",
                                key=f"inv_u_due_{it['record_id']}",
                            )
                            status_u = st.text_input(
                                "Estado (opcional)",
                                value=data.get("status") or "",
                                key=f"inv_u_status_{it['record_id']}",
                            )
                            notes_u = st.text_area(
                                "Notas (opcional)",
                                value=data.get("notes") or "",
                                key=f"inv_u_notes_{it['record_id']}",
                            )
                            reason_u = st.text_area(
                                "Motivo (obligatorio)",
                                key=f"inv_u_reason_{it['record_id']}",
                                placeholder="Ej: Corrección por contraste con extracto/documentación adicional.",
                            )
                            evidence_u = _evidence_inputs(f"inv_update_{it['record_id']}")

                            if st.button(
                                "✅ Guardar nueva versión",
                                key=f"inv_u_btn_{it['record_id']}",
                                disabled=not bool(doc_options),
                            ):
                                try:
                                    payload = {
                                        "created_by": created_by,
                                        "reason": reason_u,
                                        "evidence": evidence_u or [],
                                        "logical_id": it["logical_id"],
                                        "expected_version": int(it["version"]),
                                        "supplier": supplier_u,
                                        "supplier_tax_id": supplier_tax_id_u or None,
                                        "invoice_number": invoice_number_u or None,
                                        "contract_ref": contract_ref_u or None,
                                        "issue_date": issue_date_u or None,
                                        "due_date": due_u or None,
                                        "amount_total": float(amount_u),
                                        "status": status_u or None,
                                        "notes": notes_u or None,
                                    }
                                    client.update_situation_invoice(case_id, payload)
                                    st.success("✅ Factura actualizada (nueva versión creada)")
                                    st.session_state["evidence_link_cache"] = {}
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error actualizando factura: {e}")
                else:
                    st.info("Aún no hay facturas. Crea la primera arriba.")

            # ----------------------------
            # CRÉDITOS
            # ----------------------------
            with tab_cred:
                st.subheader("💳 Créditos")
                col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns([2, 1, 1, 1, 1])
                with col_c1:
                    cred_creditor_filter = st.text_input(
                        "Acreedor contiene (opcional)",
                        key="cred_filter_creditor",
                        placeholder="Ej: Banco, Leasing…",
                    )
                with col_c2:
                    cred_secured_filter = st.selectbox(
                        "Garantía",
                        ["", "Solo garantizados", "Solo no garantizados"],
                        index=0,
                        key="cred_filter_secured",
                    )
                with col_c3:
                    cred_page_size = st.selectbox(
                        "Tamaño",
                        [10, 20, 50, 100],
                        index=1,
                        key="cred_filter_page_size",
                    )
                with col_c4:
                    cred_page = st.number_input(
                        "Página",
                        min_value=1,
                        value=1,
                        step=1,
                        key="cred_filter_page",
                    )
                with col_c5:
                    cred_include_history = st.checkbox(
                        "Histórico (todas)",
                        value=False,
                        key="cred_filter_include_history",
                    )
                try:
                    secured_val = None
                    if cred_secured_filter == "Solo garantizados":
                        secured_val = True
                    elif cred_secured_filter == "Solo no garantizados":
                        secured_val = False
                    resp = client.list_situation_credits(
                        case_id,
                        include_history=bool(cred_include_history),
                        creditor=cred_creditor_filter or None,
                        secured=secured_val,
                        page=int(cred_page),
                        page_size=int(cred_page_size),
                    )
                    items = resp.get("items", [])
                    total = int(resp.get("total", 0) or 0)
                except Exception as e:
                    st.error(f"Error cargando créditos: {e}")
                    items = []
                    total = 0

                if st.button("⬇️ Exportar créditos (Excel)", key="export_credits_excel"):
                    try:
                        data = client.download_situation_credits_excel(case_id)
                        st.download_button(
                            "Descargar Excel",
                            data=data,
                            file_name=f"situation_credits_{case_id}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_credits_excel",
                        )
                    except Exception as e:
                        st.error(f"Error exportando Excel: {e}")

                with st.expander("➕ Añadir crédito", expanded=False):
                    creditor = st.text_input("Acreedor", key="cred_creditor")
                    creditor_tax_id = st.text_input("NIF acreedor (opcional)", key="cred_tax_id")
                    contract_ref = st.text_input("Referencia contrato (opcional)", key="cred_ref")
                    amount_total = st.number_input("Importe total", min_value=0.0, value=0.0, key="cred_amount")
                    outstanding_principal = st.number_input(
                        "Principal pendiente (opcional)",
                        min_value=0.0,
                        value=0.0,
                        key="cred_outstanding_principal",
                    )
                    secured = st.checkbox("Garantizado (hipoteca/prenda/aval)", value=False, key="cred_secured")
                    guarantee_details = st.text_area("Detalle garantía (opcional)", key="cred_guarantee")
                    maturity_date = st.text_input("Vencimiento (YYYY-MM-DD, opcional)", key="cred_maturity")
                    notes = st.text_area("Notas (opcional)", key="cred_notes")
                    reason = st.text_area("Motivo (obligatorio)", key="cred_reason")
                    evidence = _evidence_inputs("cred_create")

                    if st.button("💾 Crear crédito", type="primary", disabled=not bool(doc_options)):
                        try:
                            payload = {
                                "created_by": created_by,
                                "reason": reason,
                                "evidence": evidence or [],
                                "creditor": creditor,
                                "creditor_tax_id": creditor_tax_id or None,
                                "contract_ref": contract_ref or None,
                                "amount_total": float(amount_total),
                                "outstanding_principal": float(outstanding_principal),
                                "secured": bool(secured),
                                "guarantee_details": guarantee_details or None,
                                "maturity_date": maturity_date or None,
                                "notes": notes or None,
                            }
                            client.create_situation_credit(case_id, payload)
                            st.success("✅ Crédito creado")
                            st.session_state["evidence_link_cache"] = {}
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error creando crédito: {e}")

                if items:
                    st.write(f"Mostrando **{len(items)}** de **{total}** crédito(s).")
                    st.dataframe(
                        [
                            {
                                "creditor": it["data"].get("creditor"),
                                "amount_total": it["data"].get("amount_total"),
                                "secured": it["data"].get("secured"),
                                "version": it.get("version"),
                                "evidence": it.get("evidence_count"),
                                "logical_id": it.get("logical_id"),
                            }
                            for it in items
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.markdown("---")
                    for it in items:
                        data = it.get("data", {}) or {}
                        with st.expander(
                            f"{data.get('creditor')} — {data.get('amount_total')} {data.get('currency','EUR')} (v{it.get('version')})",
                            expanded=False,
                        ):
                            creditor_u = st.text_input(
                                "Acreedor",
                                value=data.get("creditor") or "",
                                key=f"cred_u_creditor_{it['record_id']}",
                            )
                            creditor_tax_id_u = st.text_input(
                                "NIF acreedor (opcional)",
                                value=data.get("creditor_tax_id") or "",
                                key=f"cred_u_tax_id_{it['record_id']}",
                            )
                            contract_ref_u = st.text_input(
                                "Referencia contrato (opcional)",
                                value=data.get("contract_ref") or "",
                                key=f"cred_u_ref_{it['record_id']}",
                            )
                            amount_u = st.number_input(
                                "Importe total",
                                min_value=0.0,
                                value=float(data.get("amount_total") or 0.0),
                                key=f"cred_u_amount_{it['record_id']}",
                            )
                            outstanding_principal_u = st.number_input(
                                "Principal pendiente (opcional)",
                                min_value=0.0,
                                value=float(data.get("outstanding_principal") or 0.0),
                                key=f"cred_u_outstanding_principal_{it['record_id']}",
                            )
                            secured_u = st.checkbox(
                                "Garantizado",
                                value=bool(data.get("secured") or False),
                                key=f"cred_u_secured_{it['record_id']}",
                            )
                            guarantee_u = st.text_area(
                                "Detalle garantía (opcional)",
                                value=data.get("guarantee_details") or "",
                                key=f"cred_u_guarantee_{it['record_id']}",
                            )
                            maturity_u = st.text_input(
                                "Vencimiento (YYYY-MM-DD, opcional)",
                                value=data.get("maturity_date") or "",
                                key=f"cred_u_maturity_{it['record_id']}",
                            )
                            notes_u = st.text_area(
                                "Notas (opcional)",
                                value=data.get("notes") or "",
                                key=f"cred_u_notes_{it['record_id']}",
                            )
                            reason_u = st.text_area(
                                "Motivo (obligatorio)",
                                key=f"cred_u_reason_{it['record_id']}",
                            )
                            evidence_u = _evidence_inputs(f"cred_update_{it['record_id']}")

                            if st.button(
                                "✅ Guardar nueva versión",
                                key=f"cred_u_btn_{it['record_id']}",
                                disabled=not bool(doc_options),
                            ):
                                try:
                                    payload = {
                                        "created_by": created_by,
                                        "reason": reason_u,
                                        "evidence": evidence_u or [],
                                        "logical_id": it["logical_id"],
                                        "expected_version": int(it["version"]),
                                        "creditor": creditor_u,
                                        "creditor_tax_id": creditor_tax_id_u or None,
                                        "contract_ref": contract_ref_u or None,
                                        "amount_total": float(amount_u),
                                        "outstanding_principal": float(outstanding_principal_u),
                                        "secured": bool(secured_u),
                                        "guarantee_details": guarantee_u or None,
                                        "maturity_date": maturity_u or None,
                                        "notes": notes_u or None,
                                    }
                                    client.update_situation_credit(case_id, payload)
                                    st.success("✅ Crédito actualizado (nueva versión creada)")
                                    st.session_state["evidence_link_cache"] = {}
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error actualizando crédito: {e}")
                else:
                    st.info("Aún no hay créditos. Crea el primero arriba.")

            # ----------------------------
            # BIENES
            # ----------------------------
            with tab_assets:
                st.subheader("🏠 Bienes")
                col_b1, col_b2, col_b3, col_b4, col_b5, col_b6 = st.columns([1, 2, 1, 1, 1, 1])
                with col_b1:
                    asset_type_filter = st.selectbox(
                        "Tipo (opcional)",
                        ["", "INMUEBLE", "VEHICULO", "MAQUINARIA_EQUIPO"],
                        index=0,
                        key="asset_filter_type",
                    )
                with col_b2:
                    asset_desc_filter = st.text_input(
                        "Descripción contiene (opcional)",
                        key="asset_filter_desc",
                        placeholder="Ej: nave, local, vehículo…",
                    )
                with col_b3:
                    asset_page_size = st.selectbox(
                        "Tamaño",
                        [10, 20, 50, 100],
                        index=1,
                        key="asset_filter_page_size",
                    )
                with col_b4:
                    asset_page = st.number_input(
                        "Página",
                        min_value=1,
                        value=1,
                        step=1,
                        key="asset_filter_page",
                    )
                with col_b5:
                    asset_include_history = st.checkbox(
                        "Histórico (todas)",
                        value=False,
                        key="asset_filter_include_history",
                        help="Si se activa, muestra todas las versiones. Si no, solo vigentes.",
                    )
                with col_b6:
                    st.caption(" ")
                try:
                    resp = client.list_situation_assets(
                        case_id,
                        include_history=bool(asset_include_history),
                        asset_type=asset_type_filter or None,
                        description=asset_desc_filter or None,
                        page=int(asset_page),
                        page_size=int(asset_page_size),
                    )
                    items = resp.get("items", [])
                    total = int(resp.get("total", 0) or 0)
                except Exception as e:
                    st.error(f"Error cargando bienes: {e}")
                    items = []
                    total = 0

                if st.button("⬇️ Exportar bienes (Excel)", key="export_assets_excel"):
                    try:
                        data = client.download_situation_assets_excel(case_id)
                        st.download_button(
                            "Descargar Excel",
                            data=data,
                            file_name=f"situation_assets_{case_id}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_assets_excel",
                        )
                    except Exception as e:
                        st.error(f"Error exportando Excel: {e}")

                with st.expander("➕ Añadir bien", expanded=False):
                    asset_type = st.selectbox(
                        "Tipo de bien",
                        ["INMUEBLE", "VEHICULO", "MAQUINARIA_EQUIPO"],
                        key="asset_type",
                    )
                    description = st.text_input("Descripción", key="asset_desc")
                    location = st.text_input("Ubicación/dirección (opcional)", key="asset_location")
                    val_ac = st.number_input(
                        "Tasación administración concursal (opcional)",
                        min_value=0.0,
                        value=0.0,
                        key="asset_val_ac",
                    )
                    val_ext = st.number_input(
                        "Tasación externa (opcional)",
                        min_value=0.0,
                        value=0.0,
                        key="asset_val_ext",
                    )
                    liens = st.text_area("Cargas/gravámenes (opcional)", key="asset_liens")
                    notes = st.text_area("Notas (opcional)", key="asset_notes")
                    reason = st.text_area("Motivo (obligatorio)", key="asset_reason")
                    evidence = _evidence_inputs("asset_create")

                    if st.button("💾 Crear bien", type="primary", disabled=not bool(doc_options)):
                        try:
                            payload = {
                                "created_by": created_by,
                                "reason": reason,
                                "evidence": evidence or [],
                                "asset_type": asset_type,
                                "description": description,
                                "location": location or None,
                                "valuation_admin_concursal": float(val_ac) if val_ac else None,
                                "valuation_external": float(val_ext) if val_ext else None,
                                "liens": liens or None,
                                "notes": notes or None,
                            }
                            client.create_situation_asset(case_id, payload)
                            st.success("✅ Bien creado")
                            st.session_state["evidence_link_cache"] = {}
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error creando bien: {e}")

                if items:
                    st.write(f"Mostrando **{len(items)}** de **{total}** bien(es).")
                    st.dataframe(
                        [
                            {
                                "asset_type": it["data"].get("asset_type"),
                                "description": it["data"].get("description"),
                                "val_ac": it["data"].get("valuation_admin_concursal"),
                                "val_ext": it["data"].get("valuation_external"),
                                "version": it.get("version"),
                                "evidence": it.get("evidence_count"),
                                "logical_id": it.get("logical_id"),
                            }
                            for it in items
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.markdown("---")
                    for it in items:
                        data = it.get("data", {}) or {}
                        with st.expander(
                            f"{data.get('asset_type')}: {data.get('description')} (v{it.get('version')})",
                            expanded=False,
                        ):
                            col_meta1, col_meta2 = st.columns([1, 1])
                            with col_meta1:
                                if st.button(
                                    "📎 Ver evidencia",
                                    key=f"asset_view_evidence_{it['record_id']}",
                                ):
                                    try:
                                        ev_resp = client.list_situation_record_evidence(
                                            case_id, entity="ASSET", record_id=it["record_id"]
                                        )
                                        ev_items = ev_resp.get("items", [])
                                        if not ev_items:
                                            st.info("Sin evidencia (no esperado en MVP).")
                                        else:
                                            st.dataframe(ev_items, use_container_width=True, hide_index=True)
                                    except Exception as e:
                                        st.error(f"Error cargando evidencia: {e}")
                            with col_meta2:
                                if st.button(
                                    "🧾 Ver auditoría",
                                    key=f"asset_view_audit_{it['record_id']}",
                                ):
                                    try:
                                        au_resp = client.list_situation_audit(
                                            case_id, entity="ASSET", logical_id=it["logical_id"]
                                        )
                                        au_items = au_resp.get("items", [])
                                        if not au_items:
                                            st.info("Sin auditoría.")
                                        else:
                                            st.dataframe(au_items, use_container_width=True, hide_index=True)
                                    except Exception as e:
                                        st.error(f"Error cargando auditoría: {e}")

                            with st.expander("➕ Añadir evidencia (sin crear versión)", expanded=False):
                                ev_reason_add = st.text_area(
                                    "Motivo (obligatorio)",
                                    key=f"asset_add_ev_reason_{it['record_id']}",
                                    placeholder="Ej: Se incorpora tasación/documento adicional del activo.",
                                )
                                ev_add = _evidence_inputs(f"asset_add_ev_{it['record_id']}")
                                if st.button(
                                    "💾 Añadir evidencia",
                                    key=f"asset_add_ev_btn_{it['record_id']}",
                                    disabled=not bool(doc_options),
                                ):
                                    try:
                                        payload = {
                                            "created_by": created_by,
                                            "reason": ev_reason_add,
                                            "evidence": ev_add or [],
                                        }
                                        client.add_situation_record_evidence(
                                            case_id,
                                            entity="ASSET",
                                            record_id=it["record_id"],
                                            payload=payload,
                                        )
                                        st.success("✅ Evidencia añadida")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error añadiendo evidencia: {e}")

                            desc_u = st.text_input(
                                "Descripción",
                                value=data.get("description") or "",
                                key=f"asset_u_desc_{it['record_id']}",
                            )
                            location_u = st.text_input(
                                "Ubicación/dirección (opcional)",
                                value=data.get("location") or "",
                                key=f"asset_u_location_{it['record_id']}",
                            )
                            reason_u = st.text_area(
                                "Motivo (obligatorio)",
                                key=f"asset_u_reason_{it['record_id']}",
                            )
                            evidence_u = _evidence_inputs(f"asset_update_{it['record_id']}")
                            if st.button(
                                "✅ Guardar nueva versión",
                                key=f"asset_u_btn_{it['record_id']}",
                                disabled=not bool(doc_options),
                            ):
                                try:
                                    payload = {
                                        "created_by": created_by,
                                        "reason": reason_u,
                                        "evidence": evidence_u or [],
                                        "logical_id": it["logical_id"],
                                        "expected_version": int(it["version"]),
                                        "description": desc_u,
                                        "location": location_u or None,
                                    }
                                    client.update_situation_asset(case_id, payload)
                                    st.success("✅ Bien actualizado (nueva versión creada)")
                                    st.session_state["evidence_link_cache"] = {}
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error actualizando bien: {e}")
                else:
                    st.info("Aún no hay bienes. Crea el primero arriba.")

            # ----------------------------
            # DEUDA PÚBLICA
            # ----------------------------
            with tab_pub:
                st.subheader("🏛️ Deuda pública")
                col_p1, col_p2, col_p3, col_p4, col_p5 = st.columns([1, 1, 1, 1, 1])
                with col_p1:
                    pub_auth_filter = st.selectbox(
                        "Organismo",
                        ["", "AEAT", "TGSS", "OTRO"],
                        index=0,
                        key="pub_filter_auth",
                    )
                with col_p2:
                    pub_deferred_filter = st.selectbox(
                        "Aplazada",
                        ["", "Sí", "No"],
                        index=0,
                        key="pub_filter_deferred",
                    )
                with col_p3:
                    pub_page_size = st.selectbox(
                        "Tamaño",
                        [10, 20, 50, 100],
                        index=1,
                        key="pub_filter_page_size",
                    )
                with col_p4:
                    pub_page = st.number_input(
                        "Página",
                        min_value=1,
                        value=1,
                        step=1,
                        key="pub_filter_page",
                    )
                with col_p5:
                    pub_include_history = st.checkbox(
                        "Histórico (todas)",
                        value=False,
                        key="pub_filter_include_history",
                    )
                try:
                    deferred_val = None
                    if pub_deferred_filter == "Sí":
                        deferred_val = True
                    elif pub_deferred_filter == "No":
                        deferred_val = False
                    resp = client.list_situation_public_debts(
                        case_id,
                        include_history=bool(pub_include_history),
                        authority=pub_auth_filter or None,
                        deferred=deferred_val,
                        page=int(pub_page),
                        page_size=int(pub_page_size),
                    )
                    items = resp.get("items", [])
                    total = int(resp.get("total", 0) or 0)
                except Exception as e:
                    st.error(f"Error cargando deudas públicas: {e}")
                    items = []
                    total = 0

                if st.button("⬇️ Exportar deuda pública (Excel)", key="export_public_debts_excel"):
                    try:
                        data = client.download_situation_public_debts_excel(case_id)
                        st.download_button(
                            "Descargar Excel",
                            data=data,
                            file_name=f"situation_public_debts_{case_id}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_public_debts_excel",
                        )
                    except Exception as e:
                        st.error(f"Error exportando Excel: {e}")

                with st.expander("➕ Añadir deuda pública", expanded=False):
                    authority = st.selectbox("Organismo", ["AEAT", "TGSS", "OTRO"], key="pub_auth")
                    concept = st.text_input("Concepto (opcional)", key="pub_concept")
                    period_start = st.text_input("Periodo inicio (YYYY-MM-DD, opcional)", key="pub_period_start")
                    period_end = st.text_input("Periodo fin (YYYY-MM-DD, opcional)", key="pub_period_end")
                    expediente_aplazamiento = st.text_input("Expediente aplazamiento (opcional)", key="pub_expediente")
                    amount_total = st.number_input("Importe", min_value=0.0, value=0.0, key="pub_amount")
                    deferred = st.checkbox("Aplazada/fraccionada", value=False, key="pub_deferred")
                    notes = st.text_area("Notas (opcional)", key="pub_notes")
                    reason = st.text_area("Motivo (obligatorio)", key="pub_reason")
                    evidence = _evidence_inputs("pub_create")

                    if st.button("💾 Crear deuda pública", type="primary", disabled=not bool(doc_options)):
                        try:
                            payload = {
                                "created_by": created_by,
                                "reason": reason,
                                "evidence": evidence or [],
                                "authority": authority,
                                "concept": concept or None,
                                "period_start": period_start or None,
                                "period_end": period_end or None,
                                "expediente_aplazamiento": expediente_aplazamiento or None,
                                "amount_total": float(amount_total),
                                "deferred": bool(deferred),
                                "notes": notes or None,
                            }
                            client.create_situation_public_debt(case_id, payload)
                            st.success("✅ Deuda pública creada")
                            st.session_state["evidence_link_cache"] = {}
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error creando deuda pública: {e}")

                if items:
                    st.write(f"Mostrando **{len(items)}** de **{total}** deuda(s).")
                    st.dataframe(
                        [
                            {
                                "authority": it["data"].get("authority"),
                                "amount_total": it["data"].get("amount_total"),
                                "deferred": it["data"].get("deferred"),
                                "version": it.get("version"),
                                "evidence": it.get("evidence_count"),
                                "logical_id": it.get("logical_id"),
                            }
                            for it in items
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("Aún no hay deudas públicas. Crea la primera arriba.")

            # ----------------------------
            # JUZGADO
            # ----------------------------
            with tab_court:
                st.subheader("🏛️ Juzgado / actuaciones")
                col_j1, col_j2, col_j3, col_j4, col_j5, col_j6 = st.columns([1, 2, 2, 1, 1, 1])
                with col_j1:
                    court_type_filter = st.selectbox(
                        "Tipo",
                        ["", "demanda", "monitorio", "ejecucion", "embargo", "resolucion", "otro"],
                        index=0,
                        key="court_filter_type",
                    )
                with col_j2:
                    court_proc_filter = st.text_input(
                        "Nº procedimiento contiene (opcional)",
                        key="court_filter_proc",
                    )
                with col_j3:
                    court_status_filter = st.text_input(
                        "Estado contiene (opcional)",
                        key="court_filter_status",
                    )
                with col_j4:
                    court_page_size = st.selectbox(
                        "Tamaño",
                        [10, 20, 50, 100],
                        index=1,
                        key="court_filter_page_size",
                    )
                with col_j5:
                    court_page = st.number_input(
                        "Página",
                        min_value=1,
                        value=1,
                        step=1,
                        key="court_filter_page",
                    )
                with col_j6:
                    court_include_history = st.checkbox(
                        "Histórico (todas)",
                        value=False,
                        key="court_filter_include_history",
                    )
                try:
                    resp = client.list_situation_court_records(
                        case_id,
                        include_history=bool(court_include_history),
                        action_type=court_type_filter or None,
                        procedure_number=court_proc_filter or None,
                        status=court_status_filter or None,
                        page=int(court_page),
                        page_size=int(court_page_size),
                    )
                    items = resp.get("items", [])
                    total = int(resp.get("total", 0) or 0)
                except Exception as e:
                    st.error(f"Error cargando actuaciones: {e}")
                    items = []
                    total = 0

                if st.button("⬇️ Exportar juzgado (Excel)", key="export_court_excel"):
                    try:
                        data = client.download_situation_court_records_excel(case_id)
                        st.download_button(
                            "Descargar Excel",
                            data=data,
                            file_name=f"situation_court_records_{case_id}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_court_excel",
                        )
                    except Exception as e:
                        st.error(f"Error exportando Excel: {e}")

                with st.expander("➕ Añadir actuación", expanded=False):
                    action_type = st.selectbox(
                        "Tipo",
                        ["demanda", "monitorio", "ejecucion", "embargo", "resolucion", "otro"],
                        key="court_action_type",
                    )
                    court = st.text_input("Juzgado (opcional)", key="court_name")
                    procedure_number = st.text_input("Nº procedimiento (opcional)", key="court_proc")
                    claimant = st.text_input("Demandante (opcional)", key="court_claimant")
                    amount_claimed = st.number_input(
                        "Importe reclamado (opcional)",
                        min_value=0.0,
                        value=0.0,
                        key="court_amount",
                    )
                    status_txt = st.text_input("Estado (opcional)", key="court_status")
                    stage = st.text_input("Fase/etapa procesal (opcional)", key="court_stage")
                    notes = st.text_area("Notas (opcional)", key="court_notes")
                    reason = st.text_area("Motivo (obligatorio)", key="court_reason")
                    evidence = _evidence_inputs("court_create")

                    if st.button("💾 Crear actuación", type="primary", disabled=not bool(doc_options)):
                        try:
                            payload = {
                                "created_by": created_by,
                                "reason": reason,
                                "evidence": evidence or [],
                                "action_type": action_type,
                                "court": court or None,
                                "procedure_number": procedure_number or None,
                                "claimant": claimant or None,
                                "amount_claimed": float(amount_claimed) if amount_claimed else None,
                                "status": status_txt or None,
                                "stage": stage or None,
                                "notes": notes or None,
                            }
                            client.create_situation_court_record(case_id, payload)
                            st.success("✅ Actuación creada")
                            st.session_state["evidence_link_cache"] = {}
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error creando actuación: {e}")

                if items:
                    st.write(f"Mostrando **{len(items)}** de **{total}** actuación(es).")
                    st.dataframe(
                        [
                            {
                                "action_type": it["data"].get("action_type"),
                                "court": it["data"].get("court"),
                                "procedure_number": it["data"].get("procedure_number"),
                                "amount_claimed": it["data"].get("amount_claimed"),
                                "status": it["data"].get("status"),
                                "version": it.get("version"),
                                "evidence": it.get("evidence_count"),
                                "logical_id": it.get("logical_id"),
                            }
                            for it in items
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("Aún no hay actuaciones. Crea la primera arriba.")

        # =========================================================
        # SUB_C: PLIEGOS (SUBMISSIONS) — MVP 1 plantilla
        # =========================================================
        with sub_c:
            st.subheader("⚖️ Pliegos / formularios (MVP)")
            st.caption(
                "Flujo: **Crear BORRADOR → Rellenar campos manuales → Validar → Congelar (snapshot) → Generar DOCX**."
            )

            template_code_default = "JUZ_SOL_CONCURSO_VOLUNTARIO_PJ"
            template_code = st.text_input(
                "template_code (puedes cambiarlo)",
                value=template_code_default,
                key="subm_template_code",
                help="Ej: JUZ_SOL_CONCURSO_VOLUNTARIO_PJ",
            ).strip() or template_code_default

            col_s1, col_s2 = st.columns([2, 1])
            with col_s1:
                submission_ref = st.text_input(
                    "Referencia (opcional: nº autos/expediente)",
                    key="subm_ref",
                    placeholder="Ej: Autos 123/2026",
                )
            with col_s2:
                created_by_subm = st.text_input(
                    "Usuario (created_by)",
                    value=st.session_state.get("situation_created_by", "abogado"),
                    key="subm_created_by",
                )

            if st.button("➕ Crear submission (BORRADOR)", type="primary", key="subm_create_btn"):
                try:
                    s = client.create_submission(
                        case_id,
                        {
                            "target": "JUZGADO",
                            "reference": submission_ref or None,
                            "created_by": created_by_subm,
                            "notes": None,
                        },
                    )
                    st.session_state["active_submission_id"] = s["submission_id"]
                    st.success(f"✅ Submission creada: {s['submission_id']}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error creando submission: {e}")

            active_submission_id = st.session_state.get("active_submission_id")
            st.write(f"**Submission activa:** `{active_submission_id or '—'}`")

            # Listado rápido de submissions
            try:
                subs = client.list_submissions(case_id, page=1, page_size=10)
                st.dataframe(subs.get("items", []), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Error listando submissions: {e}")

            if active_submission_id:
                st.markdown("---")
                st.subheader("1) Resolver plantilla (ver faltantes)")
                if st.button("🔎 Resolver", key="subm_resolve_btn"):
                    try:
                        res = client.resolve_submission_template(
                            case_id, active_submission_id, template_code=template_code
                        )
                        st.session_state["subm_last_resolve"] = res
                        st.success("✅ Plantilla resuelta")
                    except Exception as e:
                        st.error(f"Error resolviendo: {e}")

                res = st.session_state.get("subm_last_resolve")
                if res:
                    # UX: no mostrar preview técnico (keys tipo debtor.*, insolvency.*, totals.*) por defecto.
                    # Si se necesita, habilitarlo manualmente en modo avanzado.
                    missing = res.get("missing_required", [])
                    if res.get("warnings"):
                        st.info({"warnings": res.get("warnings")})

                st.markdown("---")
                # UX: ocultar el bloque de edición manual por defecto (evita “cajas” bajo el wizard).
                show_manual = st.toggle("Avanzado: editar campos manuales", value=False, key="subm_show_manual_fields")

                if show_manual:
                    st.subheader("1.5) Rellenar campos manuales (guardar)")
                    st.info("Deshabilitado por ahora para evitar volver a mostrar 'cajas' técnicas. Usar el wizard y el guardado.")

                st.markdown("---")
                st.subheader("2) Validar → Congelar → Generar")
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    if st.button("✅ Validar", key="subm_validate_btn"):
                        try:
                            v = client.validate_submission_template(
                                case_id, active_submission_id, template_code=template_code
                            )
                            st.session_state["subm_last_validate"] = v
                            if v.get("ok"):
                                st.success("PASS ✅")
                            else:
                                st.error(v.get("errors"))
                        except Exception as e:
                            st.error(f"Error validando: {e}")
                with col_b:
                    if st.button("📌 Congelar snapshot", key="subm_snapshot_btn"):
                        try:
                            s = client.snapshot_submission(
                                case_id, active_submission_id, template_code=template_code
                            )
                            st.session_state["subm_last_snapshot"] = s
                            st.success(f"✅ Snapshot creado: {s.get('snapshot_id')} ({s.get('created_items')})")
                        except Exception as e:
                            st.error(f"Error congelando: {e}")
                with col_c:
                    if st.button("📝 Generar DOCX", key="subm_generate_btn"):
                        try:
                            g = client.generate_submission_output(
                                case_id, active_submission_id, template_code=template_code
                            )
                            st.session_state["subm_last_generated"] = g.get("generated")
                            st.success("✅ Documento generado")
                        except Exception as e:
                            st.error(f"Error generando: {e}")

                gen = st.session_state.get("subm_last_generated")
                if gen:
                    st.markdown("---")
                    st.subheader("Descarga")
                    try:
                        data = client.download_generated_submission_doc(
                            case_id, active_submission_id, gen["generated_id"]
                        )
                        st.download_button(
                            "⬇️ Descargar DOCX",
                            data=data,
                            file_name=f"{template_code}_{case_id}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    except Exception as e:
                        st.error(f"Error descargando DOCX: {e}")

                st.markdown("---")
                st.subheader("3) Outputs del submission (multi-output)")
                try:
                    outs = client.list_generated_submission_docs(case_id, active_submission_id)
                except Exception as e:
                    outs = []
                    st.error(f"Error listando outputs: {e}")
                if outs:
                    st.dataframe(outs, use_container_width=True, hide_index=True)
                    for o in outs[:20]:
                        try:
                            data = client.download_generated_submission_doc(
                                case_id, active_submission_id, o["generated_id"]
                            )
                            st.download_button(
                                f"⬇️ Descargar {o.get('format')} {o.get('generated_id')[:8]}…",
                                data=data,
                                file_name=os.path.basename(o.get("storage_path") or f"{template_code}_{case_id}.docx"),
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                key=f"dl_{o.get('generated_id')}",
                            )
                        except Exception:
                            pass
                else:
                    st.info("Aún no hay outputs generados para esta submission.")

                st.markdown("---")
                st.subheader("4) Marcar PRESENTADO")
                presented_reason = st.text_area(
                    "Motivo/justificación (obligatorio)",
                    key="subm_presented_reason",
                    placeholder="Ej: Presentado en sede judicial / LexNET el día X.",
                ).strip()
                if st.button("📨 Marcar como PRESENTADO", key="subm_mark_presented_btn"):
                    try:
                        client.update_submission_status(
                            case_id,
                            active_submission_id,
                            status="PRESENTADO",
                            actor=created_by_subm,
                            reason=presented_reason,
                        )
                        st.success("✅ Status actualizado a PRESENTADO")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error marcando PRESENTADO: {e}")

# =========================================
# TAB 10: ADMINISTRADOR CONCURSAL (placeholder)
# =========================================
with tab10:
    st.header("🧑‍⚖️ Administrador Concursal")
    st.caption("Pestaña vacía (placeholder). Se implementará el flujo y documentos del Administrador Concursal.")

# =========================================
# FOOTER
# =========================================

st.markdown("---")
st.caption("⚖️ Phoenix Legal - Sistema de Análisis Legal Automatizado | v1.0.0")
st.caption(
    "⚠️ Este es un sistema de asistencia técnica. Requiere revisión por profesional legal cualificado."
)
