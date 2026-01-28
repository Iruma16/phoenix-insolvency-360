"""
Enums y modelos para gestión de duplicados (FASE 2A).
"""
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from app.models.document import Document


class DuplicateAction(str, Enum):
    """Acciones disponibles para documentos duplicados."""
    PENDING = "pending"
    KEEP_BOTH = "keep_both"
    MARK_DUPLICATE = "mark_duplicate"
    EXCLUDE_FROM_ANALYSIS = "exclude_from_analysis"


class DuplicateActionRequest(BaseModel):
    """Request body para resolver acción de duplicado."""
    action: DuplicateAction = Field(
        ...,
        description="Acción a tomar sobre el documento duplicado"
    )
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Razón opcional de la decisión (auditoría legal)"
    )
    decided_by: Optional[str] = Field(
        None,
        max_length=100,
        description="Usuario/email que toma la decisión"
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
