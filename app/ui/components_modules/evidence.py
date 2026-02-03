"""
Componente de visualización de evidencias.

Renderiza evidencias probatorias con trazabilidad completa.
"""
from typing import Any

import streamlit as st


def render_evidence_expander(evidence: dict[str, Any], label: str = "🔍 Ver Evidencia"):
    """
    Renderiza un expander con la evidencia completa.

    Muestra:
    - Documento fuente
    - Página
    - Fragmento extraído
    - Método de extracción
    - Confianza

    Args:
        evidence: Dict con evidence (document_id, filename, page, excerpt, etc.)
        label: Texto del expander
    """
    if not evidence:
        return

    with st.expander(label):
        st.write(f"**📄 Documento:** `{evidence.get('filename', 'N/A')}`")

        if evidence.get("page"):
            st.write(f"**📖 Página:** {evidence['page']}")

        if evidence.get("document_id"):
            st.caption(f"ID: `{evidence['document_id'][:12]}...`")

        if evidence.get("excerpt"):
            st.write("**📝 Fragmento extraído:**")
            st.code(evidence["excerpt"], language=None)

        # Metadatos técnicos
        method = evidence.get("extraction_method", "N/A")
        confidence = evidence.get("extraction_confidence", 0)
        st.caption(f"Método: {method} | Confianza extracción: {confidence:.0%}")


def render_alert_evidence_list(evidence_list: list[dict[str, Any]], alert_id: str):
    """
    Renderiza una lista completa de evidencias de una alerta.

    Muestra todas las evidencias agrupadas con metadata completa para
    trazabilidad legal.

    Args:
        evidence_list: Lista de diccionarios de evidencia
        alert_id: ID de la alerta (para keys únicas de Streamlit)
    """
    if not evidence_list:
        st.info("ℹ️ No hay evidencias disponibles para esta alerta")
        return

    st.write(f"**📂 Total de evidencias:** {len(evidence_list)}")
    st.markdown("---")

    for idx, ev in enumerate(evidence_list, 1):
        with st.expander(
            f"📄 Evidencia #{idx}: {ev.get('filename', 'Documento sin nombre')}",
            expanded=(idx == 1),
        ):
            # Información del documento
            col1, col2 = st.columns(2)

            with col1:
                st.write("**📄 Documento:**")
                st.code(ev.get("filename", "N/A"), language=None)

                if ev.get("document_id"):
                    st.caption(f"Doc ID: `{ev['document_id'][:16]}...`")

                if ev.get("chunk_id"):
                    st.caption(f"Chunk ID: `{ev['chunk_id'][:16]}...`")

            with col2:
                st.write("**📍 Ubicación:**")

                # Información de página
                location = ev.get("location", {})
                if location.get("page_start"):
                    if location.get("page_end") and location["page_end"] != location["page_start"]:
                        st.write(f"📖 Páginas: {location['page_start']}-{location['page_end']}")
                    else:
                        st.write(f"📖 Página: {location['page_start']}")

                # Offsets de caracteres
                if location.get("start_char") is not None and location.get("end_char") is not None:
                    st.caption(f"Caracteres: {location['start_char']}-{location['end_char']}")

                # Método de extracción
                if location.get("extraction_method"):
                    st.caption(f"Método: `{location['extraction_method']}`")

            # Contenido de la evidencia
            if ev.get("content"):
                st.write("**📝 Contenido extraído:**")
                content = ev["content"]

                # Limitar longitud si es muy largo
                if len(content) > 1000:
                    st.code(
                        content[:1000]
                        + "\n\n[... texto truncado, mostrando primeros 1000 caracteres ...]",
                        language=None,
                    )
                    with st.expander("Ver texto completo"):
                        st.code(content, language=None)
                else:
                    st.code(content, language=None)

            st.markdown("")
