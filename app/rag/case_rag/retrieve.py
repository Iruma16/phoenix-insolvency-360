from __future__ import annotations

from typing import List, Literal, Optional
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session
from openai import OpenAI

from app.core.variables import (
    RAG_AUTO_BUILD_EMBEDDINGS,
    EMBEDDING_MODEL,
    RAG_MIN_SIMILARITY_SCORE,
    RAG_WEAK_RESPONSE_MAX_DISTANCE,
    RAG_HALLUCINATION_RISK_THRESHOLD,
    LEGAL_QUALITY_SCORE_BLOCK_THRESHOLD,
    LEGAL_QUALITY_SCORE_WARNING_THRESHOLD,
)
from app.services.embeddings_pipeline import (
    get_case_collection,
    build_embeddings_for_case,
)
from app.services.document_chunk_pipeline import (
    build_document_chunks_for_case,
)
from app.services.document_quality import get_document_quality_summary
from app.models.document import Document
from app.models.document_chunk import DocumentChunk


# =========================================================
# ESTADOS INTERNOS RAG
# =========================================================

RAGStatus = Literal[
    "OK",
    "CASE_NOT_FOUND",
    "NO_CHUNKS",
    "NO_EMBEDDINGS",
    "NO_RELEVANT_CONTEXT",
    "PARTIAL_CONTEXT",
]

ConfidenceLevel = Literal["alta", "media", "baja"]


@dataclass
class RAGInternalResult:
    status: RAGStatus
    context_text: str  # Contexto crudo concatenado de chunks
    sources: List[dict]  # Lista de chunks con metadatos y scores
    confidence: ConfidenceLevel
    warnings: List[str]
    hallucination_risk: bool = False  # True si hay alto riesgo de alucinación


# =========================================================
# FUNCIÓN RAG (CEREBRO ÚNICO)
# =========================================================

def rag_answer_internal(
    *,
    db: Session,
    case_id: str,
    question: str,
    top_k: int,
    doc_types: Optional[List[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> RAGInternalResult:

    warnings: List[str] = []

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
                "Se requieren conclusiones manuales hasta que la documentación esté completamente procesada."
            ] + legal_risks,
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
    query = db.query(Document).filter(Document.case_id == case_id)

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
    chunks_count = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.case_id == case_id,
            DocumentChunk.document_id.in_(document_ids),
        )
        .count()
    )

    if chunks_count == 0:
        warnings.append(
            "No había chunks y se ha ejecutado el chunking automáticamente."
        )

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
    try:
        collection = get_case_collection(case_id)
        if collection.count() == 0:
            raise ValueError("Vectorstore vacío")
    except Exception:
        if not RAG_AUTO_BUILD_EMBEDDINGS:
            return RAGInternalResult(
                status="NO_EMBEDDINGS",
                context_text="",  # Sin embeddings disponibles
                sources=[],
                confidence="baja",
                warnings=warnings,
                hallucination_risk=False,
            )

        warnings.append(
            "El índice semántico no existía y se ha generado automáticamente."
        )
        build_embeddings_for_case(db=db, case_id=case_id)
        collection = get_case_collection(case_id)

    # --------------------------------------------------
    # 4️⃣ Búsqueda semántica
    # --------------------------------------------------
    # Generar embedding de la pregunta usando el mismo modelo que los embeddings almacenados
    openai_client = OpenAI()
    question_embedding = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[question],
    ).data[0].embedding

    results = collection.query(
        query_embeddings=[question_embedding],
        n_results=top_k,
        include=["metadatas", "documents", "distances"],  # ✅ Incluir distancias
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
            valid_pairs.append((text, {"document_id": document_id, "chunk_index": chunk_index}, distance))
        except Exception as e:
            # Si hay algún error procesando este elemento, saltarlo
            print(f"[WARN] Error procesando elemento en validación: {e}")
            continue

    if not valid_pairs:
        return RAGInternalResult(
            status="NO_RELEVANT_CONTEXT",
            context_text="",  # Sin contexto válido encontrado
            sources=[],
            confidence="baja",
            warnings=warnings,
            hallucination_risk=False,
        )

    # ✅ Determinar riesgo de alucinación y respuesta débil basado en la mejor distancia
    # Usar umbral ajustado por calidad documental (baja calidad → más estricto)
    best_distance = valid_pairs[0][2] if valid_pairs else float('inf')
    hallucination_risk = best_distance > quality_adjusted_hallucination_threshold
    is_weak_response = best_distance > RAG_WEAK_RESPONSE_MAX_DISTANCE
    
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
            f"⚠️ La información encontrada tiene baja relevancia para la consulta. "
            "Se recomienda revisar manualmente la respuesta y contrastarla con la documentación original."
        )

    if hallucination_risk:
        warnings.append(
            f"⚠️ RIESGO LEGAL: Alto riesgo de que la respuesta contenga información incorrecta o inventada. "
            f"Calidad documental: {quality_score:.1f}/100. "
            "Se requiere verificación exhaustiva con la documentación original antes de usar esta respuesta."
        )

    for text, meta, distance in valid_pairs:
        # Los tipos ya están validados y convertidos en el paso anterior
        document_id = meta["document_id"]
        chunk_index = meta["chunk_index"]
        
        context_blocks.append(
            f"[Documento {document_id} | Chunk {chunk_index}]\n{text}"
        )
        sources.append(
            {
                "document_id": document_id,
                "chunk_index": chunk_index,
                "content": text,
                "similarity_score": round(distance, 4),  # ✅ Incluir score de similitud
            }
        )

    context = "\n\n".join(context_blocks)

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

    return RAGInternalResult(
        status=status,
        context_text=context,  # Contexto crudo concatenado
        sources=sources,
        confidence=confidence,
        warnings=warnings,
        hallucination_risk=hallucination_risk,  # ✅ Incluir flag de riesgo de alucinación
    )

