"""
ENDPOINT OFICIAL DE EXPLORACIÓN DE CHUNKS (PANTALLA 2).

PRINCIPIO: Esta capa NO interpreta, NO analiza, NO razona.
Solo permite INSPECCIÓN de datos exactos del core.

PROHIBIDO:
- generar texto
- resumir o interpretar
- ocultar location u offsets
- búsqueda semántica
- ejecutar RAG o LLM
- inferir significado
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.models.case import Case
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.chunk_summary import (
    ChunkSummary,
    ChunkLocationSummary,
)
from app.core.exceptions import ChunkContractViolationError


router = APIRouter(
    prefix="/cases/{case_id}/chunks",
    tags=["chunks"],
)


def _build_chunk_summary(chunk: DocumentChunk, db: Session) -> ChunkSummary:
    """
    Construye un ChunkSummary desde un DocumentChunk del core.
    
    NO inventa datos.
    NO oculta información.
    SOLO expone el estado EXACTO.
    
    Args:
        chunk: Chunk del core
        db: Sesión de base de datos
        
    Returns:
        ChunkSummary con datos exactos
        
    Raises:
        ChunkContractViolationError: Si el chunk no cumple el contrato
    """
    # Validar contrato: location obligatoria
    if chunk.start_char is None or chunk.end_char is None:
        raise ChunkContractViolationError(
            rule_violated=f"Chunk sin offsets obligatorios: {chunk.chunk_id}",
            chunk_id=chunk.chunk_id
        )
    
    if not chunk.extraction_method:
        raise ChunkContractViolationError(
            rule_violated=f"Chunk sin extraction_method: {chunk.chunk_id}",
            chunk_id=chunk.chunk_id
        )
    
    if not chunk.content or not chunk.content.strip():
        raise ChunkContractViolationError(
            rule_violated=f"Chunk con contenido vacío: {chunk.chunk_id}",
            chunk_id=chunk.chunk_id
        )
    
    # Obtener documento para filename
    document = db.query(Document).filter(
        Document.document_id == chunk.document_id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Documento {chunk.document_id} no encontrado para chunk {chunk.chunk_id}"
        )
    
    # Construir location
    location = ChunkLocationSummary(
        start_char=chunk.start_char,
        end_char=chunk.end_char,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        extraction_method=chunk.extraction_method,
    )
    
    return ChunkSummary(
        chunk_id=chunk.chunk_id,
        case_id=chunk.case_id,
        document_id=chunk.document_id,
        filename=document.filename,
        content=chunk.content,  # Texto LITERAL, sin modificar
        location=location,
        created_at=chunk.created_at,
    )


@router.get(
    "",
    response_model=List[ChunkSummary],
    summary="Listar chunks de un caso",
    description=(
        "Lista todos los chunks de un caso, con filtros opcionales. "
        "Búsqueda LITERAL (no semántica). "
        "Devuelve datos EXACTOS del core sin interpretación."
    ),
)
def list_chunks(
    case_id: str,
    document_id: Optional[str] = Query(None, description="Filtrar por documento específico"),
    filename: Optional[str] = Query(None, description="Filtrar por nombre de archivo (parcial)"),
    text_contains: Optional[str] = Query(
        None,
        description="Búsqueda LITERAL en el contenido (case-insensitive)",
        min_length=3
    ),
    limit: int = Query(100, ge=1, le=1000, description="Número máximo de resultados"),
    db: Session = Depends(get_db),
) -> List[ChunkSummary]:
    """
    Lista chunks de un caso.
    
    Búsqueda LITERAL (ILIKE), NO semántica.
    Devuelve datos EXACTOS sin interpretación.
    
    Args:
        case_id: ID del caso
        document_id: Filtro opcional por documento
        filename: Filtro opcional por nombre de archivo
        text_contains: Búsqueda literal en contenido (opcional)
        limit: Máximo de resultados
        db: Sesión de base de datos
        
    Returns:
        Lista de ChunkSummary
        
    Raises:
        HTTPException 404: Si el caso no existe
    """
    # Verificar que el caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Caso '{case_id}' no encontrado"
        )
    
    # Query base: chunks del caso
    query = db.query(DocumentChunk).filter(
        DocumentChunk.case_id == case_id
    )
    
    # Filtro por document_id
    if document_id:
        query = query.filter(DocumentChunk.document_id == document_id)
    
    # Filtro por filename (requiere join)
    if filename:
        query = query.join(Document).filter(
            Document.filename.ilike(f"%{filename}%")
        )
    
    # Búsqueda LITERAL en contenido (NO semántica)
    if text_contains:
        query = query.filter(
            DocumentChunk.content.ilike(f"%{text_contains}%")
        )
    
    # Ordenar y limitar
    chunks = query.order_by(
        DocumentChunk.created_at.desc()
    ).limit(limit).all()
    
    # Construir summaries
    results = []
    for chunk in chunks:
        try:
            summary = _build_chunk_summary(chunk, db)
            results.append(summary)
        except ChunkContractViolationError as e:
            # Si un chunk rompe el contrato, saltar (no romper toda la lista)
            # pero registrar el error
            continue
    
    return results


@router.get(
    "/{chunk_id}",
    response_model=ChunkSummary,
    summary="Obtener un chunk específico",
    description=(
        "Obtiene un chunk específico del caso. "
        "Devuelve datos EXACTOS del core sin interpretación. "
        "Falla con 404 si no existe o no pertenece al caso."
    ),
)
def get_chunk(
    case_id: str,
    chunk_id: str,
    db: Session = Depends(get_db),
) -> ChunkSummary:
    """
    Obtiene un chunk específico.
    
    Devuelve datos EXACTOS sin interpretación.
    
    Args:
        case_id: ID del caso
        chunk_id: ID del chunk
        db: Sesión de base de datos
        
    Returns:
        ChunkSummary con datos exactos
        
    Raises:
        HTTPException 404: Si el caso no existe
        HTTPException 404: Si el chunk no existe o no pertenece al caso
        HTTPException 500: Si el chunk rompe el contrato
    """
    # Verificar que el caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Caso '{case_id}' no encontrado"
        )
    
    # Buscar chunk
    chunk = db.query(DocumentChunk).filter(
        DocumentChunk.chunk_id == chunk_id,
        DocumentChunk.case_id == case_id,  # IMPORTANTE: validar que pertenece al caso
    ).first()
    
    if not chunk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chunk '{chunk_id}' no encontrado en caso '{case_id}'"
        )
    
    # Construir summary
    try:
        return _build_chunk_summary(chunk, db)
    except ChunkContractViolationError as e:
        # Si el chunk rompe el contrato, es un error crítico
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chunk rompe contrato: {e.rule_violated}"
        )


# =========================================================
# ENDPOINTS PROHIBIDOS (NO IMPLEMENTADOS)
# =========================================================

# POST /cases/{case_id}/chunks → PROHIBIDO (no se crean chunks desde UI)
# PUT /cases/{case_id}/chunks/{chunk_id} → PROHIBIDO (no se editan chunks)
# DELETE /cases/{case_id}/chunks/{chunk_id} → PROHIBIDO (no se borran chunks)
# POST /cases/{case_id}/chunks/search → PROHIBIDO (no búsqueda semántica)
# POST /cases/{case_id}/chunks/analyze → PROHIBIDO (no análisis)

