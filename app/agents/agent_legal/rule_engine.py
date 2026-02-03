"""
Motor de reglas para el Agente Legal.
"""

import logging
from typing import Any, Optional

from .logic import _extract_allowed_articles, _normalize_article_reference
from .models import Rule, Rulebook
from .rule_evaluator import RuleEvaluator
from .schema import LegalAgentResult, LegalRisk


def _filter_legal_articles(
    legal_articles: list[str], allowed_articles: set, legal_context: str
) -> tuple:
    """Filtra artículos legales, dejando solo los permitidos."""
    valid_articles = []
    discarded_articles = []

    for article_ref in legal_articles:
        normalized = _normalize_article_reference(article_ref)
        if normalized and normalized in allowed_articles:
            valid_articles.append(article_ref)
        else:
            discarded_articles.append(article_ref)

    return valid_articles, discarded_articles


logger = logging.getLogger(__name__)


class RuleEngine:
    """Motor de evaluación de reglas legales."""

    def __init__(self, rulebook: Rulebook, legal_context: str = ""):
        """
        Inicializa el motor de reglas.

        Args:
            rulebook: Rulebook cargado con reglas
            legal_context: Contexto legal para filtrado anti-alucinación
        """
        self.rulebook = rulebook
        self.legal_context = legal_context
        self.allowed_articles = _extract_allowed_articles(legal_context)

    def evaluate_rules(self, variables: dict[str, Any]) -> list[LegalRisk]:
        """
        Evalúa todas las reglas del rulebook.

        Args:
            variables: Variables del caso

        Returns:
            Lista de riesgos legales detectados
        """
        evaluator = RuleEvaluator(variables)
        risks = []

        for rule in self.rulebook.rules:
            try:
                risk = self._evaluate_rule(rule, evaluator, variables)
                if risk:
                    risks.append(risk)
            except Exception as e:
                logger.warning(f"Error evaluando regla {rule.rule_id}: {e}")
                continue

        return risks

    def _evaluate_rule(
        self, rule: Rule, evaluator: RuleEvaluator, variables: dict[str, Any]
    ) -> Optional[LegalRisk]:
        """
        Evalúa una regla individual.

        Args:
            rule: Regla a evaluar
            evaluator: Evaluador de expresiones
            variables: Variables del caso

        Returns:
            LegalRisk si la regla se activa, None en caso contrario
        """
        try:
            missing_vars = []
            for var_name in rule.trigger.variables_required:
                if var_name not in variables:
                    missing_vars.append(var_name)

            if missing_vars:
                logger.debug(f"Regla {rule.rule_id}: faltan variables {missing_vars}")
                return None

            trigger_result = evaluator.evaluate(rule.trigger.condition)
            if trigger_result is not True:
                return None

            severity = evaluator.evaluate_severity(rule.severity_logic.dict())
            if not severity:
                severity = "indeterminado"

            confidence = evaluator.evaluate_confidence(rule.confidence_logic.dict())
            if not confidence:
                confidence = "indeterminado"

            if confidence == "indeterminate":
                confidence = "indeterminado"

            filtered_articles, discarded_articles = _filter_legal_articles(
                rule.article_refs, self.allowed_articles, self.legal_context
            )

            if discarded_articles:
                confidence = "indeterminado"

            description = evaluator.format_template(rule.outputs.description_template, {})
            recommendation = evaluator.format_template(rule.outputs.recommendation_template, {})

            evidence_status = "suficiente"
            if filtered_articles == [] and rule.article_refs != []:
                evidence_status = "falta"
            elif discarded_articles:
                evidence_status = "insuficiente"
            elif confidence == "indeterminado":
                evidence_status = "insuficiente"

            return LegalRisk(
                risk_type=rule.risk_type,
                description=description,
                severity=severity,
                legal_articles=filtered_articles,
                jurisprudence=[],
                evidence_status=evidence_status,
                recommendation=recommendation,
            )
        except Exception as e:
            logger.error(f"Error creando LegalRisk para regla {rule.rule_id}: {e}")
            return None

    def build_result(
        self, case_id: str, risks: list[LegalRisk], legal_context: str = ""
    ) -> LegalAgentResult:
        """
        Construye el resultado final del Agente Legal.

        Args:
            case_id: ID del caso
            risks: Lista de riesgos detectados
            legal_context: Contexto legal

        Returns:
            LegalAgentResult completo
        """
        try:
            if not risks:
                return LegalAgentResult(
                    case_id=case_id,
                    legal_risks=[],
                    legal_conclusion="No se detectaron riesgos legales específicos según las reglas evaluadas.",
                    confidence_level="alta",
                    missing_data=[],
                    legal_basis=[],
                )

            all_basis = []

            for risk in risks:
                all_basis.extend(risk.legal_articles)

            unique_basis = list(set(all_basis))

            confidence_levels = [risk.severity for risk in risks]
            if any(s in ("critica", "critical", "alta", "high") for s in confidence_levels):
                overall_confidence = "media"
            elif any(s in ("media", "medium") for s in confidence_levels):
                overall_confidence = "media"
            else:
                overall_confidence = "baja"

            if any(risk.severity == "indeterminado" for risk in risks):
                overall_confidence = "indeterminado"

            conclusion_parts = [f"Se detectaron {len(risks)} riesgo(s) legal(es)."]
            if unique_basis:
                conclusion_parts.append(f"Artículos relevantes: {', '.join(unique_basis[:5])}")
            legal_conclusion = " ".join(conclusion_parts)

            return LegalAgentResult(
                case_id=case_id,
                legal_risks=risks,
                legal_conclusion=legal_conclusion,
                confidence_level=overall_confidence,
                missing_data=[],
                legal_basis=unique_basis,
            )
        except Exception as e:
            logger.error(f"Error construyendo resultado: {e}")
            return LegalAgentResult(
                case_id=case_id,
                legal_risks=[],
                legal_conclusion="Error al evaluar reglas legales.",
                confidence_level="indeterminado",
                missing_data=[],
                legal_basis=[],
            )
