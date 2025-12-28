from __future__ import annotations

from typing import List, Optional
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.variables import RAG_TOP_K_DEFAULT
from app.rag.case_rag.retrieve import rag_answer_internal, ConfidenceLevel
from app.agents.base.response_builder import build_llm_answer


router = APIRouter(prefix="/rag", tags=["RAG"])


# =========================================================
# SCHEMAS API
# =========================================================

class RAGRequest(BaseModel):
    case_id: str
    question: str
    top_k: int = RAG_TOP_K_DEFAULT

    doc_types: Optional[List[str]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class RAGSource(BaseModel):
    document_id: str
    chunk_index: int
    content: str
    similarity_score: Optional[float] = None  # Distancia de similitud (menor = más similar)


class RAGResponse(BaseModel):
    answer: str
    sources: List[RAGSource]
    confidence: ConfidenceLevel
    warnings: List[str]
    hallucination_risk: bool = False  # True si hay alto riesgo de alucinación


# =========================================================
# ENDPOINT RAG (CAPA API)
# =========================================================

@router.post("/ask", response_model=RAGResponse)
def ask_rag(
    payload: RAGRequest,
    db: Session = Depends(get_db),
):
    # 1. Recuperar contexto crudo (RAG solo recupera)
    result = rag_answer_internal(
        db=db,
        case_id=payload.case_id,
        question=payload.question,
        top_k=payload.top_k,
        doc_types=payload.doc_types,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )

    # 2. Si no hay contexto, devolver error sin llamar a LLM
    if not result.context_text:
        # Construir mensaje de error basado en status
        error_message = {
            "CASE_NOT_FOUND": "No existe documentación que cumpla los criterios indicados para este caso.",
            "NO_CHUNKS": "Hay documentos en el caso, pero no se ha podido extraer contenido utilizable para su análisis.",
            "NO_EMBEDDINGS": "La documentación existe, pero el índice semántico no está disponible.",
            "NO_RELEVANT_CONTEXT": "No se ha encontrado información relevante en la documentación para responder a esta pregunta.",
            "PARTIAL_CONTEXT": "La información encontrada es parcial.",
        }.get(result.status, "No se pudo recuperar contexto para esta pregunta.")
        
        return RAGResponse(
            answer=error_message,
            sources=[RAGSource(**s) for s in result.sources],
            confidence=result.confidence,
            warnings=result.warnings,
            hallucination_risk=result.hallucination_risk,
        )

    # 3. Generar respuesta con LLM (agentes son los únicos que llaman a LLM)
    answer = build_llm_answer(
        question=payload.question,
        context_text=result.context_text,
    )

    return RAGResponse(
        answer=answer,
        sources=[RAGSource(**s) for s in result.sources],
        confidence=result.confidence,
        warnings=result.warnings,
        hallucination_risk=result.hallucination_risk,  # ✅ Incluir flag de riesgo de alucinación
    )
