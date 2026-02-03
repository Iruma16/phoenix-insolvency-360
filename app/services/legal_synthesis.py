"""
SÍNTESIS JURÍDICA - Transforma hallazgos técnicos en criterio legal reproducible.

PRINCIPIOS:
1. Cada decisión es auditable (qué regla, con qué datos, por qué)
2. Separación total: lógica aquí, render en pdf_report.py
3. El sistema puede decir "NO SÉ" (aumenta credibilidad)

REGLAS BASE: TRLC (Texto Refundido Ley Concursal)
"""
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


class RiskLevel(str, Enum):
    CRITICAL = "CRÍTICO"
    HIGH = "ALTO"
    MEDIUM = "MEDIO"
    LOW = "BAJO"
    INDETERMINATE = "INDETERMINADO"


class LegalWeight(str, Enum):
    CRITICAL = "CRÍTICO"
    HIGH = "ALTO"
    MEDIUM = "MEDIO"
    LOW = "BAJO"
    NEUTRAL = "NEUTRO"


@dataclass
class RuleTrace:
    """Auditabilidad: qué regla se disparó, con qué datos, por qué."""

    rule_id: str
    rule_name: str
    triggered_by: list[str]
    article_trlc: str
    reasoning: str
    evidence: dict[str, Any]


@dataclass
class LegalThesis:
    """Conclusión principal del informe."""

    statement: str
    risk_level: RiskLevel
    reasoning: str
    can_conclude: bool  # False = "NO SÉ"
    inconclusive_reason: Optional[str]
    rule_trace: Optional[RuleTrace]


@dataclass
class HierarchizedRisk:
    """Riesgo ordenado por peso legal, no por severity técnica."""

    legal_weight: LegalWeight
    fact: str
    article_trlc: str
    consequence: str
    defense_possible: Optional[str]
    rule_trace: RuleTrace


@dataclass
class DocumentaryGap:
    """Vacío documental peligroso."""

    missing_document: str
    legal_interpretation: str
    article_trlc: str
    severity: LegalWeight


@dataclass
class StrategicRecommendation:
    """Acción concreta y accionable."""

    action: str
    rationale: str
    priority: str  # "INMEDIATA", "ALTA", "MEDIA"


@dataclass
class LegalSynthesis:
    """Output completo de la síntesis jurídica."""

    thesis: LegalThesis
    risk_hierarchy: list[HierarchizedRisk]
    fact_to_consequence: list[dict[str, Any]]
    documentary_gaps: list[DocumentaryGap]
    strategic_recommendations: list[StrategicRecommendation]
    neutral_facts: list[dict[str, Any]]


# ========================================
# BLOQUE A: TESIS GLOBAL
# ========================================


def _rule_R1_delay_filing(risks: list[dict], timeline: list[dict]) -> Optional[RuleTrace]:
    """
    R1: Retraso en solicitud de concurso.
    Art. 5 + 164.2.1º TRLC - Presunción de culpabilidad.
    """
    delay_risk = next((r for r in risks if r.get("risk_type") == "delay_filing"), None)
    if not delay_risk:
        return None

    # Buscar evento de insolvencia en timeline
    insolvency_event = None
    for event in timeline:
        desc = event.get("description", "").lower()
        if any(kw in desc for kw in ["insolvencia", "pérdida", "negativo", "impago"]):
            insolvency_event = event
            break

    if delay_risk.get("severity") == "high":
        return RuleTrace(
            rule_id="R1",
            rule_name="Retraso en solicitud de concurso",
            triggered_by=[
                f"delay_filing severity={delay_risk.get('severity')}",
                f"insolvency_detected={insolvency_event is not None}",
            ],
            article_trlc="Art. 5 + 164.2.1º TRLC",
            reasoning="Presunción de culpabilidad por retraso >2 meses desde conocimiento de insolvencia",
            evidence={"delay_risk": delay_risk, "insolvency_event": insolvency_event},
        )

    return None


def _rule_R2_negative_equity(risks: list[dict]) -> Optional[RuleTrace]:
    """
    R2: Patrimonio neto negativo reiterado.
    Art. 363 LSC + 164 TRLC - Indicio de gestión negligente.
    """
    accounting_risks = [r for r in risks if r.get("risk_type") == "accounting_red_flags"]

    for risk in accounting_risks:
        desc = risk.get("explanation", "").lower()
        if "patrimonio neto negativo" in desc or "balance negativo" in desc:
            return RuleTrace(
                rule_id="R2",
                rule_name="Patrimonio neto negativo reiterado",
                triggered_by=[f"accounting_red_flags: {desc[:100]}"],
                article_trlc="Art. 363 LSC + 164 TRLC",
                reasoning="Indicio de gestión negligente - NO culpabilidad automática, pero suma",
                evidence={"risk": risk},
            )

    return None


def _rule_R3_missing_accounting(risks: list[dict], documents: list[dict]) -> Optional[RuleTrace]:
    """
    R3: Ausencia de contabilidad fiable.
    Art. 164.2.2º TRLC - Presunción CASI DIRECTA de culpabilidad.
    """
    doc_gap = next((r for r in risks if r.get("risk_type") == "documentation_gap"), None)
    if not doc_gap:
        return None

    missing = doc_gap.get("explanation", "").lower()
    critical_missing = any(kw in missing for kw in ["estados contables", "balance", "contabilidad"])

    if critical_missing and doc_gap.get("severity") == "high":
        return RuleTrace(
            rule_id="R3",
            rule_name="Ausencia de contabilidad fiable",
            triggered_by=[
                "documentation_gap severity=high",
                f"missing_critical_docs: {missing[:100]}",
            ],
            article_trlc="Art. 164.2.2º TRLC",
            reasoning="CRÍTICO: Presunción casi directa de culpabilidad - casi indefendible",
            evidence={"doc_gap": doc_gap, "documents_count": len(documents)},
        )

    return None


# ========================================
# BLOQUE B: RIESGOS DETERMINANTES
# ========================================


def _rule_R4_selective_payments(risks: list[dict]) -> Optional[RuleTrace]:
    """R4: Pagos selectivos/preferentes - Art. 164.2.4º TRLC."""
    # Implementar cuando haya detección de pagos selectivos
    return None


def _rule_R5_related_party_operations(risks: list[dict]) -> Optional[RuleTrace]:
    """R5: Operaciones con vinculadas - Arts. 283-287 TRLC."""
    # Implementar cuando haya detección de operaciones vinculadas
    return None


def _rule_R6_repeated_seizures(risks: list[dict], timeline: list[dict]) -> Optional[RuleTrace]:
    """R6: Embargos administrativos reiterados - Art. 164 TRLC (indicio)."""
    embargo_events = [e for e in timeline if "embargo" in e.get("description", "").lower()]

    if len(embargo_events) >= 2:
        return RuleTrace(
            rule_id="R6",
            rule_name="Embargos administrativos reiterados",
            triggered_by=[f"embargo_count={len(embargo_events)}"],
            article_trlc="Art. 164 TRLC (indicio)",
            reasoning="Refuerza conocimiento de insolvencia - suma, no determina solo",
            evidence={"embargos": embargo_events},
        )

    return None


# ========================================
# BLOQUE D: VACÍOS DOCUMENTALES
# ========================================


def _rule_R9_missing_corporate_decisions(
    documents: list[dict], risks: list[dict]
) -> Optional[DocumentaryGap]:
    """R9: Falta de actas/decisiones societarias."""
    doc_gap = next((r for r in risks if r.get("risk_type") == "documentation_gap"), None)
    if not doc_gap:
        return None

    missing = doc_gap.get("explanation", "").lower()
    if "actas" in missing or "junta" in missing:
        return DocumentaryGap(
            missing_document="Actas de junta / decisiones societarias",
            legal_interpretation="La ausencia será interpretada como presunción de opacidad por el administrador concursal",
            article_trlc="Art. 164 TRLC",
            severity=LegalWeight.HIGH,
        )

    return None


def _rule_R10_missing_key_contracts(
    documents: list[dict], risks: list[dict]
) -> Optional[DocumentaryGap]:
    """R10: Falta de contratos clave."""
    doc_gap = next((r for r in risks if r.get("risk_type") == "documentation_gap"), None)
    if not doc_gap:
        return None

    missing = doc_gap.get("explanation", "").lower()
    if "contrato" in missing:
        return DocumentaryGap(
            missing_document="Contratos clave con proveedores/clientes",
            legal_interpretation="Debilita posición defensiva - riesgo probatorio",
            article_trlc="Art. 164 TRLC",
            severity=LegalWeight.MEDIUM,
        )

    return None


# ========================================
# BLOQUE E: REGLAS DE SÍNTESIS
# ========================================


def _rule_S1_dangerous_accumulation(traces: list[RuleTrace]) -> bool:
    """S1: Acumulación peligrosa = R1 + (R2 o R4)."""
    has_R1 = any(t.rule_id == "R1" for t in traces)
    has_R2_or_R4 = any(t.rule_id in ["R2", "R4"] for t in traces)
    return has_R1 and has_R2_or_R4


def _rule_S2_almost_automatic_presumption(traces: list[RuleTrace]) -> bool:
    """S2: Presunción casi automática = R3 (sin contabilidad)."""
    return any(t.rule_id == "R3" for t in traces)


def _rule_S3_lack_of_proof(traces: list[RuleTrace], gaps: list[DocumentaryGap]) -> bool:
    """S3: Falta de prueba = hay riesgos pero faltan docs clave."""
    has_risks = len(traces) > 0
    has_critical_gaps = any(g.severity in [LegalWeight.HIGH, LegalWeight.CRITICAL] for g in gaps)
    return has_risks and has_critical_gaps


# ========================================
# FUNCIÓN PRINCIPAL
# ========================================


def synthesize_legal_position(
    risks: list[dict], legal_findings: list[dict], timeline: list[dict], documents: list[dict]
) -> dict:
    """
    NÚCLEO: Transforma hallazgos técnicos en criterio jurídico.

    Returns:
        Dict serializable (para JSON/state)
    """

    # 1. DISPARAR REGLAS (BLOQUE A, B)
    traces: list[RuleTrace] = []

    if trace := _rule_R1_delay_filing(risks, timeline):
        traces.append(trace)
    if trace := _rule_R2_negative_equity(risks):
        traces.append(trace)
    if trace := _rule_R3_missing_accounting(risks, documents):
        traces.append(trace)
    if trace := _rule_R6_repeated_seizures(risks, timeline):
        traces.append(trace)

    # 2. DETECTAR VACÍOS DOCUMENTALES (BLOQUE D)
    gaps: list[DocumentaryGap] = []

    if gap := _rule_R9_missing_corporate_decisions(documents, risks):
        gaps.append(gap)
    if gap := _rule_R10_missing_key_contracts(documents, risks):
        gaps.append(gap)

    # 3. APLICAR REGLAS DE SÍNTESIS (BLOQUE E)

    # S2: Presunción casi automática
    if _rule_S2_almost_automatic_presumption(traces):
        thesis = LegalThesis(
            statement="Existe un riesgo CRÍTICO de calificación culpable por ausencia de contabilidad fiable",
            risk_level=RiskLevel.CRITICAL,
            reasoning="La falta de contabilidad genera presunción casi directa de culpabilidad (Art. 164.2.2º TRLC)",
            can_conclude=True,
            inconclusive_reason=None,
            rule_trace=next(t for t in traces if t.rule_id == "R3"),
        )

    # S3: Falta de prueba
    elif _rule_S3_lack_of_proof(traces, gaps):
        thesis = LegalThesis(
            statement="No puede emitirse un dictamen concluyente con la información actual",
            risk_level=RiskLevel.INDETERMINATE,
            reasoning="Existen indicios de riesgo pero la falta de documentación clave impide una conclusión definitiva",
            can_conclude=False,
            inconclusive_reason=f"Documentación crítica ausente: {', '.join([g.missing_document for g in gaps])}",
            rule_trace=traces[0] if traces else None,
        )

    # S1: Acumulación peligrosa
    elif _rule_S1_dangerous_accumulation(traces):
        thesis = LegalThesis(
            statement="Existe un riesgo ALTO de calificación culpable por acumulación de indicios determinantes",
            risk_level=RiskLevel.HIGH,
            reasoning="Retraso en solicitud de concurso (R1) reforzado por patrimonio neto negativo o pagos selectivos",
            can_conclude=True,
            inconclusive_reason=None,
            rule_trace=next(t for t in traces if t.rule_id == "R1"),
        )

    # Riesgos detectados pero sin acumulación peligrosa
    elif traces:
        highest_trace = traces[0]  # Ya ordenado por importancia
        thesis = LegalThesis(
            statement=f"Se detectan indicios de riesgo que requieren análisis detallado: {highest_trace.rule_name}",
            risk_level=RiskLevel.MEDIUM,
            reasoning=highest_trace.reasoning,
            can_conclude=True,
            inconclusive_reason=None,
            rule_trace=highest_trace,
        )

    # Sin riesgos significativos
    else:
        thesis = LegalThesis(
            statement="No se aprecian indicios suficientes de calificación culpable con la documentación actual",
            risk_level=RiskLevel.LOW,
            reasoning="No se han detectado patrones de riesgo determinantes según Arts. 164-165 TRLC",
            can_conclude=True,
            inconclusive_reason=None,
            rule_trace=None,
        )

    # 4. JERARQUIZAR RIESGOS (por peso legal)
    risk_hierarchy = _hierarchize_risks(traces)

    # 5. HECHOS NEUTROS (BLOQUE C)
    neutral_facts = _extract_neutral_facts(risks, timeline)

    # 6. RECOMENDACIONES ESTRATÉGICAS
    recommendations = _generate_recommendations(thesis, traces, gaps)

    # 7. ENSAMBLAR SÍNTESIS
    synthesis = LegalSynthesis(
        thesis=thesis,
        risk_hierarchy=risk_hierarchy,
        fact_to_consequence=[],  # Se llenará con traces
        documentary_gaps=gaps,
        strategic_recommendations=recommendations,
        neutral_facts=neutral_facts,
    )

    # Serializar a dict (para state/JSON)
    return asdict(synthesis)


def _hierarchize_risks(traces: list[RuleTrace]) -> list[HierarchizedRisk]:
    """Ordena riesgos por peso legal (R3 > R1 > R2 > R6)."""
    weight_order = {"R3": 0, "R1": 1, "R2": 2, "R4": 3, "R5": 4, "R6": 5}
    sorted_traces = sorted(traces, key=lambda t: weight_order.get(t.rule_id, 99))

    hierarchy = []
    for trace in sorted_traces:
        weight = (
            LegalWeight.CRITICAL
            if trace.rule_id == "R3"
            else LegalWeight.HIGH
            if trace.rule_id in ["R1", "R4", "R5"]
            else LegalWeight.MEDIUM
        )

        hierarchy.append(
            HierarchizedRisk(
                legal_weight=weight,
                fact=trace.rule_name,
                article_trlc=trace.article_trlc,
                consequence=trace.reasoning,
                defense_possible=_get_defense(trace.rule_id),
                rule_trace=trace,
            )
        )

    return hierarchy


def _get_defense(rule_id: str) -> Optional[str]:
    """Defensa posible según regla."""
    defenses = {
        "R1": "Prueba de negociaciones activas o falta de conocimiento real de insolvencia",
        "R2": "Justificar pérdidas por contexto de mercado o medidas de reestructuración",
        "R3": None,  # Casi indefendible
        "R4": "Demostrar que los pagos eran necesarios para continuidad de actividad",
        "R6": "Contextualizar como consecuencia, no causa, de la insolvencia",
    }
    return defenses.get(rule_id)


def _extract_neutral_facts(risks: list[dict], timeline: list[dict]) -> list[dict]:
    """BLOQUE C: Hechos que NO incriminan solos."""
    neutral = []

    # R7: Facturas impagadas (contexto, no culpabilidad)
    for risk in risks:
        if risk.get("risk_type") == "document_inconsistency":
            neutral.append(
                {
                    "type": "Facturas impagadas",
                    "description": risk.get("explanation", ""),
                    "legal_weight": "BAJO-MEDIO",
                    "note": "Contexto de insolvencia, no determinante de culpabilidad",
                }
            )

    # R8: Pérdidas operativas
    for event in timeline:
        if "pérdida" in event.get("description", "").lower():
            neutral.append(
                {
                    "type": "Pérdidas operativas",
                    "description": event.get("description"),
                    "legal_weight": "CONTEXTUAL",
                    "note": "Explica insolvencia, no implica culpabilidad",
                }
            )

    return neutral[:5]  # Limitar a 5 más relevantes


def _generate_recommendations(
    thesis: LegalThesis, traces: list[RuleTrace], gaps: list[DocumentaryGap]
) -> list[StrategicRecommendation]:
    """Genera recomendaciones accionables según la situación."""
    recs = []

    # Si hay R3 (sin contabilidad)
    if any(t.rule_id == "R3" for t in traces):
        recs.append(
            StrategicRecommendation(
                action="URGENTE: Reconstruir contabilidad inmediatamente",
                rationale="La ausencia de contabilidad es casi indefendible. Prioridad máxima antes de presentar concurso",
                priority="INMEDIATA",
            )
        )

    # Si hay R1 (retraso)
    if any(t.rule_id == "R1" for t in traces):
        recs.append(
            StrategicRecommendation(
                action="Documentar negociaciones y medidas de reestructuración",
                rationale="Crear evidencia de buena fe para defender el retraso en solicitud de concurso",
                priority="ALTA",
            )
        )

    # Si hay gaps críticos
    for gap in gaps:
        if gap.severity == LegalWeight.HIGH:
            recs.append(
                StrategicRecommendation(
                    action=f"Recopilar: {gap.missing_document}",
                    rationale=gap.legal_interpretation,
                    priority="ALTA",
                )
            )

    # Recomendación general
    if not thesis.can_conclude:
        recs.append(
            StrategicRecommendation(
                action="Completar expediente documental antes de presentar concurso",
                rationale="No puede defenderse una posición sin base documental sólida",
                priority="INMEDIATA",
            )
        )

    return recs
