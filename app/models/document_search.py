"""
Modelos para el buscador documental (UI abogado-friendly).

Contrato de salida para UI:
- document_id
- filename
- doc_type
- created_at
- source
- snippet
- page
- chunk_id (si el snippet proviene de chunk; opcional)
- confidence (0..1)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DocumentSearchResult(BaseModel):
    document_id: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)
    doc_type: str = Field(..., min_length=1)
    created_at: datetime
    source: Optional[str] = None
    snippet: Optional[str] = None
    page: Optional[int] = Field(None, ge=1)
    chunk_id: Optional[str] = Field(None, min_length=1, max_length=40)
    confidence: float = Field(..., ge=0.0, le=1.0)

    model_config = {"extra": "forbid"}


class DocumentSearchResponse(BaseModel):
    items: list[DocumentSearchResult] = Field(default_factory=list)
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=200)
    total: int = Field(0, ge=0)

    model_config = {"extra": "forbid"}

