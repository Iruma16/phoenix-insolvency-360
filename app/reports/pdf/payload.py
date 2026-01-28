from datetime import datetime, timezone
from typing import Any


def build_report_payload(case_id: str, analysis_result: dict[str, Any]) -> dict[str, Any]:
    """
    Construye el payload estructurado del informe a partir del resultado del análisis.
    Incluye SÍNTESIS JURÍDICA para generar informe con valor profesional.

    Args:
        case_id: Identificador del caso
        analysis_result: Resultado del análisis (debe incluir: synthesis, risks, timeline, etc.)

    Returns:
        Dict con estructura del informe lista para renderizar
    """

    # Extraer datos del análisis
    risks = analysis_result.get("risks", [])
    timeline = analysis_result.get("timeline", [])
    legal_findings = analysis_result.get("legal_findings", [])
    documents = analysis_result.get("documents", [])
    report_data = analysis_result.get("report", {})
    auditor_llm = analysis_result.get("auditor_llm", {})
    prosecutor_llm = analysis_result.get("prosecutor_llm", {})

    # SÍNTESIS JURÍDICA (nueva capa de valor)
    synthesis = report_data.get("synthesis", None)

    # Calcular overall_risk (desde síntesis si existe)
    if synthesis and synthesis.get("thesis"):
        thesis_risk = synthesis["thesis"].get("risk_level", "indeterminate")
        # Normalizar (puede venir como "ALTO" o "high")
        overall_risk = str(thesis_risk).lower().replace("crítico", "critical")
    else:
        overall_risk = report_data.get("overall_risk", "indeterminate")

    # Construir resumen ejecutivo (usando síntesis si existe)
    if synthesis:
        executive_summary = _build_executive_summary_from_synthesis(synthesis, legal_findings)
    else:
        executive_summary = _build_executive_summary(risks, legal_findings, overall_risk)

    # Construir hechos del caso
    case_facts = _build_case_facts(documents, timeline)

    # Construir hallazgos y riesgos con evidencias
    findings = _build_findings_with_evidence(risks, legal_findings)

    # Extraer artículos TRLC relevantes
    legal_articles = _extract_legal_articles(legal_findings)

    # Construir tabla de trazabilidad
    traceability = _build_traceability_table(findings, legal_articles)

    return {
        "case_id": case_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "system_version": "Phoenix Legal v2.0 - Síntesis Jurídica",
        "overall_risk": overall_risk,
        "synthesis": synthesis,  # ← Nueva capa
        "executive_summary": executive_summary,
        "case_facts": case_facts,
        "findings": findings,
        "legal_articles": legal_articles,
        "traceability": traceability,
        "auditor_llm": auditor_llm,
        "prosecutor_llm": prosecutor_llm,
    }


def _build_executive_summary_from_synthesis(
    synthesis: dict[str, Any], legal_findings: list[dict]
) -> dict[str, Any]:
    """Construye resumen ejecutivo desde SÍNTESIS JURÍDICA (nueva capa de valor)."""

    thesis = synthesis.get("thesis", {})
    risk_hierarchy = synthesis.get("risk_hierarchy", [])

    # Contar por peso legal (no por severity técnica)
    risk_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for risk in risk_hierarchy:
        weight = str(risk.get("legal_weight", "low")).lower()
        if weight in risk_counts:
            risk_counts[weight] += 1

    # Top 3 riesgos por peso legal
    top_risks = risk_hierarchy[:3]

    return {
        "overall_risk": str(thesis.get("risk_level", "indeterminate")).lower(),
        "thesis_statement": thesis.get("statement", ""),
        "thesis_reasoning": thesis.get("reasoning", ""),
        "can_conclude": thesis.get("can_conclude", True),
        "inconclusive_reason": thesis.get("inconclusive_reason"),
        "risk_counts": risk_counts,
        "top_risks": [
            {
                "type": r.get("fact", "unknown"),
                "legal_weight": r.get("legal_weight", "low"),
                "article": r.get("article_trlc", ""),
                "consequence": r.get("consequence", "Sin descripción")[:200],
                "defense": r.get("defense_possible"),
            }
            for r in top_risks
        ],
        "legal_findings_count": len(legal_findings),
    }


def _build_executive_summary(
    risks: list[dict], legal_findings: list[dict], overall_risk: str
) -> dict[str, Any]:
    """Construye el resumen ejecutivo (legacy, sin síntesis)."""

    # Contar riesgos por severidad
    risk_counts = {"high": 0, "medium": 0, "low": 0, "indeterminate": 0}
    for risk in risks:
        severity = risk.get("severity", "indeterminate")
        risk_counts[severity] = risk_counts.get(severity, 0) + 1

    # Principales riesgos (top 3 por severidad)
    severity_order = {"high": 0, "medium": 1, "low": 2, "indeterminate": 3}
    sorted_risks = sorted(
        risks, key=lambda r: severity_order.get(r.get("severity", "indeterminate"), 99)
    )
    top_risks = sorted_risks[:3]

    return {
        "overall_risk": overall_risk,
        "risk_counts": risk_counts,
        "top_risks": [
            {
                "type": r.get("risk_type", "unknown"),
                "severity": r.get("severity", "indeterminate"),
                "confidence": r.get("confidence", "indeterminate"),
                "description": r.get("explanation", "Sin descripción")[:200],
            }
            for r in top_risks
        ],
        "legal_findings_count": len(legal_findings),
    }


def _build_case_facts(documents: list[dict], timeline: list[dict]) -> list[dict[str, str]]:
    """Construye la lista de hechos extraídos del caso."""

    facts: list[dict[str, str]] = []

    # Hechos de la timeline
    for event in timeline[:10]:  # Limitar a 10 eventos más relevantes
        facts.append(
            {
                "source_type": "timeline",
                "date": event.get("date", "Fecha desconocida"),
                "description": event.get("description", "Sin descripción"),
                "document": event.get("doc_type", "documento"),
            }
        )

    # Hechos de documentos clave
    key_doc_types = ["acta", "contabilidad", "contrato"]
    for doc in documents:
        if doc.get("doc_type") in key_doc_types:
            facts.append(
                {
                    "source_type": "document",
                    "date": doc.get("date", "N/A"),
                    "description": f"Documento: {doc.get('filename', 'sin nombre')}",
                    "document": doc.get("doc_type", "documento"),
                }
            )

    return facts[:15]  # Limitar a 15 hechos más relevantes


def _build_findings_with_evidence(
    risks: list[dict], legal_findings: list[dict]
) -> list[dict[str, Any]]:
    """Construye hallazgos con evidencias completas."""

    findings = []

    for risk in risks:
        finding: dict[str, Any] = {
            "type": risk.get("risk_type", "unknown"),
            "severity": risk.get("severity", "indeterminate"),
            "confidence": risk.get("confidence", "indeterminate"),
            "description": risk.get("explanation", "Sin descripción"),
            "impact": risk.get("impact", "Impacto no especificado"),
            "evidence_case": risk.get("evidence", []),
            "evidence_law": [],
            "has_sufficient_evidence": len(risk.get("evidence", [])) > 0,
        }

        # Buscar legal_finding correspondiente para añadir evidencia legal
        matching_lf = next(
            (lf for lf in legal_findings if lf.get("finding_type") == risk.get("risk_type")),
            None,
        )

        if matching_lf:
            finding["evidence_law"] = matching_lf.get("legal_basis", [])
            finding["weight"] = matching_lf.get("weight", 0)
            finding["counter_evidence"] = matching_lf.get("counter_evidence", [])
            finding["mitigation"] = matching_lf.get("mitigation", "")

        findings.append(finding)

    return findings


def _extract_legal_articles(legal_findings: list[dict]) -> list[dict[str, str]]:
    """Extrae artículos del TRLC mencionados."""

    articles: list[dict[str, str]] = []
    seen_articles = set()

    for finding in legal_findings:
        legal_basis = finding.get("legal_basis", [])
        for article in legal_basis:
            article_ref = f"{article.get('law', '')}_{article.get('article', '')}"

            if article_ref not in seen_articles:
                articles.append(
                    {
                        "ref": f"{article.get('law', 'TRLC')} Art. {article.get('article', 'N/A')}",
                        "description": article.get("description", "Sin descripción")[:300],
                        "relevance": finding.get("finding_type", "general"),
                        "source": article.get("source", "BOE"),
                    }
                )
                seen_articles.add(article_ref)

    return articles


def _build_traceability_table(findings: list[dict], articles: list[dict]) -> list[dict[str, str]]:
    """Construye tabla de trazabilidad claim -> evidencia caso -> evidencia ley."""

    traceability = []

    for finding in findings:
        claim = f"{finding['type']}: {finding['description'][:100]}"

        # Evidencia del caso
        evidence_case = finding.get("evidence_case", [])
        case_evidence_parts = []
        for ev in evidence_case[:2]:
            if isinstance(ev, dict):
                text = ev.get("summary", ev.get("description", "Sin detalles"))
            elif isinstance(ev, str):
                text = ev
            else:
                text = str(ev)
            case_evidence_parts.append(text[:50])

        case_evidence = "; ".join(case_evidence_parts) or "Sin evidencia de caso"

        # Evidencia legal
        legal_evidence = (
            "; ".join([f"{ev.get('article', 'N/A')}" for ev in finding.get("evidence_law", [])[:2]])
            or "Sin artículos aplicables"
        )

        traceability.append(
            {
                "claim": claim,
                "case_source": case_evidence,
                "legal_source": legal_evidence,
                "confidence": finding.get("confidence", "N/A"),
            }
        )

    return traceability
