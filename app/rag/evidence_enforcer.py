"""
ENFORCEMENT DE EVIDENCIA OBLIGATORIA (FASE 4 - ENDURECIMIENTO 4).

REGLAS DURAS:
1. NO retrieve sin chunks → excepción
2. NO chunks sin location → excepción
3. NO respuesta sin evidencia mínima → excepción
4. TODO chunk DEBE cumplir contrato DocumentChunk

Este módulo valida ANTES del LLM call.
"""
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.rag.exceptions import (
    NoChunksFoundError,
    InvalidChunkLocationError,
    InsufficientEvidenceError,
)


# Umbrales duros para FASE 4
MIN_CHUNKS_FOR_RESPONSE = 2
MIN_SIMILARITY_THRESHOLD = 0.7


def validate_chunk_has_location(chunk: DocumentChunk) -> None:
    """
    Valida que un chunk tenga location obligatoria.
    
    FAIL HARD si falta:
    - start_char
    - end_char  
    - extraction_method
    
    Raises:
        InvalidChunkLocationError: Si location es inválida
    """
    if chunk.start_char is None:
        raise InvalidChunkLocationError(
            chunk_id=chunk.chunk_id,
            reason="start_char es None"
        )
    
    if chunk.end_char is None:
        raise InvalidChunkLocationError(
            chunk_id=chunk.chunk_id,
            reason="end_char es None"
        )
    
    if chunk.start_char >= chunk.end_char:
        raise InvalidChunkLocationError(
            chunk_id=chunk.chunk_id,
            reason=f"start_char ({chunk.start_char}) >= end_char ({chunk.end_char})"
        )
    
    if not chunk.extraction_method:
        raise InvalidChunkLocationError(
            chunk_id=chunk.chunk_id,
            reason="extraction_method es None"
        )


def validate_chunks_exist(db: Session, case_id: str, document_ids: List[str]) -> int:
    """
    Valida que existan chunks para los documentos.
    
    FAIL HARD si no hay chunks.
    
    Returns:
        Número de chunks encontrados
        
    Raises:
        NoChunksFoundError: Si no hay chunks
    """
    chunks_count = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.case_id == case_id,
            DocumentChunk.document_id.in_(document_ids),
        )
        .count()
    )
    
    if chunks_count == 0:
        raise NoChunksFoundError(case_id=case_id)
    
    return chunks_count


def enforce_evidence_quality(
    sources: List[Dict[str, Any]],
    case_id: str,
    min_chunks: int = MIN_CHUNKS_FOR_RESPONSE,
) -> None:
    """
    Enforce que la evidencia cumpla requisitos mínimos.
    
    FAIL HARD si:
    - Menos de min_chunks fuentes
    - Alguna fuente sin chunk_id
    - Alguna fuente sin location
    
    Args:
        sources: Lista de fuentes recuperadas
        case_id: ID del caso
        min_chunks: Mínimo de chunks requeridos
        
    Raises:
        InsufficientEvidenceError: Si evidencia es insuficiente
        InvalidChunkLocationError: Si algún chunk no tiene location
    """
    if len(sources) < min_chunks:
        raise InsufficientEvidenceError(
            case_id=case_id,
            chunks_found=len(sources),
            min_required=min_chunks,
        )
    
    # Validar que cada fuente tenga chunk_id y location
    for source in sources:
        chunk_id = source.get("chunk_id")
        if not chunk_id:
            raise InvalidChunkLocationError(
                chunk_id="UNKNOWN",
                reason="Fuente sin chunk_id"
            )
        
        # Validar location fields
        if source.get("start_char") is None:
            raise InvalidChunkLocationError(
                chunk_id=chunk_id,
                reason="start_char faltante en fuente"
            )
        
        if source.get("end_char") is None:
            raise InvalidChunkLocationError(
                chunk_id=chunk_id,
                reason="end_char faltante en fuente"
            )


def validate_retrieval_result(
    sources: List[Dict[str, Any]],
    case_id: str,
) -> None:
    """
    Validación completa del resultado de retrieval.
    
    FAIL HARD si no cumple requisitos de FASE 4.
    
    Args:
        sources: Fuentes recuperadas
        case_id: ID del caso
        
    Raises:
        RAGEvidenceError: Si evidencia no es válida
    """
    # 1. Validar que hay evidencia mínima
    enforce_evidence_quality(sources, case_id)
    
    # 2. Validar que todas las fuentes tienen metadata completa
    for source in sources:
        if not source.get("chunk_id"):
            raise InvalidChunkLocationError(
                chunk_id="UNKNOWN",
                reason="Chunk sin chunk_id"
            )
        
        if not source.get("document_id"):
            raise InvalidChunkLocationError(
                chunk_id=source.get("chunk_id", "UNKNOWN"),
                reason="Chunk sin document_id"
            )
        
        if not source.get("content"):
            raise InvalidChunkLocationError(
                chunk_id=source.get("chunk_id", "UNKNOWN"),
                reason="Chunk sin content"
            )

