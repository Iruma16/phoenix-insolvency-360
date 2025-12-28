"""
Modelos de datos para el motor de reglas.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class Trigger(BaseModel):
    """Trigger de activación de una regla."""
    condition: str = Field(..., description="Expresión lógica evaluable")
    variables_required: List[str] = Field(default_factory=list, description="Variables necesarias para evaluar")


class EvidenceRequired(BaseModel):
    """Evidencia requerida para mitigar el riesgo."""
    document_types: List[str] = Field(default_factory=list)
    descriptions: List[str] = Field(default_factory=list)


class SeverityLogic(BaseModel):
    """Lógica de escalado de severidad."""
    low: Optional[str] = None
    medium: Optional[str] = None
    high: Optional[str] = None
    critical: Optional[str] = None


class ConfidenceLogic(BaseModel):
    """Lógica de cálculo de confianza."""
    high: Optional[str] = None
    medium: Optional[str] = None
    low: Optional[str] = None
    indeterminate: Optional[str] = None


class Outputs(BaseModel):
    """Templates de salida de la regla."""
    description_template: str
    recommendation_template: str
    missing_data_template: Optional[str] = None


class Rule(BaseModel):
    """Regla del motor de reglas."""
    rule_id: str
    risk_type: str
    article_refs: List[str]
    trigger: Trigger
    evidence_required: EvidenceRequired
    severity_logic: SeverityLogic
    confidence_logic: ConfidenceLogic
    outputs: Outputs


class Rulebook(BaseModel):
    """Rulebook completo."""
    metadata: Dict[str, Any]
    rules: List[Rule]

