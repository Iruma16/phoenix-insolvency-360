"""
UI MVP para Phoenix Legal conectada con FastAPI backend.

Versión refactorizada con componentes reutilizables y caché.
"""
import os

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


# Inicializar cliente API
@st.cache_resource
def get_api_client():
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

# =========================================
# PANTALLA PRINCIPAL
# =========================================

# Tabs principales
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
    [
        "🆕 Gestión de Casos",
        "📤 Documentos",
        "📊 Análisis Financiero",
        "⚠️ Alertas",
        "📄 Informe Legal",
        "🔍 Duplicados",
        "🚨 Riesgos Culpabilidad",
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

                    if result.get("errors"):
                        st.warning(f"⚠️ {len(result['errors'])} error(es)")
                        for error in result["errors"]:
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
                    status_color = {"ingested": "🟢", "pending": "🟡", "failed": "🔴"}.get(
                        doc["status"], "⚪"
                    )

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
    st.header("⚠️ Alertas Técnicas")

    if not st.session_state.get("selected_case_id"):
        st.warning("⚠️ Selecciona o crea un caso primero")
    else:
        case_id = st.session_state["selected_case_id"]

        if st.button("🔍 Verificar Alertas", type="primary"):
            try:
                with st.spinner("Analizando calidad de datos..."):
                    alerts = client.get_analysis_alerts(case_id)

                if alerts:
                    st.warning(f"⚠️ Se detectaron {len(alerts)} alerta(s)")

                    for alert in alerts:
                        severity_color = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(
                            alert["severity"], "⚪"
                        )

                        with st.expander(f"{severity_color} {alert['alert_type']}"):
                            st.write(f"**Mensaje:** {alert['message']}")
                            if alert.get("evidence"):
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

                    st.success("✅ Informe generado")

                    st.subheader("📋 Resumen del Informe")
                    st.write(f"**ID del Informe:** `{report['report_id']}`")
                    st.write(f"**Generado:** {report['generated_at']}")
                    st.write(f"**Hallazgos:** {len(report.get('findings', []))}")

                    if report.get("findings"):
                        st.subheader("🔍 Hallazgos Principales")
                        findings = report["findings"]
                        for i, finding in enumerate(findings, 1):
                            with st.expander(f"{i}. {finding.get('title', 'Sin título')}"):
                                st.write(finding.get("description", "Sin descripción"))
                                if finding.get("evidence"):
                                    st.write(
                                        f"**Evidencia:** {len(finding['evidence'])} documento(s)"
                                    )

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
                        mime="application/pdf",
                    )
                    st.success("✅ PDF generado")
                except Exception as e:
                    st.error(f"Error al descargar PDF: {e}")

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
# FOOTER
# =========================================

st.markdown("---")
st.caption("⚖️ Phoenix Legal - Sistema de Análisis Legal Automatizado | v1.0.0")
st.caption(
    "⚠️ Este es un sistema de asistencia técnica. Requiere revisión por profesional legal cualificado."
)
