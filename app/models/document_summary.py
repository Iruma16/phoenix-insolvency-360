"""
DOCUMENT SUMMARY - Modelo de vista para gestión de documentos (PANTALLA 1).

PRINCIPIO: Este modelo NO modifica el dominio.
Solo lee el estado real del core y lo expone para la UI.

NO permite:
- editar documentos
- borrar documentos
- reintentar ingesta desde UI
- modificar estados
- sobrescribir resultados
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    """
    Estado de procesamiento de un documento.
    
    CALCULADO a partir del estado real del core:
    - PENDING: documento registrado pero no procesado aún
    - INGESTED: documento procesado exitosamente, chunks generados
    - FAILED: documento rechazado por validación o error en procesamiento
    """
    PENDING = "pending"
    INGESTED = "ingested"
    FAILED = "failed"


class DocumentSummary(BaseModel):
    """
    Resumen de un documento para la UI.
    
    CONTRATO:
    - document_id: identificador único del documento
    - case_id: caso al que pertenece
    - filename: nombre del archivo original
    - file_type: tipo de archivo (PDF, DOCX, etc)
    - status: estado calculado desde el core
    - chunks_count: número real de chunks generados
    - error_message: mensaje de error si status=FAILED
    - created_at: timestamp de creación
    
    Este modelo es READ-ONLY desde la perspectiva de la UI.
    """
    document_id: str = Field(
        ...,
        description="Identificador único del documento",
        min_length=1
    )
    
    case_id: str = Field(
        ...,
        description="ID del caso al que pertenece el documento",
        min_length=1
    )
    
    filename: str = Field(
        ...,
        description="Nombre del archivo original",
        min_length=1
    )
    
    file_type: str = Field(
        ...,
        description="Tipo de archivo (PDF, DOCX, TXT, etc)",
        min_length=1
    )
    
    status: DocumentStatus = Field(
        ...,
        description="Estado de procesamiento calculado desde el core"
    )
    
    chunks_count: int = Field(
        default=0,
        description="Número real de chunks generados",
        ge=0
    )
    
    error_message: Optional[str] = Field(
        None,
        description="Mensaje de error si status=FAILED"
    )
    
    created_at: datetime = Field(
        ...,
        description="Timestamp de creación del documento"
    )
    
    # =====================================================
    # DEDUPLICACIÓN (FASE 2A)
    # =====================================================
    
    is_duplicate: bool = Field(
        default=False,
        description="Indica si este documento es un duplicado de otro"
    )
    
    duplicate_of_document_id: Optional[str] = Field(
        None,
        description="ID del documento original del que este es duplicado"
    )
    
    duplicate_of_filename: Optional[str] = Field(
        None,
        description="Nombre del archivo original del que este es duplicado"
    )
    
    duplicate_similarity: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Score de similaridad con el documento original (0.0-1.0)"
    )
    
    duplicate_action: Optional[str] = Field(
        None,
        description="Acción del abogado: pending, keep_both, mark_duplicate, exclude_from_analysis"
    )
    
    model_config = {"extra": "forbid"}

