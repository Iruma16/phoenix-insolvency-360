"""
Modelo de datos para entidades legales extraídas.

FASE 2A: INGESTA MULTI-FORMATO
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class LegalEntity(BaseModel):
    """
    Entidad legal extraída de un documento.

    Tipos de entidades:
    - AMOUNT: Cuantía monetaria (reclamación, deuda, embargo)
    - DATE: Fecha relevante (notificación, vencimiento, plazo)
    - CREDITOR: Acreedor/demandante
    - DEBTOR: Deudor/demandado
    - COURT: Juzgado/tribunal
    - PROCEDURE: Procedimiento judicial
    - DEADLINE: Plazo de respuesta/actuación
    """

    entity_type: Literal["AMOUNT", "DATE", "CREDITOR", "DEBTOR", "COURT", "PROCEDURE", "DEADLINE"]
    value: str = Field(description="Valor extraído (texto original)")
    normalized_value: Optional[str] = Field(None, description="Valor normalizado")

    # Para AMOUNT
    amount: Optional[Decimal] = Field(None, description="Cuantía monetaria")
    currency: Optional[str] = Field(None, description="Moneda")

    # Para DATE/DEADLINE
    date_value: Optional[date] = Field(None, description="Fecha normalizada")

    # Contexto
    context: Optional[str] = Field(None, description="Contexto donde aparece (frase completa)")
    confidence: float = Field(default=0.5, description="Confianza de extracción (0-1)")
    extraction_method: str = Field(default="unknown", description="Método: regex, llm, manual")

    # Posición en documento
    start_char: Optional[int] = Field(None, description="Offset inicio en texto")
    end_char: Optional[int] = Field(None, description="Offset fin en texto")

    @field_validator("date_value", mode="before")
    @classmethod
    def parse_date(cls, v):
        """Parsea fechas desde strings."""
        if v is None or isinstance(v, date):
            return v

        if isinstance(v, str):
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    continue

        return v


class LegalDocument(BaseModel):
    """
    Documento legal con entidades extraídas.
    """

    document_type: Literal["EMBARGO", "DENUNCIA", "RESOLUCION", "NOTIFICACION", "OTRO"]
    entities: list[LegalEntity] = Field(default_factory=list)

    # Resumen automático
    summary: Optional[str] = Field(None, description="Resumen generado automáticamente")

    def get_amounts(self) -> list[LegalEntity]:
        """Retorna todas las cuantías encontradas."""
        return [e for e in self.entities if e.entity_type == "AMOUNT"]

    def get_dates(self) -> list[LegalEntity]:
        """Retorna todas las fechas encontradas."""
        return [e for e in self.entities if e.entity_type == "DATE"]

    def get_deadlines(self) -> list[LegalEntity]:
        """Retorna todos los plazos encontrados."""
        return [e for e in self.entities if e.entity_type == "DEADLINE"]

    def get_total_amount(self) -> Optional[Decimal]:
        """Calcula cuantía total reclamada."""
        amounts = [e.amount for e in self.get_amounts() if e.amount]
        return sum(amounts, Decimal("0")) if amounts else None
