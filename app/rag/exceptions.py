"""
Excepciones para RAG con evidencia obligatoria (FASE 4 - ENDURECIMIENTO 4).

PRINCIPIO: El sistema NO RESPONDE sin evidencia.
Fallar explícitamente es mejor que responder sin base documental.
"""
from app.core.exceptions import PhoenixException, ErrorSeverity
from typing import Optional


class RAGEvidenceError(PhoenixException):
    """
    Excepción base cuando RAG no puede garantizar evidencia.
    
    FASE 4 (ENDURECIMIENTO 4):
    - NO chunks → excepción
    - Chunks sin location → excepción  
    - Evidencia insuficiente → excepción
    """
    
    def __init__(self, reason: str, case_id: Optional[str] = None, **kwargs):
        details = {"reason": reason}
        if case_id:
            details["case_id"] = case_id
        
        super().__init__(
            code="RAG_EVIDENCE_ERROR",
            message=f"RAG no puede responder: {reason}",
            details=details,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )


class NoChunksFoundError(RAGEvidenceError):
    """
    Excepción cuando no hay chunks disponibles para retrieval.
    
    FAIL HARD: No se puede responder sin chunks.
    """
    
    def __init__(self, case_id: str, **kwargs):
        super().__init__(
            reason="No hay chunks disponibles en el vectorstore",
            case_id=case_id,
            **kwargs
        )


class InvalidChunkLocationError(RAGEvidenceError):
    """
    Excepción cuando un chunk no tiene location válida.
    
    FAIL HARD: Chunk sin location no puede usarse como evidencia.
    """
    
    def __init__(self, chunk_id: str, reason: str, **kwargs):
        details = {
            "chunk_id": chunk_id,
            "validation_failed": reason
        }
        
        super().__init__(
            reason=f"Chunk {chunk_id[:16]}... sin location válida: {reason}",
            **kwargs
        )
        self.details.update(details)


class InsufficientEvidenceError(RAGEvidenceError):
    """
    Excepción cuando la evidencia recuperada es insuficiente.
    
    FAIL HARD: No se puede responder con evidencia débil.
    """
    
    def __init__(self, case_id: str, chunks_found: int, min_required: int, **kwargs):
        details = {
            "chunks_found": chunks_found,
            "min_required": min_required,
        }
        
        super().__init__(
            reason=f"Evidencia insuficiente: {chunks_found} chunks < {min_required} requeridos",
            case_id=case_id,
            **kwargs
        )
        self.details.update(details)

