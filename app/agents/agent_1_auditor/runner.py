"""
Runner para ejecutar el agente auditor.
"""
import logging
from typing import Tuple
from sqlalchemy.orm import Session

from app.rag.case_rag.service import query_case_rag
from .logic import audit_logic
from .schema import AuditorResult

logger = logging.getLogger(__name__)


def run_auditor(case_id: str, question: str, db: Session) -> Tuple[AuditorResult, bool]:
    """
    Ejecuta el Agente Auditor con RAG.

    Args:
        case_id: ID del caso a auditar
        question: Pregunta o consulta para el auditor
        db: Sesión de base de datos

    Returns:
        Tupla (AuditorResult, auditor_fallback)
        - AuditorResult: con summary, risks y next_actions
        - auditor_fallback: True si se usó fallback (sin contexto válido)
    """
    logger.info(
        "Agente Auditor iniciado",
        extra={
            "agent_name": "auditor",
            "case_id": case_id,
            "stage": "analysis",
        }
    )

    # Consultar RAG para obtener contexto
    context = query_case_rag(
        db=db,
        case_id=case_id,
        query=question,
    )

    # Detectar si hay fallback: contexto vacío o muy corto
    auditor_fallback = not context or len(context.strip()) < 100

    # Ejecutar lógica de auditoría con pregunta y contexto
    result = audit_logic(question, context)

    output = AuditorResult(**result)

    logger.info(
        "Agente Auditor finalizado",
        extra={
            "agent_name": "auditor",
            "case_id": case_id,
            "stage": "analysis",
            "auditor_fallback": auditor_fallback,
        }
    )

    return output, auditor_fallback
