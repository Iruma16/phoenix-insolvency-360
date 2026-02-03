from __future__ import annotations

import os
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.base.response_builder import build_llm_answer
from app.core.config import settings
from app.core.database import get_db
from app.core.variables import RAG_ACTIVE_POLICY, RAG_TOP_K_DEFAULT
from app.rag.case_rag.retrieve import ConfidenceLevel, rag_answer_internal
from app.services.confidence_scoring import (
    calculate_confidence_score,
    explain_confidence_score,
    interpret_score_for_stdout,
)
from app.services.legal_phrasing import (
    get_insufficient_evidence_message,
    get_no_relevant_context_message,
    get_partial_information_message,
    get_response_type_from_policy_decision,
    get_technical_unavailable_message,
    print_response_type_decision,
    wrap_response_with_evidence_notice,
)
from app.services.response_policy import (
    evaluate_policy,
    get_policy,
    print_policy_decision,
)

router = APIRouter(prefix="/rag", tags=["RAG"])


# region agent log (debug-mode)
def _dbg_log_rag(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    try:
        _path = "/Users/irumabragado/Documents/procesos/202512_phoenix-legal/.cursor/debug.log"
        payload = {
            "sessionId": "debug-session",
            "runId": "rag-env-debug-v1",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(__import__("time").time() * 1000),
        }
        with open(_path, "a", encoding="utf-8") as f:
            f.write(__import__("json").dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


# endregion agent log (debug-mode)

# =========================================================
# SCHEMAS API
# =========================================================


class RAGRequest(BaseModel):
    case_id: str
    question: str
    top_k: int = RAG_TOP_K_DEFAULT

    doc_types: Optional[list[str]] = None
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
    sources: list[RAGSource]
    confidence: ConfidenceLevel
    warnings: list[str]
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
    # Debug: comprobar disponibilidad real de clave/LLM (sin exponer secretos)
    _dbg_log_rag(
        "H1",
        "app/rag/case_rag/rag.py:ask_rag",
        "env_check",
        {
            "case_id": str(payload.case_id),
            "llm_enabled": bool(getattr(settings, "llm_enabled", False)),
            "llm_available": bool(getattr(settings, "llm_available", False)),
            "settings_openai_key_present": bool(getattr(settings, "openai_api_key", None)),
            "env_openai_key_present": bool(os.getenv("OPENAI_API_KEY")),
        },
    )
    _q = (payload.question or "").lower()
    _dbg_log_rag(
        "H2",
        "app/rag/case_rag/rag.py:ask_rag",
        "question_signals",
        {
            "case_id": str(payload.case_id),
            "question_len": len(payload.question or ""),
            "has_domicilio": "domicilio" in _q,
            "has_apoder": ("apoder" in _q) or ("poder" in _q),
            "has_insolv": "insolv" in _q,
        },
    )
    # --------------------------------------------------
    # PASO 1: Recuperar contexto (retrieve.py - datos puros)
    # --------------------------------------------------
    try:
        result = rag_answer_internal(
            db=db,
            case_id=payload.case_id,
            question=payload.question,
            top_k=payload.top_k,
            doc_types=payload.doc_types,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
    except Exception as e:
        # Degradación controlada: nunca devolver 500 por fallos internos del RAG.
        final_message = get_insufficient_evidence_message("RAG temporalmente no disponible.")
        return RAGResponse(
            answer=final_message,
            sources=[],
            confidence="baja",
            warnings=[f"RAG_INTERNAL_ERROR: {type(e).__name__}"],
            hallucination_risk=True,
            confidence_score=0.0,
            response_type="EVIDENCIA_INSUFICIENTE",
        )

    # Debug: resumen del retrieval (sin contenido sensible)
    try:
        filenames = []
        for s in (result.sources or [])[:8]:
            fn = s.get("filename") or s.get("document_id")
            if fn:
                filenames.append(str(fn))
        uniq = []
        for fn in filenames:
            if fn not in uniq:
                uniq.append(fn)
        _dbg_log_rag(
            "H3",
            "app/rag/case_rag/rag.py:ask_rag",
            "retrieval_summary",
            {
                "case_id": str(payload.case_id),
                "status": str(getattr(result, "status", "")),
                "num_sources": len(result.sources or []),
                "confidence": str(getattr(result, "confidence", "")),
                "hallucination_risk": bool(getattr(result, "hallucination_risk", False)),
                "filenames_top": uniq[:5],
            },
        )
    except Exception:
        pass

    # --------------------------------------------------
    # PASO 2: Si no hay contexto, devolver error sin LLM
    # --------------------------------------------------
    if not result.context_text:
        # Mensajes UX por status (NO mezclar "no hay evidencia" con "RAG no configurado/no listo")
        error_message = {
            "CASE_NOT_FOUND": "No existe documentación que cumpla los criterios indicados para este caso.",
            "NO_CHUNKS": "Hay documentos en el caso, pero no se ha podido extraer contenido utilizable para su análisis.",
            "NO_EMBEDDINGS": "La documentación existe, pero el índice semántico no está disponible.",
            "RAG_NOT_READY": "RAG no disponible: no existe versión ACTIVE del vectorstore para este caso.",
            "RAG_CONFIG_MISSING": "LLM/RAG no disponible: OPENAI_API_KEY no configurada en el proceso.",
            # Back-compat (legacy)
            "LLM_UNAVAILABLE": "LLM/RAG no disponible: configuración incompleta (legacy).",
            "NO_RELEVANT_CONTEXT": "No se ha encontrado información relevante en la documentación para responder a esta pregunta.",
            "PARTIAL_CONTEXT": "La información encontrada es parcial.",
        }.get(result.status, "No se pudo recuperar contexto para esta pregunta.")

        # UX: para problemas de configuración/estado del RAG, no decir "evidencia insuficiente"
        if result.status in (
            "RAG_NOT_READY",
            "RAG_CONFIG_MISSING",
            "LLM_UNAVAILABLE",
            "NO_EMBEDDINGS",
            "NO_CHUNKS",
        ):
            final_message = get_technical_unavailable_message(error_message)
            response_type = "SISTEMA_NO_DISPONIBLE"
            _dbg_log_rag(
                "H4",
                "app/rag/case_rag/rag.py:ask_rag",
                "no_context_branch",
                {
                    "case_id": str(payload.case_id),
                    "status": str(getattr(result, "status", "")),
                    "response_type": response_type,
                    "phrasing": "technical_unavailable",
                },
            )
        elif result.status == "NO_RELEVANT_CONTEXT":
            final_message = get_no_relevant_context_message()
            response_type = "EVIDENCIA_INSUFICIENTE"
            _dbg_log_rag(
                "H4",
                "app/rag/case_rag/rag.py:ask_rag",
                "no_context_branch",
                {
                    "case_id": str(payload.case_id),
                    "status": str(getattr(result, "status", "")),
                    "response_type": response_type,
                    "phrasing": "no_relevant_context",
                },
            )
        else:
            # REGLA 3: Usar phrasing controlado (esto sí es evidencia insuficiente)
            final_message = get_insufficient_evidence_message(error_message)
            response_type = "EVIDENCIA_INSUFICIENTE"
            _dbg_log_rag(
                "H4",
                "app/rag/case_rag/rag.py:ask_rag",
                "no_context_branch",
                {
                    "case_id": str(payload.case_id),
                    "status": str(getattr(result, "status", "")),
                    "response_type": response_type,
                    "phrasing": "insufficient_evidence",
                },
            )

        return RAGResponse(
            answer=final_message,
            sources=[RAGSource(**s) for s in result.sources],
            confidence=result.confidence,
            warnings=result.warnings,
            hallucination_risk=result.hallucination_risk,
            confidence_score=0.0,
            response_type=response_type,
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
    print("[SCORING] Factores:")
    for key, value in score_explanation["factors"].items():
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
        # UX (D): información parcial / no concluyente por política (no culpar a falta de docs si ya hay chunks)
        final_message = (
            get_partial_information_message(
                confidence_score=confidence_score,
                num_chunks=len(result.sources),
            )
            + f"\n\nMotivo (política): {motivo_politica}"
        )
        _dbg_log_rag(
            "H5",
            "app/rag/case_rag/rag.py:ask_rag",
            "policy_block",
            {
                "case_id": str(payload.case_id),
                "policy": str(getattr(policy, "name", "unknown")),
                "motivo": str(motivo_politica),
                "num_sources": len(result.sources or []),
                "confidence_score": float(confidence_score),
            },
        )

        return RAGResponse(
            answer=final_message,
            sources=[RAGSource(**s) for s in result.sources],
            confidence=result.confidence,
            warnings=result.warnings + [f"Bloqueado por política {policy.name}: {motivo_politica}"],
            hallucination_risk=result.hallucination_risk,
            confidence_score=confidence_score,
            response_type="INFORMACION_PARCIAL_NO_CONCLUYENTE",
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

    # Generar respuesta base del LLM (si está disponible)
    if not settings.llm_available:
        final_message = get_technical_unavailable_message(
            "LLM/RAG no disponible (OPENAI_API_KEY no configurada o LLM deshabilitado)."
        )
        _dbg_log_rag(
            "H6",
            "app/rag/case_rag/rag.py:ask_rag",
            "llm_disabled_branch",
            {
                "case_id": str(payload.case_id),
                "settings_llm_available": bool(getattr(settings, "llm_available", False)),
                "env_openai_key_present": bool(os.getenv("OPENAI_API_KEY")),
            },
        )
        return RAGResponse(
            answer=final_message,
            sources=[RAGSource(**s) for s in result.sources],
            confidence=result.confidence,
            warnings=result.warnings + ["LLM_DISABLED: no se generó respuesta con LLM."],
            hallucination_risk=True,
            confidence_score=confidence_score,
            response_type="SISTEMA_NO_DISPONIBLE",
        )

    try:
        llm_answer = build_llm_answer(
            question=payload.question,
            context_text=result.context_text,
        )
    except Exception as e:
        final_message = get_technical_unavailable_message(
            "No se pudo generar respuesta con LLM (error del proveedor)."
        )
        _dbg_log_rag(
            "H7",
            "app/rag/case_rag/rag.py:ask_rag",
            "llm_error_branch",
            {
                "case_id": str(payload.case_id),
                "err_type": str(type(e).__name__),
            },
        )
        return RAGResponse(
            answer=final_message,
            sources=[RAGSource(**s) for s in result.sources],
            confidence=result.confidence,
            warnings=result.warnings + [f"LLM_ERROR: {type(e).__name__}"],
            hallucination_risk=True,
            confidence_score=confidence_score,
            response_type="SISTEMA_NO_DISPONIBLE",
        )

    # region agent log (debug-mode)
    try:
        _no_ev = "No hay evidencia suficiente en los documentos aportados."
        _dbg_log_rag(
            "H8",
            "app/rag/case_rag/rag.py:ask_rag",
            "llm_answer_flags",
            {
                "case_id": str(payload.case_id),
                "llm_answer_len": len(llm_answer or ""),
                "llm_answer_is_exact_no_evidence": str((llm_answer or "").strip() == _no_ev),
                "llm_answer_starts_with_no_evidence": str(
                    (llm_answer or "").strip().startswith(_no_ev)
                ),
            },
        )
    except Exception:
        pass
    # endregion agent log (debug-mode)

    # Si el LLM devolvió la frase canónica de "no hay evidencia", NO lo clasifiques como respuesta con evidencia.
    _no_ev = "No hay evidencia suficiente en los documentos aportados."
    if (llm_answer or "").strip() == _no_ev:
        _dbg_log_rag(
            "H9",
            "app/rag/case_rag/rag.py:ask_rag",
            "llm_no_evidence_override",
            {
                "case_id": str(payload.case_id),
                "response_type_before": str(response_type),
                "confidence_score": float(confidence_score),
                "num_sources": len(result.sources or []),
            },
        )
        return RAGResponse(
            answer=get_no_relevant_context_message(),
            sources=[RAGSource(**s) for s in result.sources],
            confidence="baja",
            warnings=result.warnings
            + [
                "LLM_NO_EVIDENCE: el LLM no encontró evidencia explícita en el contexto recuperado."
            ],
            hallucination_risk=False,
            confidence_score=0.0,
            response_type="EVIDENCIA_INSUFICIENTE",
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
