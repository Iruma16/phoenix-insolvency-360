from __future__ import annotations

from typing import List, Optional
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.variables import RAG_TOP_K_DEFAULT, RAG_ACTIVE_POLICY
from app.rag.case_rag.retrieve import rag_answer_internal, ConfidenceLevel
from app.agents.base.response_builder import build_llm_answer
from app.services.confidence_scoring import (
    calculate_confidence_score,
    explain_confidence_score,
    interpret_score_for_stdout,
)
from app.services.response_policy import (
    get_policy,
    evaluate_policy,
    print_policy_decision,
)
from app.services.legal_phrasing import (
    get_insufficient_evidence_message,
    get_partial_information_message,
    wrap_response_with_evidence_notice,
    get_response_type_from_policy_decision,
    print_response_type_decision,
)


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
    # REGLA 3: Metadata obligatoria para citación precisa
    chunk_id: Optional[str] = None
    filename: Optional[str] = None
    page: Optional[int] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    section_hint: Optional[str] = None


class RAGResponse(BaseModel):
    answer: str
    sources: List[RAGSource]
    confidence: ConfidenceLevel
    warnings: List[str]
    hallucination_risk: bool = False  # True si hay alto riesgo de alucinación
    # CAPA DE PRODUCTO
    confidence_score: Optional[float] = None  # Score 0-1 (REGLA 1)
    response_type: Optional[str] = None  # Tipo de salida (REGLA 3)


# =========================================================
# ENDPOINT RAG (CAPA API)
# =========================================================

@router.post("/ask", response_model=RAGResponse)
def ask_rag(
    payload: RAGRequest,
    db: Session = Depends(get_db),
):
    # --------------------------------------------------
    # PASO 1: Recuperar contexto (retrieve.py - datos puros)
    # --------------------------------------------------
    result = rag_answer_internal(
        db=db,
        case_id=payload.case_id,
        question=payload.question,
        top_k=payload.top_k,
        doc_types=payload.doc_types,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )

    # --------------------------------------------------
    # PASO 2: Si no hay contexto, devolver error sin LLM
    # --------------------------------------------------
    if not result.context_text:
        error_message = {
            "CASE_NOT_FOUND": "No existe documentación que cumpla los criterios indicados para este caso.",
            "NO_CHUNKS": "Hay documentos en el caso, pero no se ha podido extraer contenido utilizable para su análisis.",
            "NO_EMBEDDINGS": "La documentación existe, pero el índice semántico no está disponible.",
            "NO_RELEVANT_CONTEXT": "No se ha encontrado información relevante en la documentación para responder a esta pregunta.",
            "PARTIAL_CONTEXT": "La información encontrada es parcial.",
        }.get(result.status, "No se pudo recuperar contexto para esta pregunta.")
        
        # REGLA 3: Usar phrasing controlado
        final_message = get_insufficient_evidence_message(error_message)
        
        return RAGResponse(
            answer=final_message,
            sources=[RAGSource(**s) for s in result.sources],
            confidence=result.confidence,
            warnings=result.warnings,
            hallucination_risk=result.hallucination_risk,
            confidence_score=0.0,
            response_type="EVIDENCIA_INSUFICIENTE",
        )

    # --------------------------------------------------
    # PASO 3: CAPA DE PRODUCTO - Scoring + Políticas
    # --------------------------------------------------
    
    # REGLA 1: Calcular confidence_score
    confidence_score = calculate_confidence_score(
        sources=result.sources,
        ground_truth_chunk_ids=None,  # TODO: cargar GT si existe
    )
    
    # REGLA 5: Explicar score por stdout
    # CORRECCIÓN A: Usar interpret_score_for_stdout (NO incluir narrativa en dict)
    score_explanation = explain_confidence_score(
        sources=result.sources,
        confidence_score=confidence_score,
        ground_truth_chunk_ids=None,
    )
    print(f"\n{'='*80}")
    print(f"[SCORING] Confidence Score: {confidence_score:.3f}")
    print(f"[SCORING] Interpretación: {interpret_score_for_stdout(confidence_score)}")
    print(f"[SCORING] Factores:")
    for key, value in score_explanation['factors'].items():
        print(f"  - {key}: {value}")
    print(f"{'='*80}\n")
    
    # REGLA 2: Evaluar política activa
    policy = get_policy(RAG_ACTIVE_POLICY)
    cumple_politica, motivo_politica = evaluate_policy(
        policy=policy,
        num_chunks=len(result.sources),
        confidence_score=confidence_score,
    )
    
    # REGLA 5: Mostrar decisión de política por stdout
    print_policy_decision(
        policy=policy,
        num_chunks=len(result.sources),
        confidence_score=confidence_score,
        cumple=cumple_politica,
        motivo=motivo_politica,
    )
    
    # REGLA 2: Si no cumple política → BLOQUEAR respuesta
    if not cumple_politica:
        final_message = get_insufficient_evidence_message(motivo_politica)
        
        return RAGResponse(
            answer=final_message,
            sources=[RAGSource(**s) for s in result.sources],
            confidence=result.confidence,
            warnings=result.warnings + [f"Bloqueado por política {policy.name}: {motivo_politica}"],
            hallucination_risk=result.hallucination_risk,
            confidence_score=confidence_score,
            response_type="EVIDENCIA_INSUFICIENTE",
        )
    
    # --------------------------------------------------
    # PASO 4: Generar respuesta con LLM
    # --------------------------------------------------
    # CORRECCIÓN C: Pasar hallucination_risk para ajustar response_type
    response_type = get_response_type_from_policy_decision(
        cumple_politica=cumple_politica,
        confidence_score=confidence_score,
        hallucination_risk=result.hallucination_risk,
    )
    
    # REGLA 5: Mostrar tipo de respuesta por stdout
    print_response_type_decision(response_type, confidence_score)
    
    # Si información parcial, agregar advertencia ANTES de llamar al LLM
    if response_type == "INFORMACION_PARCIAL_NO_CONCLUYENTE":
        partial_warning = get_partial_information_message(
            confidence_score=confidence_score,
            num_chunks=len(result.sources),
        )
        result.warnings.append(partial_warning)
    
    # CERTIFICACIÓN 1: Log antes de llamar al LLM
    print(f"[CERT] LLM_CALL_START case_id={payload.case_id}")
    
    # CERTIFICACIÓN 2: Chunks usados como contexto
    context_chunk_ids = [s.get("chunk_id", "N/A") for s in result.sources]
    print(f"[CERT] CONTEXT_CHUNKS = {context_chunk_ids}")
    
    # Generar respuesta base del LLM
    llm_answer = build_llm_answer(
        question=payload.question,
        context_text=result.context_text,
    )
    
    # --------------------------------------------------
    # PASO 5: REGLA 3 - Aplicar phrasing legal controlado
    # --------------------------------------------------
    # CORRECCIÓN D: Pasar sources para incluir citas visibles
    final_answer = wrap_response_with_evidence_notice(
        answer=llm_answer,
        confidence_score=confidence_score,
        sources=result.sources,
    )

    return RAGResponse(
        answer=final_answer,
        sources=[RAGSource(**s) for s in result.sources],
        confidence=result.confidence,
        warnings=result.warnings,
        hallucination_risk=result.hallucination_risk,
        confidence_score=confidence_score,
        response_type=response_type,
    )
