from __future__ import annotations

"""
Lógica del Agente 2: Prosecutor (Fiscal Concursal).

Este agente actúa como un administrador concursal hostil.
No interpreta de forma benévola: busca indicios de calificación culpable.
"""

from typing import List
from datetime import date

from sqlalchemy.orm import Session

from app.rag.case_rag.retrieve import rag_answer_internal
from app.rag.legal_rag.service import query_legal_rag
from app.agents.base.response_builder import build_llm_answer
from app.core.database import get_session_factory

from .schema import (
    ProsecutorResult,
    LegalAccusation,
    Evidence,
    RiskLevel,
    LegalGround,
)


# ============================
# PREGUNTAS HOSTILES BASE
# ============================

HOSTILE_QUESTIONS: dict[str, str] = {
    "retraso_concurso": (
        "¿Cuándo se produjo la insolvencia real según balances y "
        "cuándo se solicitó el concurso?"
    ),
    "pagos_preferentes": (
        "¿Hubo pagos a acreedores no privilegiados en los meses previos al concurso?"
    ),
    "alzamiento_bienes": (
        "¿Se detectaron ventas o salidas de activos relevantes "
        "cuando la empresa ya era insolvente?"
    ),
    "operaciones_vinculadas": (
        "¿Existen operaciones con personas o empresas vinculadas "
        "antes del concurso?"
    ),
    "simulacion_patrimonial": (
        "¿Hay indicios de que la situación patrimonial fue maquillada "
        "en actas o comunicaciones oficiales?"
    ),
}


# ============================
# EJECUCIÓN PRINCIPAL
# ============================

def ejecutar_analisis_prosecutor(
    *,
    case_id: str,
    auditor_summary: Optional[str] = None,
    auditor_risks: Optional[List[str]] = None,
    auditor_fallback: bool = False,
) -> ProsecutorResult:
    """
    Ejecuta el análisis completo del Agente Prosecutor para un caso.

    Args:
        case_id: ID del caso
        auditor_summary: Resumen opcional del Auditor (para contexto)
        auditor_risks: Riesgos opcionales detectados por el Auditor (para contexto)
        auditor_fallback: True si el Auditor usó fallback (sin contexto válido)
    """
    # Nota: auditor_summary, auditor_risks y auditor_fallback están disponibles
    # para uso futuro en el análisis, pero por ahora no se usan directamente
    # para mantener la lógica del Prosecutor independiente

    SessionLocal = get_session_factory()
    db: Session = SessionLocal()

    accusations: List[LegalAccusation] = []
    critical_count = 0

    try:
        for legal_ground, question in HOSTILE_QUESTIONS.items():
            # 1. Recuperar contexto crudo (RAG solo recupera)
            rag_result = rag_answer_internal(
                db=db,
                case_id=case_id,
                question=question,
                top_k=10,
            )

            # Si el RAG ya advierte riesgo o baja confianza → sospechoso
            if rag_result.confidence == "baja" or rag_result.hallucination_risk:
                continue

            if not rag_result.sources:
                continue

            # 2. Generar respuesta con LLM (agentes son los únicos que llaman a LLM)
            answer = ""
            if rag_result.context_text:
                answer = build_llm_answer(
                    question=question,
                    context_text=rag_result.context_text,
                )

            evidences = []
            for src in rag_result.sources:
                evidences.append(
                    Evidence(
                        document_id=str(src.get("document_id")),
                        document_name=src.get("document_name"),
                        chunk_index=src.get("chunk_index"),
                        excerpt=src.get("content"),
                        date=src.get("date"),
                    )
                )

            risk_level: RiskLevel = (
                "critico" if legal_ground in {
                    "retraso_concurso",
                    "alzamiento_bienes",
                }
                else "alto"
            )

            if risk_level in ("alto", "critico"):
                critical_count += 1

            # Consultar RAG legal para enriquecer con fundamento jurídico
            legal_query = question  # Usar la pregunta hostil como consulta legal
            legal_results = query_legal_rag(
                query=legal_query,
                top_k=3,  # Top 3 resultados de ley y jurisprudencia
            )
            
            # Extraer artículos de ley (usando citation normalizada)
            legal_articles = []
            for result in legal_results:
                if result.get("authority_level") == "norma" and result.get("citation"):
                    citation = result["citation"]
                    if citation not in legal_articles:
                        legal_articles.append(citation)
            
            # Extraer jurisprudencia (usando citation normalizada)
            jurisprudence = []
            for result in legal_results:
                if result.get("authority_level") == "jurisprudencia":
                    citation = result.get("citation", "Tribunal")
                    # Añadir preview del texto si es relevante
                    if result.get("relevance") in ("alta", "media"):
                        text_preview = result.get("text", "")[:150]
                        if text_preview:
                            jur_entry = f"{citation}: {text_preview}..."
                        else:
                            jur_entry = citation
                    else:
                        jur_entry = citation
                    if len(jurisprudence) < 2:  # Máximo 2 sentencias
                        jurisprudence.append(jur_entry)
            
            accusation = LegalAccusation(
                accusation_id=f"{case_id}-{legal_ground}",
                legal_ground=legal_ground,
                risk_level=risk_level,
                title=f"Posible {legal_ground.replace('_', ' ')}",
                description=answer,
                reasoning=(
                    "Los hechos documentales recuperados muestran una "
                    "secuencia temporal incompatible con una actuación diligente."
                ),
                evidences=evidences,
                estimated_probability=0.75 if risk_level == "critico" else 0.6,
                legal_articles=legal_articles,
                jurisprudence=jurisprudence,
            )

            accusations.append(accusation)

        overall_risk: RiskLevel = (
            "critico" if critical_count >= 2
            else "alto" if critical_count == 1
            else "medio"
        )

        return ProsecutorResult(
            case_id=case_id,
            overall_risk_level=overall_risk,
            accusations=accusations,
            critical_findings_count=critical_count,
            summary_for_lawyer=(
                "Se han detectado indicios relevantes de calificación culpable. "
                "El caso presenta riesgos significativos si se presenta sin "
                "estrategia defensiva previa."
            ),
            blocking_recommendation=overall_risk in ("alto", "critico"),
        )

    finally:
        db.close()

