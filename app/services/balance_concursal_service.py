"""
Servicio principal de Balance de Situación Concursal.

FASE 1.3: Balance de Situación Automático

Orquesta todo el flujo: extracción → clasificación → ratios → insolvencia → dictamen
"""
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.financial_statement import BalanceSheet, IncomeStatement
from app.models.credit import Credit, CreditNature, CreditClassificationTRLC
from app.models.legal_opinion import LegalOpinion, OpinionConclusion
from app.models.balance_concursal_output import BalanceConcursalOutput, ClassificationSummary
from app.models.balance_situacion import BalanceSituacion, CreditoDB
from app.services.credit_classifier import TRLCCreditClassifier, TRLC_RULESET_VERSION
from app.services.financial_ratios import FinancialRatiosCalculator
from app.services.insolvency_detector import TRLCInsolvencyDetector, INSOLVENCY_RULES_VERSION


class BalanceConcursalService:
    """
    Servicio principal para análisis de Balance de Situación Concursal.
    
    Flujo completo:
    1. Extracción de datos contables
    2. Clasificación de créditos según TRLC
    3. Cálculo de ratios financieros
    4. Detección de insolvencia (actual/inminente)
    5. Generación de dictamen jurídico
    """
    
    def __init__(self, concurso_date: Optional[date] = None):
        self.concurso_date = concurso_date
        self.credit_classifier = TRLCCreditClassifier(concurso_date)
        self.ratios_calculator = FinancialRatiosCalculator()
        self.insolvency_detector = TRLCInsolvencyDetector()
    
    def analyze_balance_concursal(
        self,
        case_id: str,
        balance: BalanceSheet,
        creditos: list[Credit],
        pyg: Optional[IncomeStatement] = None,
        impagos_exigibles: Optional[list[dict]] = None
    ) -> BalanceConcursalOutput:
        """
        Análisis completo de Balance de Situación Concursal.
        
        Args:
            case_id: ID del caso
            balance: Balance de situación estructurado
            creditos: Lista de créditos a clasificar
            pyg: Cuenta de Pérdidas y Ganancias (opcional)
            impagos_exigibles: Lista de impagos exigibles (opcional)
            
        Returns:
            BalanceConcursalOutput completo
        """
        balance_id = str(uuid.uuid4())
        
        # 1. Clasificar créditos según TRLC
        creditos_clasificados = self.credit_classifier.classify_credits_batch(creditos)
        
        # 2. Resumen de clasificación
        resumen = self._generar_resumen_clasificacion(creditos_clasificados)
        
        # 3. Calcular ratios financieros
        ratios = self.ratios_calculator.calculate_all_ratios(balance, pyg)
        
        # 4. Detectar insolvencia
        analisis_insolvencia_actual = self.insolvency_detector.detectar_insolvencia_actual(
            balance,
            creditos_clasificados,
            impagos_exigibles or []
        )
        
        analisis_insolvencia_inminente = self.insolvency_detector.detectar_insolvencia_inminente(
            balance,
            pyg
        )
        
        analisis_insolvencia = {
            "actual": analisis_insolvencia_actual,
            "inminente": analisis_insolvencia_inminente,
        }
        
        # 5. Generar dictamen jurídico
        dictamen = self._generar_dictamen(
            analisis_insolvencia_actual,
            analisis_insolvencia_inminente,
            balance,
            resumen
        )
        
        # 6. Calcular confidence granular
        confidence = {
            "extraction": 0.85,  # TODO: calcular desde parsing
            "classification": self._calcular_confidence_clasificacion(creditos_clasificados),
            "ratios": self._calcular_confidence_ratios(ratios),
            "insolvency": analisis_insolvencia_actual["confidence"],
        }
        
        return BalanceConcursalOutput(
            balance_id=balance_id,
            case_id=case_id,
            fecha_analisis=datetime.utcnow(),
            ruleset_version=f"{TRLC_RULESET_VERSION}+{INSOLVENCY_RULES_VERSION}",
            balance=balance,
            pyg=pyg,
            creditos=creditos_clasificados,
            resumen_clasificacion=resumen,
            ratios=ratios,
            analisis_insolvencia=analisis_insolvencia,
            dictamen=dictamen,
            confidence=confidence,
        )
    
    def _generar_resumen_clasificacion(self, creditos: list[Credit]) -> dict[str, ClassificationSummary]:
        """Genera resumen de clasificación de créditos."""
        resumen = {}
        
        for clasificacion in CreditClassificationTRLC:
            creditos_categoria = [c for c in creditos if c.trlc_classification == clasificacion]
            resumen[clasificacion.value] = ClassificationSummary(
                count=len(creditos_categoria),
                total=sum(c.total_amount for c in creditos_categoria)
            )
        
        return resumen
    
    def _generar_dictamen(
        self,
        analisis_actual: dict,
        analisis_inminente: dict,
        balance: BalanceSheet,
        resumen: dict
    ) -> LegalOpinion:
        """Genera dictamen jurídico legible."""
        
        # Determinar conclusión
        if analisis_actual["existe_insolvencia_actual"]:
            conclusion = OpinionConclusion.INSOLVENCIA_ACTUAL_ACREDITADA
            confianza = "ALTA"
            
            fundamentos = [
                analisis_actual["razonamiento_juridico"],
            ]
            
            # P0.11: Referencias legales explícitas
            base_legal = ["Art. 2.2 TRLC", "Art. 5 TRLC"]
            
            # Agregar info de créditos
            total_contra_masa = resumen.get("contra_la_masa", ClassificationSummary(count=0, total=Decimal(0))).total
            total_privilegiados = (
                resumen.get("privilegiado_especial", ClassificationSummary(count=0, total=Decimal(0))).total +
                resumen.get("privilegiado_general", ClassificationSummary(count=0, total=Decimal(0))).total
            )
            
            fundamentos.append(
                f"Clasificación de créditos: {total_contra_masa}€ contra la masa, "
                f"{total_privilegiados}€ privilegiados"
            )
            
            if total_contra_masa > 0:
                base_legal.append("Art. 249 TRLC")
            if total_privilegiados > 0:
                base_legal.extend(["Art. 270 TRLC", "Art. 271 TRLC"])
            
            recomendacion = (
                "Valorar solicitud INMEDIATA de concurso voluntario (Art. 5 TRLC). "
                "Existe obligación legal de solicitar concurso en plazo de 2 meses desde "
                "conocimiento del estado de insolvencia. Contactar con abogado concursalista."
            )
            
        elif analisis_inminente["existe_insolvencia_inminente"]:
            conclusion = OpinionConclusion.INSOLVENCIA_INMINENTE
            confianza = "MEDIA"
            
            fundamentos = [analisis_inminente["razonamiento_juridico"]]
            
            # P0.11: Referencias legales explícitas
            base_legal = ["Art. 2.3 TRLC", "Art. 5 bis TRLC"]
            
            recomendacion = (
                "Situación financiera preocupante con indicios de insolvencia inminente. "
                "Se recomienda: 1) Plan de viabilidad urgente, 2) Negociación con acreedores, "
                "3) Valorar preconcurso o concurso voluntario. Consultar abogado concursalista."
            )
            
        elif balance.patrimonio_neto and balance.patrimonio_neto < 0:
            conclusion = OpinionConclusion.SITUACION_PREOCUPANTE
            confianza = "MEDIA"
            
            fundamentos = [
                f"Patrimonio neto negativo: {balance.patrimonio_neto}€",
                "Sin impagos exigibles documentados actualmente"
            ]
            
            # P0.11: Referencias legales explícitas
            base_legal = ["Art. 2.4.1º TRLC", "Art. 363 LSC"]
            
            recomendacion = (
                "Situación patrimonial preocupante que requiere atención. "
                "Se recomienda: 1) Auditoría completa de deudas exigibles, "
                "2) Plan de recapitalización, 3) Monitoreo continuo de liquidez."
            )
            
        else:
            conclusion = OpinionConclusion.SIN_INDICIOS_INSOLVENCIA
            confianza = "ALTA"
            
            fundamentos = [
                "No se detectan indicios de insolvencia actual o inminente",
                "Situación patrimonial estable según documentación aportada"
            ]
            
            # P0.11: Referencias legales explícitas
            base_legal = ["Art. 2 TRLC"]
            
            recomendacion = "Continuar con monitoreo habitual de indicadores financieros."
        
        return LegalOpinion(
            conclusion=conclusion,
            fundamentos=fundamentos,
            base_legal=base_legal,
            confianza=confianza,
            recomendacion=recomendacion,
        )
    
    def _calcular_confidence_clasificacion(self, creditos: list[Credit]) -> float:
        """Calcula confidence media de clasificación."""
        if not creditos:
            return 0.5
        return sum(c.confidence for c in creditos) / len(creditos)
    
    def _calcular_confidence_ratios(self, ratios: dict) -> float:
        """Calcula confidence de ratios (basado en cuántos se pudieron calcular)."""
        calculados = sum(1 for r in ratios.values() if r.status == "CALCULADO")
        total = len(ratios)
        return calculados / total if total > 0 else 0.5
    
    def persist_balance_to_db(
        self,
        db: Session,
        output: BalanceConcursalOutput,
        created_by: Optional[str] = None
    ) -> BalanceSituacion:
        """
        Persiste el balance concursal en BD con versionado.
        
        Args:
            db: Sesión de BD
            output: Output completo del análisis
            created_by: Usuario que crea el análisis
            
        Returns:
            BalanceSituacion persistido
        """
        # 1. Obtener versión anterior y calcular nueva versión
        previous_balance = (
            db.query(BalanceSituacion)
            .filter(
                BalanceSituacion.case_id == output.case_id,
                BalanceSituacion.is_active == True
            )
            .first()
        )
        
        new_version = 1
        if previous_balance:
            new_version = previous_balance.version + 1
            # Desactivar versión anterior
            previous_balance.is_active = False
            previous_balance.superseded_by = output.balance_id
        
        # 2. Crear BalanceSituacion
        balance_db = BalanceSituacion(
            balance_id=output.balance_id,
            case_id=output.case_id,
            fecha_analisis=output.fecha_analisis,
            version=new_version,
            ruleset_version=output.ruleset_version,
            is_active=True,
            balance_data=output.balance.model_dump(),
            pyg_data=output.pyg.model_dump() if output.pyg else None,
            total_activo=str(output.balance.total_activo) if output.balance.total_activo else None,
            total_pasivo=str(output.balance.total_pasivo) if output.balance.total_pasivo else None,
            patrimonio_neto=str(output.balance.patrimonio_neto) if output.balance.patrimonio_neto else None,
            ratios={k: v.model_dump() for k, v in output.ratios.items()},
            insolvencia_actual=output.analisis_insolvencia["actual"]["existe_insolvencia_actual"],
            insolvencia_inminente=output.analisis_insolvencia["inminente"]["existe_insolvencia_inminente"],
            indicadores_insolvencia=output.analisis_insolvencia,
            dictamen=output.dictamen.model_dump(),
            confidence=output.confidence,
            created_by=created_by,
        )
        
        db.add(balance_db)
        db.flush()  # Asegurar que balance_id está disponible
        
        # 3. Crear créditos
        for credit in output.creditos:
            credit_db = CreditoDB(
                credit_id=credit.credit_id,
                balance_id=output.balance_id,
                creditor_id=credit.creditor_id,
                creditor_name=credit.creditor_name,
                principal_amount=str(credit.principal_amount),
                interest_amount=str(credit.interest_amount),
                total_amount=str(credit.total_amount),
                nature=credit.nature.value,
                secured=credit.secured,
                guarantee_type=credit.guarantee_type,
                guarantee_value=str(credit.guarantee_value) if credit.guarantee_value else None,
                devengo_date=credit.devengo_date,
                due_date=credit.due_date,
                source_document_id=credit.source_document_id,
                source_description=credit.source_description,
                trlc_classification=credit.trlc_classification.value,
                classification_reasoning=credit.classification_reasoning,
                excluded_from_categories=credit.excluded_from_categories,
                confidence=credit.confidence,
                extraction_method=credit.extraction_method,
            )
            db.add(credit_db)
        
        db.commit()
        db.refresh(balance_db)
        
        return balance_db