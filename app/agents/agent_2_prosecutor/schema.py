"""
Esquemas de datos para el agente prosecutor.
JSON de salida (acusaciones).
"""
from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# ============================
# ENUMS / TIPOS CONTROLADOS
# ============================

RiskLevel = Literal["bajo", "medio", "alto", "critico"]

LegalGround = Literal[
    "retraso_concurso",
    "alzamiento_bienes",
    "doble_contabilidad",
    "simulacion_patrimonial",
    "pagos_preferentes",
    "operaciones_vinculadas",
    "falta_contabilidad",
    "incumplimiento_deber_colaboracion",
]


# ============================
# PRUEBAS / EVIDENCIAS
# ============================

class Evidence(BaseModel):
    document_id: str = Field(..., description="ID del documento donde se detecta el indicio")
    document_name: Optional[str] = Field(None, description="Nombre legible del documento")
    chunk_index: Optional[int] = Field(None, description="Fragmento concreto del documento")
    excerpt: Optional[str] = Field(
        None,
        description="Texto exacto que sustenta la acusación"
    )
    date: Optional[str] = Field(
        None,
        description="Fecha relevante del hecho (YYYY-MM-DD si es posible)"
    )


# ============================
# ACUSACIÓN INDIVIDUAL
# ============================

class LegalAccusation(BaseModel):
    accusation_id: str = Field(..., description="Identificador único de la acusación")
    legal_ground: LegalGround = Field(
        ...,
        description="Base legal de posible calificación culpable"
    )
    risk_level: RiskLevel = Field(
        ...,
        description="Nivel de riesgo estimado"
    )
    title: str = Field(
        ...,
        description="Resumen corto y contundente de la acusación"
    )
    description: str = Field(
        ...,
        description="Explicación clara del riesgo detectado"
    )
    reasoning: str = Field(
        ...,
        description="Razonamiento lógico-temporal que conecta los hechos"
    )
    evidences: List[Evidence] = Field(
        default_factory=list,
        description="Pruebas documentales que sustentan la acusación"
    )
    estimated_probability: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description="Probabilidad estimada de que el juez considere esta causa"
    )
    legal_articles: List[str] = Field(
        default_factory=list,
        description="Artículos de ley citados (ej: 'Art. 165 LC')"
    )
    jurisprudence: List[str] = Field(
        default_factory=list,
        description="Resúmenes cortos de jurisprudencia relevante"
    )


# ============================
# RESULTADO GLOBAL DEL AGENTE
# ============================

class ProsecutorResult(BaseModel):
    case_id: str = Field(..., description="Identificador del caso")
    
    overall_risk_level: RiskLevel = Field(
        ...,
        description="Nivel global de riesgo de calificación culpable"
    )

    accusations: List[LegalAccusation] = Field(
        default_factory=list,
        description="Listado completo de acusaciones detectadas"
    )

    critical_findings_count: int = Field(
        ...,
        description="Número de hallazgos críticos"
    )

    summary_for_lawyer: str = Field(
        ...,
        description="Resumen ejecutivo para el abogado (tono alerta)"
    )

    blocking_recommendation: bool = Field(
        ...,
        description=(
            "True si NO se recomienda presentar el concurso "
            "sin medidas defensivas previas"
        )
    )

