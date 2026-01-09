"""
CASE SUMMARY - Modelo de vista para gestión de casos (PANTALLA 0).

PRINCIPIO: Este modelo NO modifica el dominio.
Solo lee el estado real del core y lo expone para la UI.

NO permite:
- editar casos
- borrar casos
- modificar estados
- sobrescribir outputs
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AnalysisStatus(str, Enum):
    """
    Estado de análisis de un caso.
    
    CALCULADO a partir del estado real del core:
    - NOT_STARTED: caso existe pero no tiene documentos ni ejecuciones
    - IN_PROGRESS: tiene documentos pero no tiene output legal certificado
    - COMPLETED: tiene output legal certificado (LegalReport)
    - FAILED: última ejecución falló sin recuperación
    """
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class CaseSummary(BaseModel):
    """
    Resumen de un caso para la UI.
    
    CONTRATO:
    - case_id: identificador único del caso (generado por el core)
    - created_at: timestamp de creación
    - documents_count: número de documentos ingresados
    - last_execution_at: timestamp de última ejecución (si existe)
    - analysis_status: estado calculado desde el core
    
    Este modelo es READ-ONLY desde la perspectiva de la UI.
    """
    case_id: str = Field(
        ...,
        description="Identificador único del caso (generado por core)",
        min_length=1
    )
    
    name: str = Field(
        ...,
        description="Nombre del caso",
        min_length=1
    )
    
    created_at: datetime = Field(
        ...,
        description="Timestamp de creación del caso"
    )
    
    documents_count: int = Field(
        default=0,
        description="Número de documentos ingresados en el caso",
        ge=0
    )
    
    last_execution_at: Optional[datetime] = Field(
        None,
        description="Timestamp de última ejecución de análisis (si existe)"
    )
    
    analysis_status: AnalysisStatus = Field(
        ...,
        description="Estado de análisis calculado desde el core"
    )
    
    client_ref: Optional[str] = Field(
        None,
        description="Referencia del cliente (opcional)"
    )
    
    model_config = {"extra": "forbid"}


class CreateCaseRequest(BaseModel):
    """
    Request para crear un nuevo caso.
    
    MÍNIMO: solo requiere un nombre.
    El case_id se genera automáticamente en el core.
    """
    name: str = Field(
        ...,
        description="Nombre del caso",
        min_length=1,
        max_length=255
    )
    
    client_ref: Optional[str] = Field(
        None,
        description="Referencia del cliente (opcional)",
        max_length=255
    )
    
    model_config = {"extra": "forbid"}

