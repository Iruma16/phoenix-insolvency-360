"""
Esquemas de datos para el Agente Legal.
"""

from pydantic import BaseModel, Field


class LegalRisk(BaseModel):
    """
    Representa un riesgo legal identificado.
    """

    risk_type: str = Field(
        ...,
        description="Tipo de riesgo: omision, falta_prueba, calificacion_culpable, vicio_formal, prescripcion, otro",
    )
    description: str = Field(..., description="Descripción detallada del riesgo legal")
    severity: str = Field(..., description="Severidad: critica, alta, media, baja, indeterminado")
    legal_articles: list[str] = Field(
        default_factory=list, description="Artículos de Ley Concursal que fundamentan el riesgo"
    )
    jurisprudence: list[str] = Field(
        default_factory=list, description="Referencias jurisprudenciales relevantes"
    )
    evidence_status: str = Field(
        ..., description="Estado de la evidencia: suficiente, insuficiente, falta"
    )
    recommendation: str = Field(..., description="Recomendación legal específica")


class LegalAgentResult(BaseModel):
    """
    Resultado del análisis del Agente Legal.
    """

    case_id: str = Field(..., description="ID del caso analizado")
    legal_risks: list[LegalRisk] = Field(
        default_factory=list, description="Lista de riesgos legales identificados"
    )
    legal_conclusion: str = Field(..., description="Conclusión legal general del caso")
    confidence_level: str = Field(
        ..., description="Nivel de confianza: alta, media, baja, indeterminado"
    )
    missing_data: list[str] = Field(
        default_factory=list,
        description="Lista de datos faltantes que impiden un análisis completo",
    )
    legal_basis: list[str] = Field(
        default_factory=list, description="Lista de artículos de Ley Concursal citados"
    )
