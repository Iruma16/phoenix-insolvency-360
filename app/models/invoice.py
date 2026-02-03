"""
Modelo de datos para facturas estructuradas.

FASE 2A: INGESTA MULTI-FORMATO
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class InvoiceLineItem(BaseModel):
    """Línea de detalle de una factura."""

    description: str = Field(description="Descripción del concepto")
    quantity: Optional[Decimal] = Field(None, description="Cantidad")
    unit_price: Optional[Decimal] = Field(None, description="Precio unitario")
    amount: Decimal = Field(description="Importe total de la línea")


class StructuredInvoice(BaseModel):
    """
    Factura estructurada con campos clave extraídos.

    Usado para análisis automatizado de saldos, vencimientos, etc.
    """

    # Identificación
    invoice_number: Optional[str] = Field(None, description="Número de factura")
    invoice_type: Optional[str] = Field(None, description="Tipo: factura, abono, rectificativa")

    # Fechas
    issue_date: Optional[date] = Field(None, description="Fecha de emisión")
    due_date: Optional[date] = Field(None, description="Fecha de vencimiento")

    # Partes
    supplier_name: Optional[str] = Field(None, description="Nombre del proveedor/emisor")
    supplier_tax_id: Optional[str] = Field(None, description="NIF/CIF del proveedor")
    customer_name: Optional[str] = Field(None, description="Nombre del cliente/receptor")
    customer_tax_id: Optional[str] = Field(None, description="NIF/CIF del cliente")

    # Importes
    subtotal: Optional[Decimal] = Field(None, description="Base imponible")
    tax_amount: Optional[Decimal] = Field(None, description="Importe IVA")
    tax_rate: Optional[Decimal] = Field(None, description="% IVA aplicado")
    total_amount: Decimal = Field(description="Importe total")

    # Detalles
    line_items: list[InvoiceLineItem] = Field(default_factory=list, description="Líneas de detalle")
    currency: str = Field(default="EUR", description="Moneda")

    # Metadatos de extracción
    extraction_method: str = Field(
        default="unknown", description="Método usado: regex, llm, manual"
    )
    confidence: Optional[float] = Field(None, description="Confianza de extracción (0-1)")

    @field_validator("issue_date", "due_date", mode="before")
    @classmethod
    def parse_date(cls, v):
        """Parsea fechas desde strings."""
        if v is None or isinstance(v, date):
            return v

        if isinstance(v, str):
            # Intentar varios formatos
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    continue

        return v

    def is_overdue(self, reference_date: Optional[date] = None) -> bool:
        """Verifica si la factura está vencida."""
        if not self.due_date:
            return False

        ref = reference_date or date.today()
        return self.due_date < ref

    def days_overdue(self, reference_date: Optional[date] = None) -> int:
        """Calcula días de retraso."""
        if not self.is_overdue(reference_date):
            return 0

        ref = reference_date or date.today()
        return (ref - self.due_date).days
