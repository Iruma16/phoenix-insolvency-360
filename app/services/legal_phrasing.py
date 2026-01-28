"""
REGLA 3: UX / legal phrasing controlado.

Define salidas estándar con lenguaje jurídico prudente y consistente.
NO creativo. NO comercial. NO afirmaciones rotundas sin evidencia.
"""

from typing import Any, Literal

ResponseType = Literal[
    "RESPUESTA_CON_EVIDENCIA",
    "EVIDENCIA_INSUFICIENTE",
    "INFORMACION_PARCIAL_NO_CONCLUYENTE",
]


# =========================================================
# PLANTILLAS DE RESPUESTA CONTROLADAS
# =========================================================


def get_insufficient_evidence_message(motivo: str) -> str:
    """
    REGLA 3: Mensaje estándar para evidencia insuficiente.

    Lenguaje jurídico prudente. NO categórico.
    """
    return (
        f"No se ha localizado evidencia suficiente en la documentación aportada "
        f"para responder a esta consulta de forma fundamentada.\n\n"
        f"Motivo técnico: {motivo}\n\n"
        f"Se recomienda:\n"
        f"- Aportar documentación adicional relevante para la consulta.\n"
        f"- Reformular la pregunta con mayor especificidad.\n"
        f"- Consultar manualmente los documentos si existe sospecha de que la información está presente."
    )


def get_partial_information_message(
    *,
    confidence_score: float,
    num_chunks: int,
) -> str:
    """
    REGLA 3: Mensaje estándar para información parcial.

    Lenguaje prudente. Advierte limitaciones.
    """
    return (
        f"⚠️ ADVERTENCIA: Información parcial o no concluyente.\n\n"
        f"La documentación aportada contiene {num_chunks} fragmento(s) potencialmente relevante(s), "
        f"pero el nivel de confianza es limitado (score: {confidence_score:.2f}/1.00).\n\n"
        f"La respuesta siguiente debe interpretarse con PRUDENCIA y verificarse manualmente "
        f"antes de considerarla definitiva para efectos legales.\n\n"
        f"Se recomienda contrastar con la documentación original antes de tomar decisiones."
    )


def format_sources_citation(sources: list[dict[str, Any]]) -> str:
    """
    CORRECCIÓN D: Formatea citas visibles de sources.

    Incluye referencias EXACTAS a chunk_id, filename, page, offsets.
    """
    if not sources:
        return ""

    # CERTIFICACIÓN 2: Chunks citados en salida final
    cited_chunk_ids = [s.get("chunk_id", "N/A") for s in sources]
    print(f"[CERT] CITED_CHUNKS = {cited_chunk_ids}")

    citations = ["\n\n" + "=" * 80 + "\nFUENTES DOCUMENTALES CITADAS:\n" + "=" * 80]

    for i, source in enumerate(sources, 1):
        chunk_id = source.get("chunk_id", "N/A")
        filename = source.get("filename", source.get("document_id", "N/A"))
        page = source.get("page")
        start_char = source.get("start_char")
        end_char = source.get("end_char")
        section_hint = source.get("section_hint")
        similarity = source.get("similarity_score")

        citation = f"\n[{i}] Fuente:"
        citation += f"\n    • Documento: {filename}"

        if chunk_id and chunk_id != "N/A":
            citation += (
                f"\n    • Chunk ID: {chunk_id[:32]}..."
                if len(chunk_id) > 32
                else f"\n    • Chunk ID: {chunk_id}"
            )

        if page is not None:
            citation += f"\n    • Página: {page}"

        if start_char is not None and end_char is not None:
            citation += f"\n    • Posición: caracteres {start_char}-{end_char}"

        if section_hint:
            citation += f"\n    • Sección: {section_hint}"

        if similarity is not None:
            citation += f"\n    • Relevancia: {similarity:.3f}"

        citations.append(citation)

    citations.append("\n" + "=" * 80)
    return "\n".join(citations)


def wrap_response_with_evidence_notice(
    *,
    answer: str,
    confidence_score: float,
    sources: list[dict[str, Any]],
) -> str:
    """
    REGLA 3: Envuelve respuesta del LLM con aviso de evidencia.
    CORRECCIÓN D: Incluye citas visibles de sources.

    Ajusta lenguaje según nivel de confianza:
    - Alta (>= 0.8): Lenguaje estándar
    - Media (0.6-0.8): Lenguaje prudente
    - Baja (< 0.6): Lenguaje muy prudente con advertencias
    """
    num_sources = len(sources)

    if confidence_score >= 0.8:
        # Alta confianza: respuesta estándar con evidencia
        header = (
            f"Respuesta fundamentada en {num_sources} fuente(s) documental(es) "
            f"con nivel de confianza alto (score: {confidence_score:.2f}/1.00):\n\n"
        )
        footer = (
            "\n\nNota: Esta respuesta se basa exclusivamente en la documentación analizada. "
            "Se recomienda verificar las fuentes citadas."
        )

    elif confidence_score >= 0.6:
        # Confianza media: lenguaje prudente
        header = (
            f"⚠️ Respuesta con nivel de confianza medio (score: {confidence_score:.2f}/1.00).\n\n"
            f"Basada en {num_sources} fuente(s) documental(es). "
            f"Se recomienda interpretar con prudencia:\n\n"
        )
        footer = (
            "\n\n⚠️ ADVERTENCIA: Esta respuesta se basa en evidencia con limitaciones. "
            "Es RECOMENDABLE verificar manualmente la documentación original antes de "
            "considerar esta información como definitiva para efectos legales."
        )

    else:
        # Confianza baja: lenguaje muy prudente
        header = (
            f"⚠️⚠️ Respuesta con nivel de confianza BAJO (score: {confidence_score:.2f}/1.00).\n\n"
            f"Basada en {num_sources} fuente(s) documental(es) con relevancia limitada. "
            f"INTERPRETAR CON MÁXIMA PRUDENCIA:\n\n"
        )
        footer = (
            "\n\n⚠️⚠️ ADVERTENCIA CRÍTICA: Esta respuesta se basa en evidencia débil o inconsistente. "
            "NO debe considerarse concluyente. Es OBLIGATORIO verificar manualmente la "
            "documentación original antes de tomar decisiones basadas en esta información."
        )

    # CORRECCIÓN D: Agregar citas visibles
    citations = format_sources_citation(sources)

    return header + answer + footer + citations


def get_response_type_from_policy_decision(
    *,
    cumple_politica: bool,
    confidence_score: float,
    hallucination_risk: bool = False,
) -> ResponseType:
    """
    Determina el tipo de respuesta según política, score y riesgo de alucinación.

    REGLA 3: Clasificación estándar de salidas.
    CORRECCIÓN C: Si hallucination_risk=True → NUNCA RESPUESTA_CON_EVIDENCIA.
    """
    if not cumple_politica:
        return "EVIDENCIA_INSUFICIENTE"

    # CORRECCIÓN C: Alto riesgo de alucinación → forzar información parcial
    if hallucination_risk:
        return "INFORMACION_PARCIAL_NO_CONCLUYENTE"

    if confidence_score >= 0.6:
        return "RESPUESTA_CON_EVIDENCIA"
    else:
        return "INFORMACION_PARCIAL_NO_CONCLUYENTE"


def print_response_type_decision(
    response_type: ResponseType,
    confidence_score: float,
) -> None:
    """
    REGLA 5: Decisión trazable por stdout.
    """
    print(f"\n{'='*80}")
    print(f"[PHRASING] Tipo de respuesta: {response_type}")
    print(f"[PHRASING] Confidence score: {confidence_score:.3f}")

    if response_type == "RESPUESTA_CON_EVIDENCIA":
        print(f"[PHRASING] Lenguaje: {'Estándar' if confidence_score >= 0.8 else 'Prudente'}")
    elif response_type == "EVIDENCIA_INSUFICIENTE":
        print("[PHRASING] Lenguaje: Mensaje estándar de evidencia insuficiente")
    else:
        print("[PHRASING] Lenguaje: Advertencia de información parcial")

    print(f"{'='*80}\n")
