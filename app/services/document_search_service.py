"""
Servicio de búsqueda documental (MVP).

Enfoque:
- Filtros por case_id, doc_type(s) o categoría abogado-friendly.
- Texto libre (q) sobre filename + chunks (MVP).
- Devuelve snippet + page (si hay chunks).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.doc_types import expand_category_to_doc_types
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_search import DocumentSearchResponse, DocumentSearchResult


@dataclass(frozen=True)
class DocumentSearchParams:
    q: Optional[str] = None
    doc_types: Optional[list[str]] = None
    category: Optional[str] = None
    page: int = 1
    page_size: int = 20
    include_chunk_id: bool = False


def _build_snippet(content: str, q: Optional[str]) -> str:
    if not content:
        return ""
    text = content.strip().replace("\n", " ")
    if not q:
        return text[:200]

    qn = q.strip()
    if not qn:
        return text[:200]

    low = text.lower()
    idx = low.find(qn.lower())
    if idx < 0:
        return text[:200]

    start = max(0, idx - 80)
    end = min(len(text), idx + len(qn) + 80)
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def search_documents(
    *,
    db: Session,
    case_id: str,
    params: DocumentSearchParams,
) -> DocumentSearchResponse:
    """
    Busca documentos en un caso.

    MVP: q busca en filename y en chunks (case-insensitive).
    """

    page = max(1, int(params.page or 1))
    page_size = max(1, min(200, int(params.page_size or 20)))

    effective_doc_types: Optional[list[str]] = None
    if params.doc_types:
        effective_doc_types = [t for t in params.doc_types if isinstance(t, str) and t.strip()]
    if params.category and not effective_doc_types:
        effective_doc_types = expand_category_to_doc_types(params.category)

    base = db.query(Document).filter(
        Document.case_id == case_id,
        Document.deleted_at.is_(None),
    )

    q = (params.q or "").strip()
    if q:
        # Recall alto:
        # - filename / raw_text
        # - OR match en chunks (aunque raw_text esté vacío o incompleto)
        q_like = f"%{q}%"
        q_lower = q.lower()
        chunk_doc_ids = (
            db.query(DocumentChunk.document_id)
            .join(Document, Document.document_id == DocumentChunk.document_id)
            .filter(
                Document.case_id == case_id,
                Document.deleted_at.is_(None),
                func.lower(DocumentChunk.content).like(f"%{q_lower}%"),
            )
            .distinct()
            .subquery()
        )
        base = base.filter(
            or_(
                Document.filename.ilike(q_like),
                Document.raw_text.ilike(q_like),
                Document.document_id.in_(select(chunk_doc_ids.c.document_id)),
            )
        )

    if effective_doc_types:
        base = base.filter(Document.doc_type.in_(effective_doc_types))

    total = int(base.count())

    docs = (
        base.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items: list[DocumentSearchResult] = []
    q_lower2 = q.lower() if q else None

    for doc in docs:
        chunk = None
        # Si hay query, SOLO usamos chunk/snippet si hay match real.
        if q_lower2:
            chunk = (
                db.query(DocumentChunk)
                .filter(
                    DocumentChunk.document_id == doc.document_id,
                    func.lower(DocumentChunk.content).like(f"%{q_lower2}%"),
                )
                .order_by(func.coalesce(DocumentChunk.page_start, 0).asc(), DocumentChunk.chunk_index.asc())
                .first()
            )
        # Sin query, podemos mostrar primer chunk como vista previa.
        if chunk is None and not q_lower2:
            chunk = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == doc.document_id)
                .order_by(func.coalesce(DocumentChunk.page_start, 0).asc(), DocumentChunk.chunk_index.asc())
                .first()
            )

        snippet = None
        page_num = None
        chunk_id = None

        if chunk and chunk.content:
            # chunk match (si q existe) o primer chunk (si q no existe)
            snippet = _build_snippet(chunk.content, q) if q else _build_snippet(chunk.content, None)
            page_num = chunk.page_start if chunk.page_start else None
            if params.include_chunk_id:
                chunk_id = chunk.chunk_id
        else:
            # Fallback: si el match fue por raw_text, usar snippet de raw_text (sin página/chunk)
            if q and doc.raw_text and q_lower2 and q_lower2 in (doc.raw_text.lower()):
                snippet = _build_snippet(doc.raw_text, q)
                page_num = None
                chunk_id = None

        confidence = float(doc.doc_type_confidence) if doc.doc_type_confidence is not None else 0.0
        confidence = max(0.0, min(1.0, confidence))

        items.append(
            DocumentSearchResult(
                document_id=doc.document_id,
                filename=doc.filename,
                doc_type=doc.doc_type,
                created_at=doc.created_at,
                source=doc.source,
                snippet=snippet,
                page=page_num,
                chunk_id=chunk_id,
                confidence=confidence,
            )
        )

    return DocumentSearchResponse(items=items, page=page, page_size=page_size, total=total)

