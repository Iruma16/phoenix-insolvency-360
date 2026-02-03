"""
Modelo de Crédito para análisis concursal (TRLC).

FASE 1.3: Balance de Situación Automático
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class CreditNature(str, Enum):
    """Naturaleza jurídica del crédito."""

    SALARIO = "salario"
    SEGURIDAD_SOCIAL = "seguridad_social"
    AEAT = "aeat"
    FINANCIERO = "financiero"
    COMERCIAL = "comercial"
    SANCION = "sancion"
    MULTA = "multa"
    INTERESES = "intereses"
    PERSONA_VINCULADA = "persona_vinculada"
    OTRO = "otro"


class CreditClassificationTRLC(str, Enum):
    """Clasificación concursal según TRLC."""

    CONTRA_LA_MASA = "contra_la_masa"
    PRIVILEGIADO_ESPECIAL = "privilegiado_especial"
    PRIVILEGIADO_GENERAL = "privilegiado_general"
    ORDINARIO = "ordinario"
    SUBORDINADO = "subordinado"


class Credit(BaseModel):
    """
    Crédito individual según Derecho Concursal.

    IMPORTANTE: El objeto del análisis concursal es el CRÉDITO, no el acreedor.
    Un mismo acreedor puede tener múltiples créditos con diferentes clasificaciones.
    """

    credit_id: str = Field(..., description="UUID del crédito")
    creditor_id: str = Field(..., description="Identificador del acreedor")
    creditor_name: str

    # Importe
    principal_amount: Decimal = Field(..., ge=0)
    interest_amount: Decimal = Field(default=Decimal(0), ge=0)
    total_amount: Decimal

    # Naturaleza jurídica
    nature: CreditNature

    # Garantías
    secured: bool = Field(default=False)
    guarantee_type: Optional[Literal["real", "personal", "ninguna"]] = None
    guarantee_value: Optional[Decimal] = None

    # Fechas
    devengo_date: Optional[date] = Field(None, description="Fecha de devengo del crédito")
    due_date: Optional[date] = Field(None, description="Fecha de vencimiento")

    # Origen
    source_document_id: Optional[str] = None
    source_description: Optional[str] = None

    # Clasificación concursal (calculada)
    trlc_classification: Optional[CreditClassificationTRLC] = None
    classification_reasoning: Optional[str] = Field(
        None, description="Razonamiento jurídico de la clasificación (auditable)"
    )

    # Exclusiones explícitas (auditoría legal)
    excluded_from_categories: dict[str, str] = Field(
        default_factory=dict, description="Categorías de las que fue excluido y por qué"
    )

    # Metadata
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    extraction_method: str = Field(default="manual")

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_dates(self) -> Credit:
        """Valida coherencia de fechas (P0.3)."""
        if self.due_date and self.devengo_date:
            if self.due_date < self.devengo_date:
                raise ValueError(
                    f"Fecha de vencimiento ({self.due_date}) no puede ser anterior "
                    f"a fecha de devengo ({self.devengo_date})"
                )
        return self
