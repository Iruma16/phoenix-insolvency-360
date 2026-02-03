"""
Enums y modelos para gestión de duplicados (FASE 2A).
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.document import Document


class DuplicateAction(str, Enum):
    """Acciones disponibles para documentos duplicados."""

    PENDING = "pending"
    KEEP_BOTH = "keep_both"
    MARK_DUPLICATE = "mark_duplicate"
    EXCLUDE_FROM_ANALYSIS = "exclude_from_analysis"


class DuplicateActionRequest(BaseModel):
    """Request body para resolver acción de duplicado."""

    action: DuplicateAction = Field(..., description="Acción a tomar sobre el documento duplicado")
    reason: Optional[str] = Field(
        None, max_length=500, description="Razón opcional de la decisión (auditoría legal)"
    )
    decided_by: Optional[str] = Field(
        None, max_length=100, description="Usuario/email que toma la decisión"
    )


class DuplicateDecisionResponse(BaseModel):
    """
    Response tras resolver duplicado (PUNTO 2 - CORRECCIÓN).

    CRÍTICO: Devuelve estado del PAR completo, no solo del documento.
    Incluye decision_version para siguiente operación.
    """

    # Estado del par
    pair_id: str = Field(..., description="ID único del par")
    decision: str = Field(..., description="keep_both/mark_duplicate/exclude_from_analysis")
    decision_version: int = Field(
        ..., description="Versión actual (CRÍTICO para próxima operación)"
    )
    decided_at: datetime
    decided_by: str
    decision_reason: str

    # Documentos afectados
    doc_a_id: str
    doc_b_id: str
    affected_documents: list[str] = Field(
        ..., description="IDs de docs afectados por esta decisión"
    )

    # Metadata
    similarity: float
    duplicate_type: str

    # Opcional: información adicional del documento consultado (legacy compatibility)
    document_summary: Optional[dict[str, Any]] = Field(
        None, description="DocumentSummary del documento consultado si se necesita"
    )


class DuplicatePairSummary(BaseModel):
    """
    Resumen BLINDADO de par de documentos duplicados.

    CRÍTICO: Incluye todo lo necesario para decisiones legales defensibles:
    - Contexto completo del preview
    - Metadata de similitud explicable
    - Versión para lock optimista
    - Warnings de riesgo
    """

    # Identidad del par
    pair_id: str = Field(..., description="ID único e inmutable del par")

    # Original (doc_a)
    original_id: str
    original_filename: str
    original_date: datetime
    original_preview: str
    original_preview_offset: int = Field(0, description="Offset en chars del preview")
    original_preview_location: str = Field("start", description="start/middle/end")
    original_total_length: int = Field(0, description="Longitud total del texto")

    # Duplicado (doc_b)
    duplicate_id: str
    duplicate_filename: str
    duplicate_date: datetime
    duplicate_preview: str
    duplicate_preview_offset: int = Field(0, description="Offset en chars del preview")
    duplicate_preview_location: str = Field("start", description="start/middle/end")
    duplicate_total_length: int = Field(0, description="Longitud total del texto")

    # Metadata de similitud (EXPLICABLE)
    similarity: float = Field(..., ge=0.0, le=1.0, description="Score 0-1")
    similarity_method: Optional[str] = Field(None, description="cosine/hash/shingling")
    similarity_model: Optional[str] = Field(None, description="text-embedding-3-small/etc")
    duplicate_type: str = Field(..., description="'exact' o 'semantic'")

    # Warnings
    preview_warning: Optional[str] = Field(
        None, description="Warning si preview no es representativo"
    )

    # Decisión
    action: Optional[str] = Field(
        None, description="keep_both/mark_duplicate/exclude_from_analysis"
    )
    action_reason: Optional[str] = None
    action_by: Optional[str] = None
    action_at: Optional[datetime] = None

    # LOCK OPTIMISTA (CRÍTICO)
    expected_version: int = Field(
        0, description="Versión actual del par para control de concurrencia"
    )


def should_include_in_analysis(document: Document) -> bool:
    """
    Determina si un documento debe incluirse en análisis legal.

    Política:
    - exclude_from_analysis: NO incluir
    - mark_duplicate: NO incluir (redundante, mantener para auditoría)
    - keep_both: SÍ incluir
    - pending o None: SÍ incluir (por defecto)

    Args:
        document: Documento a evaluar

    Returns:
        True si debe incluirse en análisis
    """
    if not document.duplicate_action:
        return True

    action = document.duplicate_action

    # Excluir explícitamente y duplicados marcados
    if action in ["exclude_from_analysis", "mark_duplicate"]:
        return False

    # Incluir keep_both y pending
    return True
