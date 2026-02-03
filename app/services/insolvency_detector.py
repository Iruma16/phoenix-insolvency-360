"""
Detector de insolvencia según Art. 2 TRLC con ajustes legales.

FASE 1.3: Balance de Situación Automático

IMPORTANTE (ajuste legal):
- Patrimonio neto negativo es INDICADOR, no prueba automática
- Insolvencia ACTUAL requiere hechos de impago exigible
- PN negativo AGRAVA, no determina por sí solo
"""
from decimal import Decimal
from typing import Optional

from app.models.credit import Credit
from app.models.financial_statement import BalanceSheet, IncomeStatement

# Versión de reglas de insolvencia (P0.5 - trazabilidad legal)
INSOLVENCY_RULES_VERSION = "ART2_TRLC_v1.0"


class TRLCInsolvencyDetector:
    """
    Detector de insolvencia según Art. 2 TRLC.

    Criterios ajustados legalmente:
    - Insolvencia ACTUAL → impagos exigibles (determinante)
    - PN negativo → agravante (NO determinante por sí solo)
    """

    def detectar_insolvencia_actual(
        self, balance: BalanceSheet, creditos: list[Credit], impagos_exigibles: list[dict]
    ) -> dict:
        """
        Art. 2.2 TRLC: Incapacidad de cumplir regularmente obligaciones exigibles.

        Criterio jurídico:
        1. Existencia de impagos exigibles (determinante)
        2. PN negativo (agravante, no determinante)
        """
        indicadores = []
        nivel_gravedad = "NINGUNA"

        # 1. IMPAGOS EXIGIBLES (determinante)
        if impagos_exigibles:
            total_impagado = sum(imp.get("amount", Decimal(0)) for imp in impagos_exigibles)
            num_acreedores = len(set(imp.get("creditor_id") for imp in impagos_exigibles))

            indicadores.append(
                {
                    "tipo": "IMPAGOS_EXIGIBLES",
                    "gravedad": "CRÍTICA",
                    "base_legal": "Art. 2.2 TRLC",
                    "descripcion": f"{num_acreedores} acreedores con deudas exigibles impagadas",
                    "importe": float(total_impagado),
                    "es_determinante": True,  # CLAVE
                }
            )
            nivel_gravedad = "CRÍTICA"

        # 2. PATRIMONIO NETO NEGATIVO (agravante)
        if balance.patrimonio_neto and balance.patrimonio_neto < 0:
            indicadores.append(
                {
                    "tipo": "PATRIMONIO_NETO_NEGATIVO",
                    "gravedad": "ALTA" if impagos_exigibles else "MEDIA",
                    "base_legal": "Art. 2.4.1º TRLC",
                    "descripcion": f"Patrimonio neto negativo: {balance.patrimonio_neto}€",
                    "es_determinante": False,  # NO determina por sí solo
                    "nota": (
                        "Causa societaria que AGRAVA insolvencia si hay impagos"
                        if impagos_exigibles
                        else "Indicador preocupante pero sin impagos acreditados"
                    ),
                }
            )

            if not impagos_exigibles:
                nivel_gravedad = "MEDIA"

        # 3. RATIO LIQUIDEZ CRÍTICO (complementario)
        if balance.activo_corriente and balance.pasivo_corriente and balance.pasivo_corriente > 0:
            ratio_liquidez = balance.activo_corriente / balance.pasivo_corriente
            if ratio_liquidez < Decimal("0.5"):
                indicadores.append(
                    {
                        "tipo": "LIQUIDEZ_CRÍTICA",
                        "gravedad": "ALTA" if impagos_exigibles else "MEDIA",
                        "descripcion": f"Ratio liquidez crítico: {ratio_liquidez:.2f}",
                        "es_determinante": False,
                    }
                )

        # CONCLUSIÓN JURÍDICA
        insolvencia_actual = any(ind["es_determinante"] for ind in indicadores)

        return {
            "existe_insolvencia_actual": insolvencia_actual,
            "nivel_gravedad": nivel_gravedad,
            "indicadores": indicadores,
            "razonamiento_juridico": self._generar_razonamiento_actual(
                indicadores, insolvencia_actual
            ),
            "confidence": self._calcular_confidence_actual(indicadores),
        }

    def detectar_insolvencia_inminente(
        self,
        balance: BalanceSheet,
        pyg: Optional[IncomeStatement],
        proyecciones: Optional[dict] = None,
    ) -> dict:
        """
        Art. 2.3 TRLC: Cuando el deudor prevea que NO podrá cumplir
        regular y puntualmente sus obligaciones.
        """
        indicadores = []
        nivel_gravedad = "NINGUNA"

        # 1. Pérdidas recurrentes
        if pyg and pyg.resultado_neto and pyg.resultado_neto < 0:
            indicadores.append(
                {
                    "tipo": "PERDIDAS_RECURRENTES",
                    "gravedad": "ALTA",
                    "descripcion": f"Pérdidas netas: {pyg.resultado_neto}€",
                }
            )
            nivel_gravedad = "ALTA"

        # 2. Endeudamiento crítico
        if balance.total_pasivo and balance.total_activo and balance.total_activo > 0:
            ratio_endeudamiento = balance.total_pasivo / balance.total_activo
            if ratio_endeudamiento > Decimal("0.90"):
                indicadores.append(
                    {
                        "tipo": "ENDEUDAMIENTO_CRÍTICO",
                        "gravedad": "ALTA",
                        "descripcion": f"Endeudamiento crítico: {ratio_endeudamiento:.2%}",
                    }
                )
                nivel_gravedad = "ALTA"

        insolvencia_inminente = len(indicadores) >= 2 or any(
            i["gravedad"] == "ALTA" for i in indicadores
        )

        return {
            "existe_insolvencia_inminente": insolvencia_inminente,
            "nivel_gravedad": nivel_gravedad,
            "indicadores": indicadores,
            "razonamiento_juridico": self._generar_razonamiento_inminente(
                indicadores, insolvencia_inminente
            ),
            "confidence": 0.7 if indicadores else 0.5,
        }

    def _generar_razonamiento_actual(self, indicadores, insolvencia_actual):
        """Genera razonamiento jurídico legible."""
        if insolvencia_actual:
            determinantes = [i for i in indicadores if i.get("es_determinante")]
            return (
                f"Existe insolvencia ACTUAL (Art. 2.2 TRLC) acreditada por: "
                f"{', '.join(d['descripcion'] for d in determinantes)}. "
                + (
                    "El patrimonio neto negativo agrava la situación."
                    if any(i["tipo"] == "PATRIMONIO_NETO_NEGATIVO" for i in indicadores)
                    else ""
                )
            )
        else:
            if any(i["tipo"] == "PATRIMONIO_NETO_NEGATIVO" for i in indicadores):
                return (
                    "No se acredita insolvencia ACTUAL por ausencia de impagos exigibles documentados. "
                    "El patrimonio neto negativo es preocupante pero insuficiente por sí solo."
                )
            return "No se detectan indicios de insolvencia actual."

    def _generar_razonamiento_inminente(self, indicadores, insolvencia_inminente):
        """Genera razonamiento para insolvencia inminente."""
        if insolvencia_inminente:
            return (
                f"Existen indicios de insolvencia INMINENTE (Art. 2.3 TRLC): "
                f"{', '.join(i['descripcion'] for i in indicadores)}"
            )
        return "No se detectan indicios de insolvencia inminente."

    def _calcular_confidence_actual(self, indicadores):
        """Calcula confidence de detección de insolvencia actual."""
        if any(i.get("es_determinante") for i in indicadores):
            return 0.9  # Alta confidence si hay impagos exigibles
        elif any(i["tipo"] == "PATRIMONIO_NETO_NEGATIVO" for i in indicadores):
            return 0.6  # Media confidence si solo hay PN negativo
        return 0.5
