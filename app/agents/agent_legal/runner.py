"""
Runner del Agente Legal.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.rag.legal_rag.service import query_legal_rag

from .logic import legal_agent_logic
from .schema import LegalAgentResult, LegalRisk

logger = logging.getLogger(__name__)


def run_legal_agent(
    case_id: str,
    question: str,
    db: Session,
    auditor_summary: Optional[str] = None,
    auditor_risks: Optional[list[str]] = None,
) -> LegalAgentResult:
    """
    Ejecuta el Agente Legal para analizar riesgos legales.

    Args:
        case_id: ID del caso a analizar
        question: Pregunta legal específica
        db: Sesión de base de datos
        auditor_summary: Resumen del Auditor (opcional)
        auditor_risks: Riesgos detectados por el Auditor (opcional)

    Returns:
        LegalAgentResult con el análisis legal completo
    """
    logger.info(
        "Agente Legal iniciado",
        extra={
            "agent_name": "legal",
            "case_id": case_id,
            "stage": "analysis",
        },
    )

    # Consultar RAG Legal para obtener base legal
    try:
        legal_results = query_legal_rag(
            query=question,
            include_ley=True,
            include_jurisprudencia=True,
        )

        # Construir contexto legal
        # query_legal_rag retorna una lista de diccionarios con citation, text, etc.
        legal_context_parts = []
        for result in legal_results:
            if isinstance(result, dict):
                citation = result.get("citation", "")
                text = result.get("text", "")
                source = result.get("source", "")
                authority = result.get("authority_level", "")
                context_line = f"{citation}"
                if source:
                    context_line += f" ({source})"
                if authority:
                    context_line += f" [{authority}]"
                context_line += f": {text}"
                legal_context_parts.append(context_line)
            else:
                legal_context_parts.append(str(result))

        legal_context = "\n\n".join(legal_context_parts) if legal_context_parts else ""
    except Exception as e:
        logger.warning(f"Error consultando RAG Legal: {e}")
        legal_context = ""

    # Ejecutar lógica del agente
    result_data = legal_agent_logic(
        question=question,
        legal_context=legal_context,
        auditor_summary=auditor_summary,
        auditor_risks=auditor_risks,
    )

    # Construir resultado estructurado
    legal_risks = [LegalRisk(**risk_data) for risk_data in result_data.get("legal_risks", [])]

    result = LegalAgentResult(
        case_id=case_id,
        legal_risks=legal_risks,
        legal_conclusion=result_data.get("legal_conclusion", "No se pudo generar conclusión."),
        confidence_level=result_data.get("confidence_level", "indeterminado"),
        missing_data=result_data.get("missing_data", []),
        legal_basis=result_data.get("legal_basis", []),
    )

    logger.info(
        "Agente Legal finalizado",
        extra={
            "agent_name": "legal",
            "case_id": case_id,
            "stage": "analysis",
            "risks_count": len(legal_risks),
            "confidence_level": result.confidence_level,
        },
    )

    return result
