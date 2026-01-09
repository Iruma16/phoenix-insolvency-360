"""
EVIDENCIA VERIFICABLE PARA RAG (Endurecimiento #4)

PRINCIPIO: El sistema NO RESPONDE sin evidencia suficiente y verificable.
NO se permite inferir, rellenar o responder con disclaimer.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime


RETRIEVAL_VERSION = "1.0.0"

# UMBRALES DUROS (gates bloqueantes)
MIN_CHUNKS_REQUIRED = 2
MIN_AVG_SIMILARITY = 0.5
MIN_VALID_CHUNK_RATIO = 0.5


class NoResponseReasonCode(str, Enum):
    """Códigos normalizados para NO_RESPONSE."""
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
    EVIDENCE_WEAK = "EVIDENCE_WEAK"
    EVIDENCE_INVALID = "EVIDENCE_INVALID"


@dataclass
class DocumentChunkEvidence:
    """
    Chunk de documento con metadata completa de trazabilidad.
    
    Todos los campos son OBLIGATORIOS para considerarse evidencia válida.
    """
    chunk_id: str
    document_id: str
    content: str
    similarity_score: float
    
    # Metadata de trazabilidad (OBLIGATORIA)
    source_hash: Optional[str] = None
    page_number: Optional[int] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    filename: Optional[str] = None


@dataclass
class RetrievalEvidence:
    """
    Contrato de salida del retrieval con evidencia verificable.
    
    Si valid_chunks < MIN_CHUNKS_REQUIRED → NO_RESPONSE
    Si avg_similarity < MIN_AVG_SIMILARITY → NO_RESPONSE
    """
    chunks: List[DocumentChunkEvidence]
    total_chunks: int
    valid_chunks: int
    min_similarity: float
    max_similarity: float
    avg_similarity: float
    retrieval_version: str
    timestamp: datetime
    
    def is_sufficient(self) -> bool:
        """Retorna True si la evidencia es suficiente para responder."""
        return (
            self.valid_chunks >= MIN_CHUNKS_REQUIRED and
            self.avg_similarity >= MIN_AVG_SIMILARITY
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Estadísticas de evidencia para logging."""
        return {
            "total_chunks": self.total_chunks,
            "valid_chunks": self.valid_chunks,
            "min_similarity": round(self.min_similarity, 4),
            "max_similarity": round(self.max_similarity, 4),
            "avg_similarity": round(self.avg_similarity, 4),
            "retrieval_version": self.retrieval_version,
        }


@dataclass
class NoResponseResult:
    """
    Resultado cuando el sistema NO puede responder por falta de evidencia.
    
    NO contiene:
    - respuesta generada
    - texto inferido
    - disclaimer
    """
    response: None
    status: str  # "NO_RESPONSE"
    reason_code: NoResponseReasonCode
    evidence: RetrievalEvidence
    message: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa a diccionario."""
        return {
            "response": None,
            "status": self.status,
            "reason_code": self.reason_code.value,
            "evidence": self.evidence.get_stats(),
            "message": self.message,
        }


def validate_chunk_evidence(chunk_data: dict) -> Optional[DocumentChunkEvidence]:
    """
    Valida que un chunk tenga TODA la metadata obligatoria.
    
    Returns:
        DocumentChunkEvidence si válido, None si inválido
    """
    try:
        # Campos OBLIGATORIOS
        chunk_id = chunk_data.get("chunk_id")
        document_id = chunk_data.get("document_id")
        content = chunk_data.get("content")
        similarity_score = chunk_data.get("similarity_score")
        
        if not all([chunk_id, document_id, content, similarity_score is not None]):
            return None
        
        # Metadata de trazabilidad (opcional pero recomendada)
        source_hash = chunk_data.get("source_hash")
        page_number = chunk_data.get("page")
        start_char = chunk_data.get("start_char")
        end_char = chunk_data.get("end_char")
        filename = chunk_data.get("filename")
        
        return DocumentChunkEvidence(
            chunk_id=chunk_id,
            document_id=document_id,
            content=content,
            similarity_score=float(similarity_score),
            source_hash=source_hash,
            page_number=page_number,
            start_char=start_char,
            end_char=end_char,
            filename=filename,
        )
    except (ValueError, TypeError):
        return None


def build_retrieval_evidence(chunks: List[dict]) -> RetrievalEvidence:
    """
    Construye RetrievalEvidence desde lista de chunks raw.
    
    Valida cada chunk y calcula estadísticas de similitud.
    """
    validated_chunks = []
    
    for chunk_data in chunks:
        validated = validate_chunk_evidence(chunk_data)
        if validated:
            validated_chunks.append(validated)
    
    total_chunks = len(chunks)
    valid_chunks = len(validated_chunks)
    
    if valid_chunks == 0:
        # Sin chunks válidos
        return RetrievalEvidence(
            chunks=[],
            total_chunks=total_chunks,
            valid_chunks=0,
            min_similarity=0.0,
            max_similarity=0.0,
            avg_similarity=0.0,
            retrieval_version=RETRIEVAL_VERSION,
            timestamp=datetime.now(),
        )
    
    # Calcular estadísticas de similitud
    similarities = [c.similarity_score for c in validated_chunks]
    min_sim = min(similarities)
    max_sim = max(similarities)
    avg_sim = sum(similarities) / len(similarities)
    
    return RetrievalEvidence(
        chunks=validated_chunks,
        total_chunks=total_chunks,
        valid_chunks=valid_chunks,
        min_similarity=min_sim,
        max_similarity=max_sim,
        avg_similarity=avg_sim,
        retrieval_version=RETRIEVAL_VERSION,
        timestamp=datetime.now(),
    )


def apply_evidence_gates(evidence: RetrievalEvidence) -> Optional[NoResponseReasonCode]:
    """
    Aplica gates bloqueantes sobre la evidencia.
    
    Returns:
        NoResponseReasonCode si algún gate falla, None si pasa todos los gates
    """
    # GATE 1: total_chunks == 0
    if evidence.total_chunks == 0:
        return NoResponseReasonCode.EVIDENCE_MISSING
    
    # GATE 2: valid_chunks < MIN_CHUNKS_REQUIRED
    if evidence.valid_chunks < MIN_CHUNKS_REQUIRED:
        return NoResponseReasonCode.EVIDENCE_INSUFFICIENT
    
    # GATE 3: avg_similarity < MIN_AVG_SIMILARITY
    if evidence.avg_similarity < MIN_AVG_SIMILARITY:
        return NoResponseReasonCode.EVIDENCE_WEAK
    
    # Todos los gates pasaron
    return None


def log_evidence_decision(
    case_id: str,
    evidence: RetrievalEvidence,
    reason_code: Optional[NoResponseReasonCode],
) -> None:
    """
    Logging estructurado obligatorio de decisión de evidencia.
    """
    from app.core.logger import logger
    
    logger.info("=" * 80)
    logger.info("[EVIDENCE DECISION] Resultado")
    logger.info(f"  Case ID: {case_id}")
    logger.info(f"  Retrieval Version: {evidence.retrieval_version}")
    logger.info(f"  Timestamp: {evidence.timestamp.isoformat()}")
    logger.info(f"  Total Chunks: {evidence.total_chunks}")
    logger.info(f"  Valid Chunks: {evidence.valid_chunks}")
    logger.info(f"  Min Similarity: {evidence.min_similarity:.4f}")
    logger.info(f"  Max Similarity: {evidence.max_similarity:.4f}")
    logger.info(f"  Avg Similarity: {evidence.avg_similarity:.4f}")
    
    if reason_code:
        logger.error(f"  Status: NO_RESPONSE")
        logger.error(f"  Reason Code: {reason_code.value}")
        logger.error(f"  Decision: BLOCKED - Insufficient evidence")
    else:
        logger.info(f"  Status: EVIDENCE_VALID")
        logger.info(f"  Decision: ALLOWED - Sufficient evidence")
    
    logger.info("=" * 80)

