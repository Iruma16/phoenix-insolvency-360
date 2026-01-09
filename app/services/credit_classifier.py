"""
Clasificador de créditos según TRLC con jerarquía excluyente.

FASE 1.3: Balance de Situación Automático
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from app.models.credit import Credit, CreditNature, CreditClassificationTRLC


# Constantes legales (actualizar anualmente)
SMI_2025 = Decimal("1134")  # Salario Mínimo Interprofesional 2025

# Versión de reglas TRLC (P0.5 - trazabilidad legal)
TRLC_RULESET_VERSION = "TRLC_2020_v1.0"


class TRLCCreditClassifier:
    """
    Clasificador de créditos según jerarquía estricta TRLC.
    
    Orden jurídico (excluyente):
    1. Contra la masa (Art. 249 TRLC)
    2. Privilegiado especial (Art. 270 TRLC)
    3. Subordinado (Art. 456 TRLC) - tiene prioridad sobre general
    4. Privilegiado general (Art. 271 TRLC)
    5. Ordinario (Art. 289 TRLC) - fallback
    
    IMPORTANTE: La clasificación es excluyente y se registra el motivo
    de exclusión de categorías superiores (auditable).
    """
    
    def __init__(self, concurso_date: Optional[date] = None):
        """
        Args:
            concurso_date: Fecha de declaración de concurso (si existe)
        """
        self.concurso_date = concurso_date
    
    def classify_credit(self, credit: Credit) -> Credit:
        """
        Clasifica un crédito según jerarquía TRLC.
        
        Registra explícitamente por qué NO entra en cada categoría superior.
        """
        exclusions = {}
        
        # 1. ¿Es contra la masa? (Art. 249 TRLC)
        if self.concurso_date:
            result, reason = self._check_contra_la_masa(credit)
            if result:
                credit.trlc_classification = CreditClassificationTRLC.CONTRA_LA_MASA
                credit.classification_reasoning = f"Art. 249 TRLC: {reason}"
                return credit
            exclusions["contra_la_masa"] = reason
        
        # 2. ¿Es privilegiado especial? (Art. 270 TRLC)
        result, reason = self._check_privilegiado_especial(credit)
        if result:
            credit.trlc_classification = CreditClassificationTRLC.PRIVILEGIADO_ESPECIAL
            credit.classification_reasoning = f"Art. 270 TRLC: {reason}"
            credit.excluded_from_categories = exclusions
            return credit
        exclusions["privilegiado_especial"] = reason
        
        # 3. ¿Es subordinado? (Art. 456 TRLC - tiene prioridad sobre general)
        result, reason = self._check_subordinado(credit)
        if result:
            credit.trlc_classification = CreditClassificationTRLC.SUBORDINADO
            credit.classification_reasoning = f"Art. 456 TRLC: {reason}"
            credit.excluded_from_categories = exclusions
            return credit
        exclusions["subordinado"] = reason
        
        # 4. ¿Es privilegiado general? (Art. 271 TRLC)
        result, reason = self._check_privilegiado_general(credit)
        if result:
            credit.trlc_classification = CreditClassificationTRLC.PRIVILEGIADO_GENERAL
            credit.classification_reasoning = f"Art. 271 TRLC: {reason}"
            credit.excluded_from_categories = exclusions
            return credit
        exclusions["privilegiado_general"] = reason
        
        # 5. Por defecto: ordinario (Art. 289 TRLC)
        credit.trlc_classification = CreditClassificationTRLC.ORDINARIO
        credit.classification_reasoning = "Art. 289 TRLC: Crédito ordinario (no cumple requisitos de otras categorías)"
        credit.excluded_from_categories = exclusions
        return credit
    
    def _check_contra_la_masa(self, credit: Credit) -> tuple[bool, str]:
        """Art. 249 TRLC - Créditos contra la masa."""
        
        if not self.concurso_date:
            return False, "Fecha de concurso no disponible"
        
        # 249.1º - Salarios posteriores al concurso
        if credit.nature == CreditNature.SALARIO:
            if credit.devengo_date and credit.devengo_date >= self.concurso_date:
                return True, "Salario devengado tras declaración de concurso"
            return False, "Salario devengado antes del concurso"
        
        # 249.2º - Créditos alimenticios durante concurso
        # 249.3º - Gastos de conservación de la masa
        # (Por ahora solo implementamos salarios, el resto requiere más contexto)
        
        return False, "No cumple requisitos Art. 249 TRLC"
    
    def _check_privilegiado_especial(self, credit: Credit) -> tuple[bool, str]:
        """Art. 270 TRLC - Privilegio especial."""
        
        # 270.1º - Créditos garantizados con prenda o hipoteca
        if credit.secured and credit.guarantee_type == "real":
            return True, f"Garantía real sobre bien específico (valor: {credit.guarantee_value}€)"
        
        # 270.2º - Retenciones tributarias y SS
        if credit.nature in [CreditNature.AEAT, CreditNature.SEGURIDAD_SOCIAL]:
            if credit.source_description and "retencion" in credit.source_description.lower():
                return True, "Retenciones tributarias/SS (Art. 270.2 TRLC)"
            return False, "No es retención, sino deuda tributaria directa"
        
        # 270.3º - Créditos de trabajadores (últimos 30 días, máx 2xSMI)
        if credit.nature == CreditNature.SALARIO:
            max_privilegiado = SMI_2025 * 2 * 12 / 365 * 30  # 2xSMI prorrateado 30 días
            
            if credit.principal_amount <= max_privilegiado:
                return True, f"Salarios últimos 30 días dentro de límite (máx {max_privilegiado:.2f}€)"
            return False, f"Salarios exceden límite 2xSMI ({max_privilegiado:.2f}€), resto es ordinario"
        
        return False, "No cumple requisitos Art. 270 TRLC"
    
    def _check_subordinado(self, credit: Credit) -> tuple[bool, str]:
        """Art. 456 TRLC - Subordinación."""
        
        # 456.1º - Créditos por intereses
        if credit.nature == CreditNature.INTERESES:
            return True, "Créditos por intereses (Art. 456.1 TRLC)"
        
        # 456.2º - Multas y sanciones
        if credit.nature in [CreditNature.SANCION, CreditNature.MULTA]:
            return True, "Multas y sanciones (Art. 456.2 TRLC)"
        
        # 456.3º - Créditos de personas vinculadas
        if credit.nature == CreditNature.PERSONA_VINCULADA:
            return True, "Persona especialmente relacionada (Art. 456.3 TRLC)"
        
        return False, "No cumple requisitos Art. 456 TRLC"
    
    def _check_privilegiado_general(self, credit: Credit) -> tuple[bool, str]:
        """Art. 271 TRLC - Privilegio general."""
        
        # 271.1º - 50% créditos AEAT y SS (no retenciones)
        if credit.nature in [CreditNature.AEAT, CreditNature.SEGURIDAD_SOCIAL]:
            if not credit.source_description or "retencion" not in credit.source_description.lower():
                privileged_amount = credit.principal_amount * Decimal("0.5")
                return True, f"50% crédito tributario/SS privilegiado ({privileged_amount:.2f}€), resto ordinario"
        
        # 271.2º - Créditos de trabajadores (resto no cubierto por especial)
        if credit.nature == CreditNature.SALARIO:
            return True, "Crédito laboral no cubierto por privilegio especial"
        
        return False, "No cumple requisitos Art. 271 TRLC"
    
    def classify_credits_batch(self, credits: list[Credit]) -> list[Credit]:
        """Clasifica una lista de créditos."""
        return [self.classify_credit(credit) for credit in credits]
