"""
Contrato de salida completo del Balance de Situación Concursal.

FASE 1.3: Balance de Situación Automático
"""
from datetime import datetime
from typing import Optional
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.financial_statement import BalanceSheet, IncomeStatement
from app.models.credit import Credit, CreditClassificationTRLC
from app.models.legal_opinion import LegalOpinion, DISCLAIMER_BALANCE_CONCURSAL
from app.services.financial_ratios import RatioResult


class ClassificationSummary(BaseModel):
    """Resumen de clasificación de créditos."""
    count: int
    total: Decimal


class BalanceConcursalOutput(BaseModel):
    """
    Contrato de salida completo del Balance de Situación Concursal.
    
    Incluye todas las correcciones P0/P1/Legal.
    """
    
    # Metadata
    balance_id: str
    case_id: str
    fecha_analisis: datetime
    version: int = Field(default=1)
    ruleset_version: str = Field(
        ...,
        description="Versión de reglas TRLC + insolvencia aplicadas (trazabilidad legal P0.5)"
    )
    
    # Disclaimer legal
    advertencia_legal: str = DISCLAIMER_BALANCE_CONCURSAL
    
    # Balance estructurado
    balance: BalanceSheet
    pyg: Optional[IncomeStatement] = None
    
    # Créditos clasificados (NO acreedores)
    creditos: list[Credit]
    resumen_clasificacion: dict[str, ClassificationSummary]
    
    # Ratios con validación
    ratios: dict[str, RatioResult]
    
    # Insolvencia (ajustada P0.3)
    analisis_insolvencia: dict
    
    # Dictamen jurídico
    dictamen: LegalOpinion
    
    # Confidence granular
    confidence: dict[str, float] = Field(
        ...,
        description="Confidence separado por tipo de análisis",
        json_schema_extra={
            "example": {
                "extraction": 0.85,
                "classification": 0.90,
                "ratios": 0.95,
                "insolvency": 0.80,
            }
        }
    )
    
    model_config = {"extra": "forbid"}
