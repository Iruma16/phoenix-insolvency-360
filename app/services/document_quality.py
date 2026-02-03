"""
Servicio para generar resumen de calidad documental por caso.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.variables import CRITICAL_DOCUMENT_TYPES
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embeddings_pipeline import get_case_collection


def get_document_quality_summary(db: Session, case_id: str) -> dict[str, Any]:
    """
    Genera un resumen de calidad documental para un caso.

    Parámetros
    ----------
    db : Session
        Sesión de base de datos
    case_id : str
        ID del caso

    Retorna
    -------
    Dict con estadísticas de calidad documental
    """

    # 1. Estadísticas básicas de documentos
    total_documents = db.query(Document).filter(Document.case_id == case_id).count()

    # Por formato
    formats = (
        db.query(Document.file_format, func.count(Document.document_id))
        .filter(Document.case_id == case_id)
        .group_by(Document.file_format)
        .all()
    )
    format_distribution = {fmt: count for fmt, count in formats}

    # Por tipo
    types = (
        db.query(Document.doc_type, func.count(Document.document_id))
        .filter(Document.case_id == case_id)
        .group_by(Document.doc_type)
        .all()
    )
    type_distribution = {doc_type: count for doc_type, count in types}

    # 2. Estadísticas de chunks
    total_chunks = db.query(DocumentChunk).filter(DocumentChunk.case_id == case_id).count()

    # Chunks por documento
    chunks_per_doc = (
        db.query(DocumentChunk.document_id, func.count(DocumentChunk.chunk_id).label("chunk_count"))
        .filter(DocumentChunk.case_id == case_id)
        .group_by(DocumentChunk.document_id)
        .all()
    )

    avg_chunks_per_doc = total_chunks / total_documents if total_documents > 0 else 0
    docs_with_chunks = len(chunks_per_doc)
    docs_without_chunks = total_documents - docs_with_chunks

    # 3. Estadísticas de embeddings
    try:
        collection = get_case_collection(case_id)
        total_embeddings = collection.count()
    except Exception:
        total_embeddings = 0

    embeddings_coverage = (total_embeddings / total_chunks * 100) if total_chunks > 0 else 0

    # 4. Detectar posibles problemas (ORIENTADO A VALOR LEGAL)
    issues: list[str] = []
    legal_risks: list[str] = []  # Riesgos legales específicos

    if docs_without_chunks > 0:
        issues.append(
            f"{docs_without_chunks} documento(s) sin procesar (no disponible para búsqueda semántica)"
        )
        legal_risks.append(
            f"Información legal no indexada: {docs_without_chunks} documento(s) no disponible(s) para consulta"
        )

    if total_embeddings < total_chunks:
        missing_embeddings = total_chunks - total_embeddings
        issues.append(f"{missing_embeddings} fragmento(s) documental(es) sin índice semántico")
        legal_risks.append(
            f"Riesgo de omisión en análisis: {missing_embeddings} fragmento(s) no indexado(s)"
        )

    # ✅ ALERTA CRÍTICA: Documentos críticos sin embeddings
    critical_docs = (
        db.query(Document)
        .filter(Document.case_id == case_id, Document.doc_type.in_(CRITICAL_DOCUMENT_TYPES))
        .all()
    )

    critical_docs_without_chunks = []
    critical_docs_without_embeddings = []

    for doc in critical_docs:
        chunk_count = (
            db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.document_id).count()
        )

        if chunk_count == 0:
            critical_docs_without_chunks.append(doc)
        else:
            # Verificar embeddings (contar chunks que están en el vectorstore)
            try:
                collection = get_case_collection(case_id)
                # Obtener chunk_ids del documento
                chunk_ids = [
                    chunk.chunk_id
                    for chunk in db.query(DocumentChunk)
                    .filter(DocumentChunk.document_id == doc.document_id)
                    .all()
                ]
                # Verificar cuántos están en el vectorstore
                if chunk_ids:
                    existing = collection.get(ids=chunk_ids[:10], include=[])  # Sample
                    if len(existing.get("ids", [])) < min(10, len(chunk_ids)):
                        critical_docs_without_embeddings.append(doc)
            except Exception:
                critical_docs_without_embeddings.append(doc)

    if critical_docs_without_chunks:
        critical_names = [d.filename for d in critical_docs_without_chunks[:5]]
        legal_risks.append(
            f"⚠️ ALERTA LEGAL CRÍTICA: {len(critical_docs_without_chunks)} documento(s) legal(es) crítico(s) "
            f"sin procesar: {', '.join(critical_names)}"
        )

    if critical_docs_without_embeddings:
        critical_names = [d.filename for d in critical_docs_without_embeddings[:5]]
        legal_risks.append(
            f"⚠️ ALERTA LEGAL: {len(critical_docs_without_embeddings)} documento(s) legal(es) crítico(s) "
            f"sin índice semántico completo: {', '.join(critical_names)}"
        )

    # Archivos .doc legacy (riesgo técnico que puede afectar análisis)
    doc_legacy_count = format_distribution.get("doc", 0)
    if doc_legacy_count > 0:
        issues.append(
            f"{doc_legacy_count} archivo(s) .doc (formato legacy, puede requerir conversión)"
        )
        legal_risks.append(
            f"Riesgo de pérdida de información: {doc_legacy_count} documento(s) en formato legacy"
        )

    # 5. Calcular score de calidad (0-100)
    quality_score = 100

    # Penalizar documentos sin chunks
    if total_documents > 0:
        penalty_no_chunks = (docs_without_chunks / total_documents) * 30
        quality_score -= penalty_no_chunks

    # Penalizar chunks sin embeddings
    if total_chunks > 0:
        penalty_no_embeddings = ((total_chunks - total_embeddings) / total_chunks) * 40
        quality_score -= penalty_no_embeddings

    # Penalizar archivos legacy
    if total_documents > 0:
        penalty_legacy = (doc_legacy_count / total_documents) * 10
        quality_score -= penalty_legacy

    quality_score = max(0, min(100, quality_score))

    # Clasificar calidad
    if quality_score >= 90:
        quality_level = "excelente"
    elif quality_score >= 75:
        quality_level = "buena"
    elif quality_score >= 60:
        quality_level = "regular"
    elif quality_score >= 40:
        quality_level = "baja"
    else:
        quality_level = "crítica"

    return {
        "case_id": case_id,
        "quality_score": round(quality_score, 2),
        "quality_level": quality_level,
        "total_documents": total_documents,
        "documents_with_chunks": docs_with_chunks,
        "documents_without_chunks": docs_without_chunks,
        "total_chunks": total_chunks,
        "average_chunks_per_document": round(avg_chunks_per_doc, 2),
        "total_embeddings": total_embeddings,
        "embeddings_coverage_percent": round(embeddings_coverage, 2),
        "format_distribution": format_distribution,
        "type_distribution": type_distribution,
        "issues": issues,
        "issues_count": len(issues),
        "legal_risks": legal_risks,  # ✅ Riesgos legales específicos
        "legal_risks_count": len(legal_risks),
        "critical_documents_missing": len(critical_docs_without_chunks)
        + len(critical_docs_without_embeddings),
    }
