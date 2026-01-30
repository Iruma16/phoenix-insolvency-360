"""
UI MVP para Phoenix Legal conectada con FastAPI backend.

Versión refactorizada con componentes reutilizables y caché.
"""
import os
import inspect

import streamlit as st

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

# Configuración de la página
st.set_page_config(
    page_title="Phoenix Legal - MVP", page_icon="⚖️", layout="wide", initial_sidebar_state="expanded"
)

# Bump this cuando cambie la API del cliente (evita bugs por cache viejo)
CLIENT_API_VERSION = 3


# Inicializar cliente API
@st.cache_resource
def get_api_client(_v: int = CLIENT_API_VERSION):
    base_url = os.getenv("PHOENIX_API_BASE_URL")
    if not base_url:
        raise RuntimeError(
            "Falta PHOENIX_API_BASE_URL. Copia .env.example a .env y define PHOENIX_API_BASE_URL "
            "(ej: http://localhost:8000)."
        )
    return PhoenixLegalClient(base_url=base_url)


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


client = get_api_client()
# Fallback defensivo: si Streamlit reutiliza un cache antiguo del cliente,
# aseguramos que los métodos nuevos existan.
if not hasattr(client, "exclude_document") or not hasattr(client, "generate_economic_report"):
    base_url = os.getenv("PHOENIX_API_BASE_URL") or "http://localhost:8000"
    client = PhoenixLegalClient(base_url=base_url)

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
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
    [
        "🆕 Gestión de Casos",
        "📤 Documentos",
        "📊 Análisis Financiero",
        "⚠️ Alertas",
        "📄 Informe Económico",
        "🔍 Duplicados",
        "🚨 Riesgos Culpabilidad",
        "📚 Cuadro de situación",
    ]
)

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
    st.header("⚠️ Alertas (con síntesis del asistente)")

    if not st.session_state.get("selected_case_id"):
        st.warning("⚠️ Selecciona o crea un caso primero")
    else:
        case_id = st.session_state["selected_case_id"]

        sub_raw, sub_assistant = st.tabs(["🔎 Alertas técnicas (raw)", "🧠 Asistente (beta)"])

        with sub_assistant:
            st.subheader("🧠 Puntos a tener en cuenta (guardado en backend)")
            st.caption(
                "Esto se genera bajo demanda (botón Reanalizar) y queda guardado en el caso. "
                "Si entran documentos nuevos, verás que queda pendiente de reanalizar."
            )

            # Estado (si está generado / si hay docs nuevos / versionado)
            status_data = None
            try:
                status_data = client.get_alerts_voice_status(case_id)
            except Exception as e:
                st.error(f"No se pudo cargar el estado de alertas con voz: {e}")

            if status_data:
                c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 1.2])
                with c1:
                    st.markdown("**Estado**")
                    st.caption("Generado" if status_data.get("has_generated") else "No generado")
                with c2:
                    st.markdown("**Generado el**")
                    st.caption(status_data.get("generated_at") or "—")
                with c3:
                    st.markdown("**Docs nuevos**")
                    st.caption("Sí" if status_data.get("documents_newer_than_generation") else "No")
                with c4:
                    st.markdown("**Versión notas**")
                    st.caption(str(status_data.get("overrides_version") or 0))

                st.markdown("---")

                a1, a2 = st.columns([1.2, 2.8])
                with a1:
                    if st.button("🔄 Reanalizar (guardar)", type="primary", key="alerts_voice_generate"):
                        try:
                            with st.spinner("Generando alertas con voz (LLM+reglas, con fallback)..."):
                                client.generate_alerts_voice(case_id)
                            st.success("✅ Generado y guardado")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al reanalizar: {e}")
                with a2:
                    if status_data.get("documents_newer_than_generation"):
                        st.warning("Hay documentos nuevos desde la última generación. Conviene reanalizar.")
                    else:
                        st.caption("Sin cambios detectados en documentación desde la última generación.")

                if not status_data.get("has_generated"):
                    st.info("Pulsa **Reanalizar (guardar)** para generar la vista y dejarla lista para revisión.")
                else:
                    try:
                        bundle = client.get_alerts_voice(case_id)
                    except Exception as e:
                        bundle = None
                        st.error(f"No se pudo cargar el bundle guardado: {e}")

                    if bundle:
                        cards = list(bundle.get("cards") or [])
                        # Resumen ligero por relevancia
                        counts = {"ALTA": 0, "MEDIA": 0, "BAJA": 0}
                        for c in cards:
                            counts[str(c.get("relevance") or "MEDIA")] = counts.get(
                                str(c.get("relevance") or "MEDIA"), 0
                            ) + 1
                        st.write(
                            f"🟥 **{counts.get('ALTA',0)} punto(s) delicado(s)** · "
                            f"🟨 **{counts.get('MEDIA',0)} cosa(s) a revisar** · "
                            f"🟢 **{counts.get('BAJA',0)} detalle(s) menor(es)**"
                        )
                        st.markdown("---")

                        # Lista vertical (core)
                        for idx, c in enumerate(cards, 1):
                            card_id = str(c.get("card_id") or c.get("source_alert_id") or f"card_{idx}")
                            title = str(c.get("title_human") or "—")
                            domain = str(c.get("domain") or "DOCS")
                            rel = str(c.get("relevance") or "MEDIA")
                            status_txt = str(c.get("status") or "pendiente")
                            changed = bool(c.get("changed_since_last_review"))

                            badge = {"ALTA": "🟥", "MEDIA": "🟨", "BAJA": "🟢"}.get(rel, "🟨")
                            changed_badge = " · cambió desde revisión" if changed else ""

                            st.markdown(f"**{badge} {title}**  \n{domain} · {rel} · {status_txt}{changed_badge}")
                            st.write(str(c.get("summary_human") or ""))

                            b1, b2, b3, b4 = st.columns([1.0, 1.3, 1.4, 1.2])
                            with b1:
                                if st.button("✔️ Revisado", key=f"alerts_voice_review_{card_id}"):
                                    try:
                                        client.update_alerts_voice_card(
                                            case_id,
                                            card_id,
                                            {"status": "revisada", "updated_by": "abogado"},
                                        )
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"No se pudo actualizar: {e}")
                            with b2:
                                if st.button("⚠️ Para informe", key=f"alerts_voice_report_{card_id}"):
                                    try:
                                        client.update_alerts_voice_card(
                                            case_id,
                                            card_id,
                                            {"para_informe": True, "updated_by": "abogado"},
                                        )
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"No se pudo actualizar: {e}")
                            with b3:
                                if st.button("🚫 No relevante", key=f"alerts_voice_drop_{card_id}"):
                                    try:
                                        client.update_alerts_voice_card(
                                            case_id,
                                            card_id,
                                            {"status": "descartada", "updated_by": "abogado"},
                                        )
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"No se pudo actualizar: {e}")
                            with b4:
                                # Nota rápida (se edita en expander)
                                st.caption("")

                            with st.expander("🔽 Ver detalles", expanded=False):
                                ev_list = c.get("evidence") or []
                                if ev_list:
                                    st.write("**📄 Evidencias**")
                                    render_alert_evidence_list(evidence_list=ev_list, alert_id=card_id)
                                else:
                                    st.info("No hay evidencias enlazadas en este punto.")

                                st.markdown("")
                                st.write("**📌 Cosas que conviene aclarar**")
                                for it in (c.get("to_clarify") or [])[:8]:
                                    st.write(f"- {it}")

                                st.markdown("")
                                st.write("**🧭 Nota de contexto**")
                                st.caption(str(c.get("disclaimer_detail") or ""))

                                st.markdown("")
                                st.write("**📝 Nota del abogado**")
                                note_key = f"alerts_voice_note_{card_id}"
                                note_val = st.text_area(
                                    "Nota",
                                    value=str(c.get("lawyer_note") or ""),
                                    key=note_key,
                                    label_visibility="collapsed",
                                    placeholder="Añade una nota breve (por qué importa, a quién pedirlo, etc.)",
                                )
                                if st.button("💾 Guardar nota", key=f"alerts_voice_note_save_{card_id}"):
                                    try:
                                        client.update_alerts_voice_card(
                                            case_id,
                                            card_id,
                                            {"lawyer_note": note_val, "updated_by": "abogado"},
                                        )
                                        st.success("✅ Nota guardada")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"No se pudo guardar nota: {e}")

                            st.markdown("---")

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
            btn_kwargs = {"disabled": (not can_export)} if supports_disabled else {}
            if st.button("⬇️ Descargar PDF cliente", key="econ_pdf_v2", **btn_kwargs):
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
            btn_kwargs = {"disabled": (not can_export)} if supports_disabled else {}
            if st.button("📨 Enviar email", key="econ_email_send_v2", **btn_kwargs):
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
        def _render_right_panel():
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
                _render_right_panel()

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
                _render_right_panel()

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
                _render_right_panel()

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

        except Exception as e:
            st.error(f"Error al cargar duplicados: {e}")

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
    st.header("📚 Cuadro de situación")

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

        sub_a, sub_b, sub_c = st.tabs(
            ["🔎 Buscador documental", "🗃️ Base de datos (Cuadro de situación)", "⚖️ Pliegos (Juzgado/AC)"]
        )

        with sub_a:
            st.subheader("🔎 Buscador documental (abogado-friendly)")

            # Estado UI
            if "doc_search_category" not in st.session_state:
                st.session_state["doc_search_category"] = "OTROS"

            # Nota: el usuario (added_by) se define arriba (compartido entre sub-tabs)

            # Categorías rápidas
            st.write("**Filtros rápidos:**")
            c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns(9)
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

            category = st.session_state.get("doc_search_category", "OTROS")
            st.caption(f"Categoría activa: **{category}** (se ignora si eliges doc_types)")

            run = st.button("🔎 Buscar", type="primary")
            if run:
                try:
                    resp = client.search_documents(
                        case_id,
                        q=q or None,
                        category=category if not selected_types else None,
                        doc_types=selected_types or None,
                        include_chunk_id=True,
                        page=int(page),
                        page_size=int(page_size),
                    )
                    items = resp.get("items", [])
                    total = resp.get("total", 0)

                    st.success(f"✅ Resultados: {len(items)} (total: {total})")

                    if items:
                        # Tabla compacta
                        rows = []
                        for it in items:
                            rows.append(
                                {
                                    "filename": it.get("filename"),
                                    "doc_type": it.get("doc_type"),
                                    "created_at": it.get("created_at"),
                                    "source": it.get("source"),
                                    "page": it.get("page"),
                                    "confidence": it.get("confidence"),
                                    "chunk_id": it.get("chunk_id"),
                                    "document_id": it.get("document_id"),
                                }
                            )
                        st.dataframe(rows, use_container_width=True, hide_index=True)

                        st.markdown("---")
                        st.subheader("👁️ Vista rápida (snippets)")
                        for it in items[:25]:
                            label = f"{it.get('filename')} — {it.get('doc_type')} (pág. {it.get('page') or '—'})"
                            with st.expander(label, expanded=False):
                                st.write(f"**Document ID:** `{it.get('document_id')}`")
                                if it.get("chunk_id"):
                                    st.write(f"**Chunk ID:** `{it.get('chunk_id')}`")
                                st.write(f"**Confianza:** {it.get('confidence')}")
                                sn = it.get("snippet")
                                if sn:
                                    st.write(sn)
                                else:
                                    st.info("Sin snippet disponible (no hay chunks o contenido vacío).")

                                st.markdown("---")
                                st.subheader("🧾 Añadir como evidencia (CAPA 3)")

                                # Fuente: desde el buscador, por defecto es evidencia documental.
                                source_type = "DOCUMENTO"
                                certainty_level = "CONSTA"

                                # Destino
                                dest = st.radio(
                                    "Destino de la evidencia",
                                    options=["General del caso (no enlazada)", "Enlazar a un registro (Cuadro de situación)"],
                                    key=f"ev_dest_{it.get('document_id')}_{it.get('chunk_id') or 'nochunk'}",
                                )

                                record_type = "other"
                                record_id = None

                                if dest.startswith("Enlazar"):
                                    record_type = st.selectbox(
                                        "record_type (canónico)",
                                        options=["invoice", "loan", "asset", "public_debt", "court_claim", "form_field"],
                                        key=f"ev_rt_{it.get('document_id')}_{it.get('chunk_id') or 'nochunk'}",
                                    )

                                    # Buscador global server-side + paginación real (sin hacks de filtrar local).
                                    link_q = st.text_input(
                                        "Buscar destino (global)",
                                        value="",
                                        key=f"ev_link_q_{record_type}_{it.get('document_id')}_{it.get('chunk_id') or 'nochunk'}",
                                        placeholder="Ej: proveedor, nº factura, acreedor, concepto AEAT, autos…",
                                    )
                                    col_p1, col_p2 = st.columns([1, 1])
                                    with col_p1:
                                        link_page = st.number_input(
                                            "Página destino",
                                            min_value=1,
                                            value=1,
                                            step=1,
                                            key=f"ev_link_page_{record_type}_{it.get('document_id')}_{it.get('chunk_id') or 'nochunk'}",
                                        )
                                    with col_p2:
                                        link_page_size = st.selectbox(
                                            "Tamaño destino",
                                            options=[20, 50, 100],
                                            index=0,
                                            key=f"ev_link_ps_{record_type}_{it.get('document_id')}_{it.get('chunk_id') or 'nochunk'}",
                                        )

                                    if "evidence_link_cache" not in st.session_state:
                                        st.session_state["evidence_link_cache"] = {}

                                    if st.button(
                                        "🔄 Refrescar destinos (limpiar caché)",
                                        key=f"ev_link_refresh_{it.get('document_id')}_{it.get('chunk_id') or 'nochunk'}",
                                    ):
                                        st.session_state["evidence_link_cache"] = {}

                                    cache_key = f"{case_id}:{record_type}:{(link_q or '').strip()}:{int(link_page)}:{int(link_page_size)}"
                                    cached = st.session_state["evidence_link_cache"].get(cache_key)
                                    if cached is None:
                                        try:
                                            cached = client.list_situation_link_targets(
                                                case_id,
                                                record_type=record_type,
                                                q=link_q or None,
                                                page=int(link_page),
                                                page_size=int(link_page_size),
                                            )
                                        except Exception:
                                            cached = {"items": [], "total": 0, "page": int(link_page), "page_size": int(link_page_size)}
                                        st.session_state["evidence_link_cache"][cache_key] = cached

                                    total2 = int(cached.get("total", 0) or 0)
                                    st.caption(f"Destinos: {len(cached.get('items', []) or [])} (total: {total2})")

                                    display_map: dict[str, str] = {}
                                    for row in cached.get("items", []) or []:
                                        rid = row.get("record_id")
                                        label = row.get("label")
                                        if not rid or not label:
                                            continue
                                        disp = f"{label} [{str(rid)[:8]}…]"
                                        display_map[disp] = rid

                                    if not display_map:
                                        st.warning("No hay resultados para enlazar con esos filtros.")
                                    else:
                                        sel = st.selectbox(
                                            "Registro destino",
                                            options=list(display_map.keys()),
                                            key=f"ev_rec_{record_type}_{it.get('document_id')}_{it.get('chunk_id') or 'nochunk'}",
                                        )
                                        record_id = display_map.get(sel)
                                else:
                                    record_type = st.selectbox(
                                        "record_type (canónico)",
                                        options=["other", "invoice", "loan", "asset", "public_debt", "court_claim", "form_field"],
                                        index=0,
                                        key=f"ev_rt_general_{it.get('document_id')}_{it.get('chunk_id') or 'nochunk'}",
                                    )
                                    record_id = None

                                # Excerpt (<= 300 chars)
                                # Nota: el snippet ahora solo se autocompleta si proviene de match real
                                # (chunk match o raw_text match). Si no, exige excerpt manual.
                                auto_excerpt = (sn or "").strip()
                                if auto_excerpt:
                                    auto_excerpt = auto_excerpt[:300]
                                excerpt = st.text_area(
                                    "Excerpt (<= 300 chars)",
                                    value=auto_excerpt,
                                    key=f"ev_excerpt_{it.get('document_id')}_{it.get('chunk_id') or 'nochunk'}",
                                    placeholder="Si no hay snippet, pega aquí un extracto breve (máx. 300 caracteres).",
                                ).strip()
                                if len(excerpt) > 300:
                                    st.error("El excerpt excede 300 caracteres.")

                                justification = st.text_area(
                                    "Justificación (obligatoria, mínimo 10 chars)",
                                    key=f"ev_just_{it.get('document_id')}_{it.get('chunk_id') or 'nochunk'}",
                                    placeholder="Por qué este documento/extracto soporta el hecho o la anotación.",
                                ).strip()

                                can_save = True
                                if len(justification) < 10:
                                    can_save = False
                                if not auto_excerpt and len(excerpt) < 10:
                                    can_save = False
                                if len(excerpt) > 300:
                                    can_save = False
                                if dest.startswith("Enlazar") and not record_id:
                                    can_save = False

                                if st.button(
                                    "➕ Guardar evidencia",
                                    key=f"ev_save_{it.get('document_id')}_{it.get('chunk_id') or 'nochunk'}",
                                    disabled=not can_save,
                                ):
                                    try:
                                        payload = {
                                            "record_type": record_type,
                                            "record_id": record_id,
                                            "source_type": source_type,
                                            "certainty_level": certainty_level,
                                            "justification": justification,
                                            "document_id": it.get("document_id"),
                                            "chunk_id": it.get("chunk_id"),
                                            "page": it.get("page"),
                                            "excerpt": excerpt or None,
                                            "added_by": st.session_state.get("situation_created_by", "abogado"),
                                        }
                                        out = client.create_case_evidence(case_id, payload)
                                        st.success(f"✅ Evidencia guardada: {out.get('evidence_id')}")
                                    except Exception as e:
                                        st.error(f"Error guardando evidencia: {e}")
                    else:
                        st.info("Sin resultados con esos filtros.")

                except Exception as e:
                    st.error(f"Error en búsqueda: {e}")

        with sub_b:
            st.subheader("🗃️ Base de datos (Cuadro de situación)")
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
                    st.write("**Campos resueltos (preview):**")
                    st.json(res.get("resolved_fields", {}))
                    missing = res.get("missing_required", [])
                    if missing:
                        st.warning(f"Faltan campos requeridos: {missing}")
                    if res.get("warnings"):
                        st.info({"warnings": res.get("warnings")})

                st.markdown("---")
                st.subheader("1.5) Rellenar campos manuales (guardar)")
                st.caption("Sugerencia: si no consta un dato, escribe **NO CONSTA** y guarda.")

                if st.button("🔄 Cargar campos", key="subm_load_fields_btn"):
                    try:
                        tf = client.get_template_fields(case_id, template_code)
                        st.session_state["subm_template_fields"] = tf
                        st.success("✅ Campos cargados")
                    except Exception as e:
                        st.error(f"Error cargando campos: {e}")

                tf = st.session_state.get("subm_template_fields")
                if tf:
                    fields = tf.get("fields", [])
                    required_missing = [
                        f for f in fields if f.get("required") and not f.get("value_json")
                    ]
                    if required_missing:
                        st.warning(
                            f"Campos requeridos sin valor manual: {[f.get('field_key') for f in required_missing]}"
                        )

                    with st.form("subm_manual_fields_form"):
                        # Render mínimo (MVP): mostrar solo campos requeridos manuales + algunos opcionales útiles
                        editable_keys = {
                            "debtor.tax_id",
                            "debtor.address",
                            "insolvency.kind",
                            "insolvency.facts",
                            "workers.count",
                            "totals.cash",
                            # opcionales
                            "debtor.register_data",
                            "debtor.object_activity",
                            "company.ceased_activity",
                        }
                        by_key = {f.get("field_key"): f for f in fields}
                        values_payload = []

                        def _current_text(k: str) -> str:
                            v = (by_key.get(k) or {}).get("value_json") or {}
                            return str(v.get("text", v.get("value", "")) or "")

                        def _current_number(k: str) -> float:
                            v = (by_key.get(k) or {}).get("value_json") or {}
                            try:
                                return float(v.get("number", v.get("value", 0.0)) or 0.0)
                            except Exception:
                                return 0.0

                        st.write("**Datos del deudor**")
                        debtor_tax_id = st.text_input("CIF", value=_current_text("debtor.tax_id"), key="mf_debtor_tax")
                        debtor_address = st.text_input(
                            "Domicilio social", value=_current_text("debtor.address"), key="mf_debtor_addr"
                        )
                        debtor_reg = st.text_input(
                            "Datos registrales (opcional)",
                            value=_current_text("debtor.register_data"),
                            key="mf_debtor_reg",
                        )
                        debtor_act = st.text_input(
                            "Objeto / actividad (opcional)",
                            value=_current_text("debtor.object_activity"),
                            key="mf_debtor_act",
                        )

                        st.write("**Insolvencia**")
                        _insolv_current = (_current_text("insolvency.kind") or "ACTUAL").strip().upper()
                        _insolv_opts = ["ACTUAL", "INMINENTE", "NO CONSTA"]
                        insolv_kind = st.selectbox(
                            "Clase de insolvencia",
                            options=_insolv_opts,
                            index=_insolv_opts.index(_insolv_current) if _insolv_current in _insolv_opts else 0,
                            key="mf_ins_kind",
                        )
                        insolv_facts = st.text_area(
                            "Hechos (breve)",
                            value=_current_text("insolvency.facts"),
                            height=120,
                            key="mf_ins_facts",
                        )
                        _ceased_current = (_current_text("company.ceased_activity") or "").strip().upper()
                        _ceased_opts = ["", "SI", "NO", "NO CONSTA"]
                        ceased_activity = st.selectbox(
                            "¿Ha cesado actividad? (opcional)",
                            options=_ceased_opts,
                            index=_ceased_opts.index(_ceased_current) if _ceased_current in _ceased_opts else 0,
                            key="mf_ceased",
                        )

                        st.write("**Magnitudes**")
                        workers_count = st.number_input(
                            "Nº trabajadores",
                            value=_current_number("workers.count"),
                            min_value=0.0,
                            step=1.0,
                            key="mf_workers",
                        )
                        cash_total = st.number_input(
                            "Tesorería",
                            value=_current_number("totals.cash"),
                            min_value=0.0,
                            step=100.0,
                            key="mf_cash",
                        )

                        updated_by = st.text_input("updated_by", value=created_by_subm, key="mf_updated_by")

                        submitted = st.form_submit_button("💾 Guardar valores")
                        if submitted:
                            try:
                                values_payload = []
                                if debtor_tax_id.strip():
                                    values_payload.append(
                                        {"field_key": "debtor.tax_id", "value_json": {"text": debtor_tax_id.strip()}, "updated_by": updated_by}
                                    )
                                if debtor_address.strip():
                                    values_payload.append(
                                        {"field_key": "debtor.address", "value_json": {"text": debtor_address.strip()}, "updated_by": updated_by}
                                    )
                                if debtor_reg.strip():
                                    values_payload.append(
                                        {"field_key": "debtor.register_data", "value_json": {"text": debtor_reg.strip()}, "updated_by": updated_by}
                                    )
                                if debtor_act.strip():
                                    values_payload.append(
                                        {"field_key": "debtor.object_activity", "value_json": {"text": debtor_act.strip()}, "updated_by": updated_by}
                                    )
                                values_payload.append(
                                    {"field_key": "insolvency.kind", "value_json": {"text": insolv_kind}, "updated_by": updated_by}
                                )
                                if insolv_facts.strip():
                                    values_payload.append(
                                        {"field_key": "insolvency.facts", "value_json": {"text": insolv_facts.strip()}, "updated_by": updated_by}
                                    )
                                if ceased_activity:
                                    values_payload.append(
                                        {"field_key": "company.ceased_activity", "value_json": {"text": ceased_activity}, "updated_by": updated_by}
                                    )
                                values_payload.append(
                                    {"field_key": "workers.count", "value_json": {"number": float(workers_count)}, "updated_by": updated_by}
                                )
                                values_payload.append(
                                    {"field_key": "totals.cash", "value_json": {"number": float(cash_total)}, "updated_by": updated_by}
                                )

                                if not values_payload:
                                    st.warning("No hay cambios para guardar.")
                                else:
                                    client.upsert_template_values(case_id, template_code, {"values": values_payload})
                                    st.success("✅ Valores guardados")
                                    # recargar campos para reflejar
                                    tf2 = client.get_template_fields(case_id, template_code)
                                    st.session_state["subm_template_fields"] = tf2
                            except Exception as e:
                                st.error(f"Error guardando valores: {e}")

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
# FOOTER
# =========================================

st.markdown("---")
st.caption("⚖️ Phoenix Legal - Sistema de Análisis Legal Automatizado | v1.0.0")
st.caption(
    "⚠️ Este es un sistema de asistencia técnica. Requiere revisión por profesional legal cualificado."
)
