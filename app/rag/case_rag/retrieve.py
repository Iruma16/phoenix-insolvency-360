from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.variables import (
    EMBEDDING_MODEL,
    LEGAL_QUALITY_SCORE_BLOCK_THRESHOLD,
    LEGAL_QUALITY_SCORE_WARNING_THRESHOLD,
    RAG_AUTO_BUILD_EMBEDDINGS,
    RAG_HALLUCINATION_RISK_THRESHOLD,
    RAG_MIN_CHUNKS_REQUIRED,
    RAG_MIN_SIMILARITY_SCORE,
    RAG_TRACE_DECISIONS,
    RAG_WEAK_RESPONSE_MAX_DISTANCE,
)
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.rag.evidence import (
    NoResponseReasonCode,
    RetrievalEvidence,
    apply_evidence_gates,
    build_retrieval_evidence,
    log_evidence_decision,
)
from app.rag.evidence_enforcer import (
    validate_chunk_has_location,
    validate_chunks_exist,
    validate_retrieval_result,
)
from app.services.document_chunk_pipeline import (
    build_document_chunks_for_case,
)
from app.services.document_quality import get_document_quality_summary
from app.services.embeddings_pipeline import (
    build_embeddings_for_case,
    get_case_collection,
)
from app.services.vectorstore_versioning import (
    get_active_version,
)

# region agent log (debug-mode)
def _dbg_log_retrieve(hypothesis_id: str, location: str, message: str, data: dict) -> None:
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
# ESTADOS INTERNOS RAG
# =========================================================

RAGStatus = Literal[
    "OK",
    "CASE_NOT_FOUND",
    "NO_CHUNKS",
    "NO_EMBEDDINGS",
    "RAG_NOT_READY",
    "RAG_CONFIG_MISSING",
    # Back-compat (legacy)
    "LLM_UNAVAILABLE",
    "NO_RELEVANT_CONTEXT",
    "PARTIAL_CONTEXT",
]

ConfidenceLevel = Literal["alta", "media", "baja"]


@dataclass
class RAGInternalResult:
    status: RAGStatus
    context_text: str  # Contexto crudo concatenado de chunks
    sources: list[dict]  # Lista de chunks con metadatos y scores
    confidence: ConfidenceLevel
    warnings: list[str]
    hallucination_risk: bool = False  # True si hay alto riesgo de alucinación
    evidence: Optional[RetrievalEvidence] = None  # Evidencia verificable (Endurecimiento #4)
    no_response_reason: Optional[NoResponseReasonCode] = None  # Código si NO_RESPONSE


# =========================================================
# FUNCIÓN RAG (CEREBRO ÚNICO)
# =========================================================


def rag_answer_internal(
    *,
    db: Session,
    case_id: str,
    question: str,
    top_k: int,
    doc_types: Optional[list[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> RAGInternalResult:
    warnings: list[str] = []
    _dbg_log_retrieve(
        "H2",
        "app/rag/case_rag/retrieve.py:rag_answer_internal",
        "entry",
        {
            "case_id": str(case_id),
            "question_len": len(question or ""),
            "top_k": int(top_k),
            "env_openai_key_present": bool(os.getenv("OPENAI_API_KEY")),
        },
    )

    # --------------------------------------------------
    # 0️⃣ EVALUAR CALIDAD DOCUMENTAL Y RIESGO LEGAL
    # --------------------------------------------------
    quality_summary = get_document_quality_summary(db=db, case_id=case_id)
    quality_score = quality_summary["quality_score"]
    legal_risks = quality_summary.get("legal_risks", [])
    critical_docs_missing = quality_summary.get("critical_documents_missing", 0)

    # ✅ BLOQUEO: Si la calidad es muy baja, NO permitir conclusiones automáticas
    if quality_score < LEGAL_QUALITY_SCORE_BLOCK_THRESHOLD:
        return RAGInternalResult(
            status="CASE_NOT_FOUND",  # Reutilizamos status para bloqueo
            context_text="",  # Sin contexto disponible por bloqueo
            sources=[],
            confidence="baja",
            warnings=[
                f"⚠️ BLOQUEO POR CALIDAD: Score {quality_score:.1f}/100 (umbral mínimo: {LEGAL_QUALITY_SCORE_BLOCK_THRESHOLD})",
                "Se requieren conclusiones manuales hasta que la documentación esté completamente procesada.",
            ]
            + legal_risks,
            hallucination_risk=True,  # Baja calidad = alto riesgo de alucinación
        )

    # ✅ ALERTA: Documentos críticos sin embeddings
    if critical_docs_missing > 0:
        warnings.extend(legal_risks)
        warnings.append(
            f"⚠️ ALERTA LEGAL: {critical_docs_missing} documento(s) legal(es) crítico(s) "
            "sin procesamiento completo. Las conclusiones pueden estar incompletas."
        )

    # ✅ ADVERTENCIA: Calidad baja pero no bloqueante
    if quality_score < LEGAL_QUALITY_SCORE_WARNING_THRESHOLD:
        warnings.append(
            f"⚠️ Calidad documental baja ({quality_score:.1f}/100). "
            "Riesgo elevado de alucinación. Se recomienda revisar conclusiones manualmente."
        )

    # ✅ Baja calidad → Alta probabilidad de alucinación
    # Ajustar umbral de riesgo de alucinación basado en calidad
    quality_adjusted_hallucination_threshold = RAG_HALLUCINATION_RISK_THRESHOLD
    if quality_score < 75:
        # Si calidad < 75, ser más estricto con riesgo de alucinación
        quality_adjusted_hallucination_threshold = RAG_HALLUCINATION_RISK_THRESHOLD * 0.85

    # --------------------------------------------------
    # 1️⃣ Validar caso + documentos
    # --------------------------------------------------
    from sqlalchemy import or_

    query = db.query(Document).filter(
        Document.case_id == case_id,
        # FASE 2A: Excluir documentos duplicados marcados para exclusión
        or_(
            Document.duplicate_action.is_(None),
            Document.duplicate_action == "pending",
            Document.duplicate_action == "keep_both",
        ),
    )

    if doc_types:
        query = query.filter(Document.doc_type.in_(doc_types))

    if date_from:
        query = query.filter(Document.date_end >= date_from)

    if date_to:
        query = query.filter(Document.date_start <= date_to)

    documents = query.all()

    if not documents:
        return RAGInternalResult(
            status="CASE_NOT_FOUND",
            context_text="",  # Sin contexto disponible
            sources=[],
            confidence="baja",
            warnings=[],
            hallucination_risk=False,
        )

    document_ids = [d.document_id for d in documents]

    # --------------------------------------------------
    # 2️⃣ Validar / generar chunks (PASO 2)
    # --------------------------------------------------
    # FASE 4: Validación DURA - no chunks → excepción
    try:
        chunks_count = validate_chunks_exist(db, case_id, document_ids)
    except Exception:
        # Si falla validación, intentar generar chunks automáticamente
        chunks_count = 0

    if chunks_count == 0:
        warnings.append("No había chunks y se ha ejecutado el chunking automáticamente.")

        build_document_chunks_for_case(
            db=db,
            case_id=case_id,
            overwrite=False,
        )

        chunks_count = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.case_id == case_id,
                DocumentChunk.document_id.in_(document_ids),
            )
            .count()
        )

        if chunks_count == 0:
            return RAGInternalResult(
                status="NO_CHUNKS",
                context_text="",  # Sin chunks disponibles
                sources=[],
                confidence="baja",
                warnings=warnings,
                hallucination_risk=False,
            )

    # --------------------------------------------------
    # 3️⃣ Validar / generar embeddings (PASO 3)
    # --------------------------------------------------
    # CAMBIO: Ahora verificamos que existe una versión ACTIVE válida
    active_version = get_active_version(case_id)
    _dbg_log_retrieve(
        "H3",
        "app/rag/case_rag/retrieve.py:rag_answer_internal",
        "active_version",
        {"case_id": str(case_id), "active_version_present": bool(active_version)},
    )

    if not active_version:
        # No existe versión activa
        if not RAG_AUTO_BUILD_EMBEDDINGS:
            return RAGInternalResult(
                status="NO_EMBEDDINGS",
                context_text="",  # Sin embeddings disponibles
                sources=[],
                confidence="baja",
                warnings=warnings,
                hallucination_risk=False,
            )

        # Generar embeddings automáticamente
        warnings.append("El índice semántico no existía y se ha generado automáticamente.")
        try:
            version_id = build_embeddings_for_case(db=db, case_id=case_id)
            warnings.append(f"Nueva versión creada: {version_id}")
        except Exception as e:
            return RAGInternalResult(
                status="NO_EMBEDDINGS",
                context_text="",
                sources=[],
                confidence="baja",
                warnings=warnings + [f"Error generando embeddings: {e}"],
                hallucination_risk=False,
            )

    # Obtener colección de la versión activa (o None para usar ACTIVE)
    try:
        collection = get_case_collection(case_id, version=None)  # None = usar ACTIVE

        # Validar que la colección no esté vacía
        if collection.count() == 0:
            warnings.append("La versión activa del vectorstore está vacía.")
            if not RAG_AUTO_BUILD_EMBEDDINGS:
                return RAGInternalResult(
                    status="NO_EMBEDDINGS",
                    context_text="",
                    sources=[],
                    confidence="baja",
                    warnings=warnings,
                    hallucination_risk=False,
                )

            # Regenerar embeddings
            warnings.append("Regenerando embeddings...")
            try:
                version_id = build_embeddings_for_case(db=db, case_id=case_id)
                warnings.append(f"Nueva versión creada: {version_id}")
                collection = get_case_collection(case_id, version=None)
            except Exception as e:
                return RAGInternalResult(
                    status="NO_EMBEDDINGS",
                    context_text="",
                    sources=[],
                    confidence="baja",
                    warnings=warnings + [f"Error regenerando embeddings: {e}"],
                    hallucination_risk=False,
                )
    except Exception as e:
        msg = str(e)
        # Caso típico: no existe ACTIVE => el RAG no está "listo", no es falta de documentos
        if "No existe versión ACTIVE" in msg or "No existe vectorstore ACTIVE" in msg:
            return RAGInternalResult(
                status="RAG_NOT_READY",
                context_text="",
                sources=[],
                confidence="baja",
                warnings=warnings
                + [
                    "RAG no disponible: no existe versión ACTIVE del vectorstore para este caso.",
                    "Acción: ejecutar ingesta/embeddings del caso o activar una versión READY.",
                ],
                hallucination_risk=True,
            )
        return RAGInternalResult(
            status="NO_EMBEDDINGS",
            context_text="",
            sources=[],
            confidence="baja",
            warnings=warnings + [f"Error accediendo al vectorstore: {e}"],
            hallucination_risk=True,
        )

    # --------------------------------------------------
    # 4️⃣ Búsqueda semántica
    # --------------------------------------------------
    # Generar embedding de la pregunta usando el mismo modelo que los embeddings almacenados
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        _dbg_log_retrieve(
            "H1",
            "app/rag/case_rag/retrieve.py:rag_answer_internal",
            "missing_openai_env",
            {"case_id": str(case_id)},
        )
        return RAGInternalResult(
            status="RAG_CONFIG_MISSING",
            context_text="",
            sources=[],
            confidence="baja",
            warnings=warnings
            + [
                "LLM/RAG no disponible: falta configurar OPENAI_API_KEY (entorno no configurado).",
                "Acción: configurar OPENAI_API_KEY en el proceso que ejecuta la app (Streamlit/FastAPI/Docker).",
            ],
            hallucination_risk=True,
        )

    try:
        openai_client = OpenAI(api_key=api_key)
        question_embedding = (
            openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=[question],
            )
            .data[0]
            .embedding
        )
    except Exception as e:
        return RAGInternalResult(
            status="LLM_UNAVAILABLE",
            context_text="",
            sources=[],
            confidence="baja",
            warnings=warnings
            + [
                f"RAG no disponible: error generando embedding de consulta ({type(e).__name__}).",
            ],
            hallucination_risk=True,
        )

    try:
        results = collection.query(
            query_embeddings=[question_embedding],
            n_results=top_k,
            include=["metadatas", "documents", "distances"],  # ✅ Incluir distancias
        )
    except Exception as e:
        return RAGInternalResult(
            status="NO_EMBEDDINGS",
            context_text="",
            sources=[],
            confidence="baja",
            warnings=warnings + [f"RAG no disponible: error consultando vectorstore ({type(e).__name__})."],
            hallucination_risk=True,
        )

    docs_found = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]  # ✅ Obtener distancias (menor = más similar)

    if not docs_found:
        return RAGInternalResult(
            status="NO_RELEVANT_CONTEXT",
            context_text="",  # Sin contexto relevante encontrado
            sources=[],
            confidence="baja",
            warnings=warnings,
            hallucination_risk=False,
        )

    # --------------------------------------------------
    # 5️⃣ Construcción de contexto + fuentes (CON FILTRO DE SCORE)
    # --------------------------------------------------
    context_blocks = []
    sources = []

    # Filtrar documentos válidos y por score mínimo de similitud
    valid_pairs = []
    for text, meta, distance in zip(docs_found, metas, distances):
        try:
            # ✅ FILTRAR POR SCORE MÍNIMO DE SIMILARIDAD
            if distance > RAG_MIN_SIMILARITY_SCORE:
                continue  # Saltar si la distancia es mayor al umbral

            # Validar texto
            if text is None or not text.strip():
                continue

            # Validar metadatos
            if meta is None:
                continue

            document_id = meta.get("document_id")
            chunk_index = meta.get("chunk_index")

            if document_id is None or chunk_index is None:
                continue

            # Convertir tipos si es necesario (ChromaDB puede devolver strings)
            document_id = str(document_id)
            try:
                chunk_index = int(chunk_index)
            except (ValueError, TypeError):
                continue  # Si no se puede convertir a int, saltar este elemento

            # ✅ Incluir distancia en los datos
            valid_pairs.append(
                (text, {"document_id": document_id, "chunk_index": chunk_index}, distance)
            )
        except Exception as e:
            # Si hay algún error procesando este elemento, saltarlo
            print(f"[WARN] Error procesando elemento en validación: {e}")
            continue

    # REGLA 4: Umbral mínimo de contexto (BLOQUEANTE)
    if len(valid_pairs) < RAG_MIN_CHUNKS_REQUIRED:
        if RAG_TRACE_DECISIONS:
            print(
                f"[RAG DECISIÓN] ❌ BLOQUEO: {len(valid_pairs)} chunks < {RAG_MIN_CHUNKS_REQUIRED} mínimo requerido"
            )
            print("[RAG DECISIÓN] Motivo: EVIDENCIA_INSUFICIENTE")

        return RAGInternalResult(
            status="NO_RELEVANT_CONTEXT",
            context_text="",  # Sin contexto válido encontrado
            sources=[],
            confidence="baja",
            warnings=warnings
            + [
                f"Se encontraron {len(valid_pairs)} fragmento(s) relevante(s), "
                f"pero se requieren al menos {RAG_MIN_CHUNKS_REQUIRED} para generar una respuesta fundamentada."
            ],
            hallucination_risk=False,
        )

    # ✅ Determinar riesgo de alucinación y respuesta débil basado en la mejor distancia
    # Usar umbral ajustado por calidad documental (baja calidad → más estricto)
    best_distance = valid_pairs[0][2] if valid_pairs else float("inf")
    hallucination_risk = best_distance > quality_adjusted_hallucination_threshold
    is_weak_response = best_distance > RAG_WEAK_RESPONSE_MAX_DISTANCE

    _dbg_log_retrieve(
        "H4",
        "app/rag/case_rag/retrieve.py:rag_answer_internal",
        "retrieval_distances",
        {
            "case_id": str(case_id),
            "valid_pairs": len(valid_pairs),
            "best_distance": float(best_distance) if best_distance != float("inf") else None,
            "hallucination_risk": bool(hallucination_risk),
            "is_weak_response": bool(is_weak_response),
        },
    )

    # ✅ Baja calidad documental aumenta riesgo de alucinación
    if quality_score < LEGAL_QUALITY_SCORE_WARNING_THRESHOLD:
        # Si calidad es baja, marcar como riesgo de alucinación incluso con mejor similitud
        if not hallucination_risk and quality_score < 65:
            hallucination_risk = True
            warnings.append(
                "Riesgo de alucinación elevado debido a baja calidad documental del caso."
            )

    # ✅ Añadir warnings orientados a valor legal (no técnico)
    if is_weak_response:
        warnings.append(
            "⚠️ La información encontrada tiene baja relevancia para la consulta. "
            "Se recomienda revisar manualmente la respuesta y contrastarla con la documentación original."
        )

    if hallucination_risk:
        warnings.append(
            f"⚠️ RIESGO LEGAL: Alto riesgo de que la respuesta contenga información incorrecta o inventada. "
            f"Calidad documental: {quality_score:.1f}/100. "
            "Se requiere verificación exhaustiva con la documentación original antes de usar esta respuesta."
        )

    # REGLA 3: Evidencia obligatoria - enriquecer sources con metadata completa
    for text, meta, distance in valid_pairs:
        # Los tipos ya están validados y convertidos en el paso anterior
        document_id = meta["document_id"]
        chunk_index = meta["chunk_index"]

        # Obtener chunk desde BD para metadata completa (chunk_id, page, offsets)
        # ✅ SEGURIDAD: Filtrar por case_id para prevenir acceso cross-case
        chunk = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.case_id == case_id,  # ✅ CRÍTICO: Aislamiento por expediente
                DocumentChunk.document_id == document_id,
                DocumentChunk.chunk_index == chunk_index,
            )
            .first()
        )

        # ✅ SEGURIDAD: Si el chunk no pertenece a este case_id, skipear
        if not chunk:
            continue  # Chunk no encontrado o no pertenece a este caso

        # FASE 4: Validar que el chunk tiene location obligatoria
        try:
            validate_chunk_has_location(chunk)
        except Exception as e:
            # Si el chunk no tiene location válida, skipear
            if RAG_TRACE_DECISIONS:
                print(f"[RAG] ⚠️ Chunk sin location válida skipeado: {e}")
            continue

        # Construir fuente con TODA la metadata necesaria para citación
        source = {
            "document_id": document_id,
            "chunk_index": chunk_index,
            "content": text,
            "similarity_score": round(distance, 4),
        }

        if chunk:
            # REGLA 3: Metadata obligatoria para citación precisa
            source["chunk_id"] = chunk.chunk_id
            source["page"] = chunk.page
            source["start_char"] = chunk.start_char
            source["end_char"] = chunk.end_char
            source["section_hint"] = chunk.section_hint

            # Obtener filename para citación
            if chunk.document:
                source["filename"] = chunk.document.filename

        context_blocks.append(f"[Documento {document_id} | Chunk {chunk_index}]\n{text}")
        sources.append(source)

    # Debug: señales de keyword en el contexto (sin loguear texto)
    try:
        ctx = ("\n\n".join(context_blocks) or "").lower()
        _dbg_log_retrieve(
            "H5",
            "app/rag/case_rag/retrieve.py:rag_answer_internal",
            "context_signals",
            {
                "case_id": str(case_id),
                "context_len": len(ctx),
                "ctx_has_domicilio": "domicilio" in ctx,
                "ctx_has_apoder": ("apoder" in ctx) or ("poder" in ctx),
                "ctx_has_insolv": "insolv" in ctx,
            },
        )
    except Exception:
        pass

    context = "\n\n".join(context_blocks)

    # --------------------------------------------------
    # 🔒 FASE 4: VALIDAR EVIDENCIA ANTES DE CONTINUAR
    # --------------------------------------------------
    # FAIL HARD si no hay evidencia suficiente
    try:
        validate_retrieval_result(sources, case_id)
    except Exception as validation_error:
        if RAG_TRACE_DECISIONS:
            print(f"[RAG] ❌ Validación de evidencia falló: {validation_error}")

        # Retornar NO_RELEVANT_CONTEXT con información del error
        return RAGInternalResult(
            status="NO_RELEVANT_CONTEXT",
            context_text="",
            sources=[],
            confidence="baja",
            warnings=warnings + [str(validation_error)],
            hallucination_risk=False,
            evidence=None,
            no_response_reason=NoResponseReasonCode.EVIDENCE_INSUFFICIENT,
        )

    # --------------------------------------------------
    # 🔒 ENDURECIMIENTO #4: VALIDAR EVIDENCIA (FAIL HARD)
    # --------------------------------------------------
    evidence = build_retrieval_evidence(sources)
    reason_code = apply_evidence_gates(evidence)

    # Logging obligatorio
    log_evidence_decision(
        case_id=case_id,
        evidence=evidence,
        reason_code=reason_code,
    )

    # GATE BLOQUEANTE: Si evidencia insuficiente → NO_RESPONSE
    if reason_code:
        if RAG_TRACE_DECISIONS:
            print(f"[RAG DECISIÓN] ❌ NO_RESPONSE: {reason_code.value}")
            print(f"[RAG DECISIÓN] Evidence stats: {evidence.get_stats()}")

        return RAGInternalResult(
            status="NO_RELEVANT_CONTEXT",
            context_text="",
            sources=[],
            confidence="baja",
            warnings=warnings
            + [
                f"NO_RESPONSE: {reason_code.value}",
                f"Valid chunks: {evidence.valid_chunks}/{evidence.total_chunks}",
                f"Avg similarity: {evidence.avg_similarity:.4f}",
            ],
            hallucination_risk=False,
            evidence=evidence,
            no_response_reason=reason_code,
        )

    # ✅ Determinar confianza basada en cantidad, calidad de similitud Y calidad documental
    if len(valid_pairs) < top_k:
        warnings.append(
            "⚠️ La respuesta se basa en información parcial de la documentación. "
            "Puede omitir información relevante."
        )
        confidence: ConfidenceLevel = "media"
        status: RAGStatus = "PARTIAL_CONTEXT"
    else:
        # Si tenemos suficientes resultados, la confianza depende de:
        # 1. Calidad de similitud (distancia)
        # 2. Calidad documental del caso (quality_score)

        # Baja calidad documental reduce confianza
        if quality_score < 65:
            confidence = "baja"  # Calidad muy baja = baja confianza
            status = "OK"
        elif hallucination_risk or quality_score < LEGAL_QUALITY_SCORE_WARNING_THRESHOLD:
            confidence = "baja"  # Alto riesgo de alucinación o calidad baja = baja confianza
            status = "OK"
        elif is_weak_response:
            confidence = "media"  # Respuesta débil = confianza media
            status = "OK"
        else:
            confidence = "alta"  # Buena similitud y calidad = alta confianza
            status = "OK"

    # --------------------------------------------------
    # 6️⃣ Devolver contexto crudo (sin LLM)
    # --------------------------------------------------
    # RAG solo recupera contexto, NO genera respuestas

    # REGLA 6: Decisión trazable
    if RAG_TRACE_DECISIONS:
        print(f"\n{'='*80}")
        print(f"[RAG DECISIÓN] case_id={case_id}")
        print("[RAG DECISIÓN] ✅ RESPUESTA_CON_EVIDENCIA")
        print(f"[RAG DECISIÓN] Chunks recuperados: {len(sources)}")
        print(f"[RAG DECISIÓN] Confianza: {confidence}")
        print(f"[RAG DECISIÓN] Riesgo alucinación: {'SÍ' if hallucination_risk else 'NO'}")
        print(f"[RAG DECISIÓN] Calidad documental: {quality_score:.1f}/100")
        print("[RAG DECISIÓN] Chunks usados:")
        for i, src in enumerate(sources, 1):
            print(
                f"  {i}. chunk_id={src.get('chunk_id', 'N/A')[:16]}... | "
                f"doc={src['document_id'][:8]}... | "
                f"score={src['similarity_score']:.3f} | "
                f"page={src.get('page', 'N/A')}"
            )
        print(f"{'='*80}\n")

    return RAGInternalResult(
        status=status,
        context_text=context,  # Contexto crudo concatenado
        sources=sources,
        confidence=confidence,
        warnings=warnings,
        hallucination_risk=hallucination_risk,  # ✅ Incluir flag de riesgo de alucinación
        evidence=evidence,  # ✅ Evidencia verificable
        no_response_reason=None,  # Sin bloqueo, evidencia válida
    )
