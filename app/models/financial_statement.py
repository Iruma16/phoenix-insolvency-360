"""
Modelo de datos para estados financieros estructurados.

FASE 2A: INGESTA MULTI-FORMATO
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class BalanceSheet(BaseModel):
    """Balance de Situación estructurado."""

    # Activo
    activo_corriente: Optional[Decimal] = None
    activo_no_corriente: Optional[Decimal] = None
    total_activo: Optional[Decimal] = None

    # Pasivo
    pasivo_corriente: Optional[Decimal] = None
    pasivo_no_corriente: Optional[Decimal] = None
    total_pasivo: Optional[Decimal] = None

    # Patrimonio Neto
    patrimonio_neto: Optional[Decimal] = None
    capital_social: Optional[Decimal] = None
    reservas: Optional[Decimal] = None
    resultado_ejercicio: Optional[Decimal] = None

    # Metadata
    fecha_cierre: Optional[date] = None
    ejercicio: Optional[str] = None

    def calcular_ratio_liquidez(self) -> Optional[Decimal]:
        """Ratio de liquidez = Activo Corriente / Pasivo Corriente."""
        if self.activo_corriente and self.pasivo_corriente and self.pasivo_corriente > 0:
            return self.activo_corriente / self.pasivo_corriente
        return None

    def calcular_ratio_endeudamiento(self) -> Optional[Decimal]:
        """Ratio de endeudamiento = Total Pasivo / Total Activo."""
        if self.total_pasivo and self.total_activo and self.total_activo > 0:
            return self.total_pasivo / self.total_activo
        return None

    def tiene_fondos_propios_negativos(self) -> bool:
        """Detecta si patrimonio neto es negativo (causa de insolvencia)."""
        return self.patrimonio_neto is not None and self.patrimonio_neto < 0


class IncomeStatement(BaseModel):
    """Cuenta de Pérdidas y Ganancias estructurada."""

    # Ingresos
    ingresos_explotacion: Optional[Decimal] = None
    otros_ingresos: Optional[Decimal] = None

    # Gastos
    gastos_explotacion: Optional[Decimal] = None
    gastos_personal: Optional[Decimal] = None
    amortizaciones: Optional[Decimal] = None
    gastos_financieros: Optional[Decimal] = None

    # Resultados
    resultado_explotacion: Optional[Decimal] = None
    resultado_financiero: Optional[Decimal] = None
    resultado_antes_impuestos: Optional[Decimal] = None
    resultado_neto: Optional[Decimal] = None

    # Metadata
    ejercicio: Optional[str] = None

    def tiene_perdidas(self) -> bool:
        """Detecta si hay pérdidas netas."""
        return self.resultado_neto is not None and self.resultado_neto < 0


class CreditorsList(BaseModel):
    """Listado de acreedores estructurado."""

    acreedores: list[dict[str, Any]] = Field(default_factory=list)
    total_deuda: Optional[Decimal] = None

    def contar_acreedores(self) -> int:
        """Cuenta número de acreedores."""
        return len(self.acreedores)


class FinancialStatements(BaseModel):
    """Conjunto de estados financieros de una empresa."""

    statement_type: Literal["BALANCE", "PYGL", "ACREEDORES", "MAYOR", "OTRO"]

    balance: Optional[BalanceSheet] = None
    income_statement: Optional[IncomeStatement] = None
    creditors_list: Optional[CreditorsList] = None

    # Metadata de extracción
    extraction_method: str = Field(default="unknown")
    confidence: float = Field(default=0.5)

    def detectar_insolvencia(self) -> list[str]:
        """Detecta indicadores de insolvencia."""
        indicadores = []

        if self.balance:
            if self.balance.tiene_fondos_propios_negativos():
                indicadores.append("Patrimonio neto negativo")

            ratio_liquidez = self.balance.calcular_ratio_liquidez()
            if ratio_liquidez and ratio_liquidez < 1:
                indicadores.append(f"Ratio de liquidez bajo: {ratio_liquidez:.2f}")

            ratio_endeudamiento = self.balance.calcular_ratio_endeudamiento()
            if ratio_endeudamiento and ratio_endeudamiento > 0.8:
                indicadores.append(f"Alto endeudamiento: {ratio_endeudamiento:.2%}")

        if self.income_statement:
            if self.income_statement.tiene_perdidas():
                indicadores.append(f"Pérdidas netas: {self.income_statement.resultado_neto}€")

        return indicadores
