"""
CHUNK SUMMARY - Modelo de vista para exploración de chunks (PANTALLA 2).

PRINCIPIO: Este modelo NO interpreta ni analiza.
Solo expone los datos EXACTOS del core para inspección.

NO permite:
- generar texto
- resumir o clasificar
- ocultar location u offsets
- modificar contenido
- inferir significado
- ejecutar análisis o LLM
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ChunkLocationSummary(BaseModel):
    """
    Location física de un chunk en el documento original.

    Datos EXACTOS del contrato de DocumentChunk.
    """

    start_char: int = Field(..., description="Offset de inicio en texto original", ge=0)

    end_char: int = Field(..., description="Offset de fin en texto original", ge=0)

    page_start: Optional[int] = Field(
        None, description="Página de inicio (1-indexed, si aplica)", ge=1
    )

    page_end: Optional[int] = Field(None, description="Página de fin (1-indexed, si aplica)", ge=1)

    extraction_method: str = Field(
        ..., description="Método de extracción del texto (pdf_text, ocr, table, etc)"
    )

    model_config = {"extra": "forbid"}


class ChunkSummary(BaseModel):
    """
    Resumen de un chunk para inspección en la UI.

    CONTRATO:
    - chunk_id: identificador único del chunk
    - case_id: caso al que pertenece
    - document_id: documento de origen
    - filename: nombre del archivo original
    - content: texto LITERAL del chunk (sin modificar)
    - location: información física de ubicación (OBLIGATORIA)
    - created_at: timestamp de creación

    Este modelo es READ-ONLY y NO INTERPRETA.
    Solo expone datos exactos del core.
    """

    chunk_id: str = Field(..., description="Identificador único del chunk", min_length=1)

    case_id: str = Field(..., description="ID del caso al que pertenece", min_length=1)

    document_id: str = Field(..., description="ID del documento de origen", min_length=1)

    filename: str = Field(..., description="Nombre del archivo original", min_length=1)

    content: str = Field(..., description="Texto LITERAL del chunk (sin modificar)", min_length=1)

    location: ChunkLocationSummary = Field(
        ..., description="Información física de ubicación (OBLIGATORIA)"
    )

    created_at: datetime = Field(..., description="Timestamp de creación del chunk")

    model_config = {"extra": "forbid"}
