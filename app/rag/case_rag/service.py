"""
Service layer para consultar el RAG de casos.

Esta capa simplifica el acceso al RAG para uso interno en agentes,
ocultando detalles de implementación (RAGInternalResult, etc).
"""
from sqlalchemy.orm import Session

from app.rag.case_rag.retrieve import rag_answer_internal


def query_case_rag(
    db: Session,
    case_id: str,
    query: str,
) -> str:
    """
    Consulta el RAG de casos y devuelve el contexto recuperado como string.

    Args:
        db: Sesión de base de datos
        case_id: ID del caso
        query: Pregunta o consulta a realizar

    Returns:
        String con el contexto recuperado. Si no hay contexto disponible,
        devuelve string vacío.
    """
    result = rag_answer_internal(
        db=db,
        case_id=case_id,
        question=query,
        top_k=10,  # Default para uso interno
    )

    return result.context_text

