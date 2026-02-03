"""
Calculadora de ratios financieros con validación completa.

FASE 1.3: Balance de Situación Automático
"""
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel

from app.models.financial_statement import BalanceSheet, IncomeStatement


class RatioResult(BaseModel):
    """Resultado de un ratio financiero con validación."""

    value: Optional[Decimal]
    status: Literal["CALCULADO", "NO_CALCULABLE", "NO_APLICABLE"]
    reason: Optional[str] = None
    interpretation: Optional[str] = None


class FinancialRatiosCalculator:
    """
    Calculadora de ratios financieros avanzados con validación.

    Incluye protección contra divisiones ilegales y valores absurdos.
    """

    # ========== RATIOS DE LIQUIDEZ ==========

    def calculate_ratio_liquidez(self, balance: BalanceSheet) -> RatioResult:
        """Ratio de liquidez = Activo Corriente / Pasivo Corriente."""

        if not balance.activo_corriente or not balance.pasivo_corriente:
            return RatioResult(
                value=None,
                status="NO_CALCULABLE",
                reason="Faltan datos: activo_corriente o pasivo_corriente",
            )

        if balance.pasivo_corriente <= 0:
            return RatioResult(
                value=None,
                status="NO_APLICABLE",
                reason="Pasivo corriente es cero o negativo (valor ilegal)",
            )

        ratio = balance.activo_corriente / balance.pasivo_corriente

        if ratio < 1:
            interp = (
                f"CRÍTICO: Activo corriente insuficiente para cubrir pasivo corriente ({ratio:.2f})"
            )
        elif ratio < 1.5:
            interp = f"BAJO: Liquidez ajustada ({ratio:.2f})"
        else:
            interp = f"ADECUADO: Liquidez sana ({ratio:.2f})"

        return RatioResult(value=ratio, status="CALCULADO", interpretation=interp)

    # ========== RATIOS DE SOLVENCIA ==========

    def calculate_ratio_solvencia(self, balance: BalanceSheet) -> RatioResult:
        """Ratio de solvencia = Total Activo / Total Pasivo."""

        if not balance.total_activo or not balance.total_pasivo:
            return RatioResult(
                value=None,
                status="NO_CALCULABLE",
                reason="Faltan datos: total_activo o total_pasivo",
            )

        if balance.total_pasivo <= 0:
            return RatioResult(
                value=None, status="NO_APLICABLE", reason="Total pasivo es cero o negativo"
            )

        ratio = balance.total_activo / balance.total_pasivo

        if ratio < 1:
            interp = f"INSOLVENTE: Activos no cubren pasivos ({ratio:.2f})"
        elif ratio < 1.5:
            interp = f"DÉBIL: Solvencia ajustada ({ratio:.2f})"
        else:
            interp = f"SOLVENTE: Buena cobertura de deudas ({ratio:.2f})"

        return RatioResult(value=ratio, status="CALCULADO", interpretation=interp)

    # ========== RATIOS DE ENDEUDAMIENTO ==========

    def calculate_ratio_endeudamiento(self, balance: BalanceSheet) -> RatioResult:
        """Ratio de endeudamiento = Total Pasivo / Total Activo."""

        if not balance.total_pasivo or not balance.total_activo:
            return RatioResult(
                value=None,
                status="NO_CALCULABLE",
                reason="Faltan datos: total_pasivo o total_activo",
            )

        if balance.total_activo <= 0:
            return RatioResult(
                value=None, status="NO_APLICABLE", reason="Total activo es cero o negativo"
            )

        ratio = balance.total_pasivo / balance.total_activo

        if ratio > 0.9:
            interp = f"CRÍTICO: Endeudamiento muy alto ({ratio:.2%})"
        elif ratio > 0.7:
            interp = f"ALTO: Endeudamiento elevado ({ratio:.2%})"
        else:
            interp = f"ACEPTABLE: Endeudamiento controlado ({ratio:.2%})"

        return RatioResult(value=ratio, status="CALCULADO", interpretation=interp)

    def calculate_ratio_autonomia(self, balance: BalanceSheet) -> RatioResult:
        """Ratio de autonomía = Patrimonio Neto / Total Activo."""

        if not balance.patrimonio_neto or not balance.total_activo:
            return RatioResult(
                value=None,
                status="NO_CALCULABLE",
                reason="Faltan datos: patrimonio_neto o total_activo",
            )

        if balance.total_activo <= 0:
            return RatioResult(
                value=None, status="NO_APLICABLE", reason="Total activo es cero o negativo"
            )

        if balance.patrimonio_neto < 0:
            return RatioResult(
                value=None,
                status="NO_APLICABLE",
                reason="Patrimonio neto negativo (fondos propios negativos)",
            )

        ratio = balance.patrimonio_neto / balance.total_activo

        return RatioResult(
            value=ratio, status="CALCULADO", interpretation=f"Autonomía financiera: {ratio:.2%}"
        )

    # ========== RATIOS DE RENTABILIDAD ==========

    def calculate_roe(self, balance: BalanceSheet, pyg: IncomeStatement) -> RatioResult:
        """ROE = Resultado Neto / Patrimonio Neto."""

        if not pyg.resultado_neto or not balance.patrimonio_neto:
            return RatioResult(
                value=None,
                status="NO_CALCULABLE",
                reason="Faltan datos: resultado_neto o patrimonio_neto",
            )

        if balance.patrimonio_neto <= 0:
            return RatioResult(
                value=None,
                status="NO_APLICABLE",
                reason="Patrimonio neto negativo o cero (ROE no interpretable)",
            )

        roe = (pyg.resultado_neto / balance.patrimonio_neto) * 100

        return RatioResult(
            value=roe,
            status="CALCULADO",
            interpretation=f"{'Rentabilidad' if roe > 0 else 'Pérdida'} del {abs(roe):.2f}% sobre fondos propios",
        )

    def calculate_roa(self, balance: BalanceSheet, pyg: IncomeStatement) -> RatioResult:
        """ROA = Resultado Neto / Total Activo."""

        if not pyg.resultado_neto or not balance.total_activo:
            return RatioResult(
                value=None,
                status="NO_CALCULABLE",
                reason="Faltan datos: resultado_neto o total_activo",
            )

        if balance.total_activo <= 0:
            return RatioResult(
                value=None, status="NO_APLICABLE", reason="Total activo es cero o negativo"
            )

        roa = (pyg.resultado_neto / balance.total_activo) * 100

        return RatioResult(
            value=roa, status="CALCULADO", interpretation=f"Rentabilidad económica: {roa:.2f}%"
        )

    # ========== MÉTODO PRINCIPAL ==========

    def calculate_all_ratios(
        self, balance: BalanceSheet, pyg: Optional[IncomeStatement] = None
    ) -> dict[str, RatioResult]:
        """Calcula todos los ratios disponibles con validación."""

        ratios = {
            # Liquidez
            "liquidez": self.calculate_ratio_liquidez(balance),
            # Solvencia
            "solvencia": self.calculate_ratio_solvencia(balance),
            # Endeudamiento
            "endeudamiento": self.calculate_ratio_endeudamiento(balance),
            "autonomia": self.calculate_ratio_autonomia(balance),
        }

        # Ratios que requieren P&G
        if pyg:
            ratios.update(
                {
                    "roe": self.calculate_roe(balance, pyg),
                    "roa": self.calculate_roa(balance, pyg),
                }
            )

        return ratios
