"""
Builder determinista del Informe de Situación Económica (bundle).

Reglas:
- NO inventar datos: si falta, marcar "no_determinable"
- Evidencia siempre que se pueda (reutiliza Evidence de financial_analysis y evidence de alertas)
- Citas legales vía RAG legal (si OPENAI_API_KEY está disponible y el vectorstore legal existe)
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.api.analysis_alerts import get_analysis_alerts
from app.models.case import Case
from app.models.economic_report import (
    ClientSummary,
    EconomicReportBundle,
    EvidenceRef,
    LegalCitation,
    RoadmapItem,
)
from app.rag.legal_rag.service import query_legal_rag
from app.services.financial_analysis import FinancialAnalysisResult
from app.services.legal_synthesis import synthesize_legal_position


def _guess_debtor_type(case_name: str) -> str:
    n = (case_name or "").upper()
    if any(x in n for x in [" S.L", " SL", " S.A", " SA", " SOCIEDAD", " SLP", " S.L.P"]):
        return "company"
    if any(x in n for x in ["DNI", "AUTÓNOMO", "AUTONOMO", "PERSONA FÍSICA", "PERSONA FISICA"]):
        return "person"
    return "unknown"


def _mk_report_id(case_id: str) -> str:
    return hashlib.sha256(f"{case_id}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:16]


def _evidence_from_financial(e) -> EvidenceRef:
    return EvidenceRef(
        document_id=e.document_id,
        filename=e.filename,
        chunk_id=e.chunk_id,
        page=e.page,
        start_char=e.start_char,
        end_char=e.end_char,
        excerpt=e.excerpt,
        extraction_method=e.extraction_method,
    )


def _pick_any_evidence(financial: FinancialAnalysisResult) -> list[EvidenceRef]:
    evs: list[EvidenceRef] = []
    try:
        if financial.insolvency:
            for s in (financial.insolvency.signals_impago or [])[:1]:
                evs.append(_evidence_from_financial(s.evidence))
            for s in (financial.insolvency.signals_contables or [])[:1]:
                evs.append(_evidence_from_financial(s.evidence))
    except Exception:
        pass
    return evs


def _build_client_summary(financial: FinancialAnalysisResult, alerts_count: int) -> ClientSummary:
    # Situación base por señales de insolvencia/ratios (determinista y conservador)
    situation = "no_determinable"
    key_points: list[str] = []
    next_7_days: list[str] = []
    warnings: list[str] = []

    if financial.insolvency:
        impagos = len(financial.insolvency.signals_impago or [])
        contables = len(financial.insolvency.signals_contables or [])
        exig = len(financial.insolvency.signals_exigibilidad or [])
        key_points.append(financial.insolvency.overall_assessment)
        if impagos > 0:
            situation = "critica"
            next_7_days.append("Revisar de inmediato embargos/requerimientos y su calendario.")
        elif contables > 0 and exig > 0:
            situation = "preocupante"
            next_7_days.append("Preparar relación de acreedores y vencimientos (facturas >90 días).")
        elif contables > 0:
            situation = "preocupante"
            next_7_days.append("Completar documentación contable para confirmar diagnóstico (balance/PyG).")

        if financial.insolvency.critical_missing_docs:
            warnings.append(
                "Faltan documentos críticos: "
                + ", ".join(financial.insolvency.critical_missing_docs[:5])
            )

    if alerts_count > 0:
        key_points.append(f"Se detectaron {alerts_count} alerta(s) en la documentación.")
        next_7_days.append("Revisar alertas y evidencias asociadas (duplicados/inconsistencias/patrones).")

    if not key_points:
        key_points.append("No hay datos suficientes para concluir una situación económica con seguridad.")

    headline = {
        "critica": "Situación económica crítica: requiere actuación inmediata.",
        "preocupante": "Situación económica preocupante: hay señales relevantes a confirmar.",
        "estable": "Situación económica estable con la documentación disponible.",
        "no_determinable": "Situación económica no determinable con la documentación actual.",
    }[situation]

    return ClientSummary(
        headline=headline,
        situation=situation,  # type: ignore[arg-type]
        key_points=key_points[:6],
        next_7_days=next_7_days[:6],
        warnings=warnings[:6],
    )



def _get_legal_citations_bundle(debtor_type: str) -> dict[str, list[LegalCitation]]:
    """
    Recupera citas legales desde el RAG legal.
    Si no hay OpenAI o no existe corpus, devuelve dict vacío.
    """
    sections: dict[str, list[LegalCitation]] = {}

    # Consultas "seguras" (TRLC / LC)
    queries = {
        "concurso": "requisitos y efectos del concurso de acreedores TRLC",
        "credito_publico": "crédito público en el concurso de acreedores TRLC",
        "exoneracion": "exoneración del pasivo insatisfecho TRLC requisitos",
        "calificacion": "calificación culpable concurso de acreedores TRLC presunciones",
    }
    # Si es empresa, exoneración se trata como "posible no aplicable" (pero citamos igualmente por transparencia)
    if debtor_type == "company":
        queries["exoneracion"] = "exoneración del pasivo insatisfecho persona física TRLC"

    for section, q in queries.items():
        raw = query_legal_rag(q, top_k=6, include_ley=True, include_jurisprudencia=True) or []
        citations: list[LegalCitation] = []
        for r in raw[:6]:
            try:
                citations.append(LegalCitation(**r))
            except Exception:
                # Mantener robustez (si cambia contrato)
                citations.append(
                    LegalCitation(
                        citation=str(r.get("citation") or "Referencia legal"),
                        text=str(r.get("text") or ""),
                        source=str(r.get("source") or "ley"),  # type: ignore[arg-type]
                        authority_level=r.get("authority_level"),
                        relevance=r.get("relevance"),
                        article=r.get("article"),
                        law=r.get("law"),
                        court=r.get("court"),
                        date=r.get("date"),
                    )
                )
        if citations:
            sections[section] = citations

    return sections


def _build_roadmap(
    *,
    debtor_type: str,
    financial: FinancialAnalysisResult,
    alerts_count: int,
    legal_citations: dict[str, list[LegalCitation]],
) -> list[RoadmapItem]:
    """
    Hoja de ruta determinista para iniciar y continuar el concurso.
    No sustituye asesoramiento profesional: es guía operativa condicionada por evidencias.
    """
    ev = _pick_any_evidence(financial)
    steps: list[RoadmapItem] = []

    missing = set((financial.insolvency.critical_missing_docs or []) if financial.insolvency else [])

    # Fase 0-7 días
    steps.append(
        RoadmapItem(
            phase="0–7 días",
            step="Consolidar expediente documental (inventario, balance, PyG, acreedores, vencimientos).",
            priority="INMEDIATA",
            status="pendiente" if missing else "en_curso",
            rationale=(
                "Sin documentación mínima no es posible una estrategia sólida. "
                "Si faltan documentos críticos, el análisis es no concluyente."
            ),
            evidence=ev,
            legal_basis=legal_citations.get("concurso", []),
        )
    )

    # Alertas / patrones
    steps.append(
        RoadmapItem(
            phase="0–7 días",
            step="Revisar alertas del expediente (duplicidades, inconsistencias, patrones sospechosos) y depurar evidencias.",
            priority="ALTA" if alerts_count else "MEDIA",
            status="pendiente" if alerts_count else "no_determinable",
            rationale=(
                "Las alertas pueden afectar la calidad probatoria y la narrativa del expediente. "
                "Si no hay alertas, este paso no aplica."
            ),
            evidence=ev,
            legal_basis=[],
        )
    )

    # Crédito público / AEAT / TGSS (guía operativa, sin inventar normativa si no existe)
    steps.append(
        RoadmapItem(
            phase="7–15 días",
            step="Identificar deuda con Hacienda (AEAT) y Seguridad Social (TGSS) y preparar opciones (aplazamiento/fraccionamiento/plan).",
            priority="ALTA",
            status="pendiente",
            rationale=(
                "Deuda pública suele condicionar el plan de pagos y la viabilidad. "
                "El sistema mostrará opciones típicas; la aplicabilidad depende de los documentos aportados."
            ),
            evidence=ev,
            legal_basis=legal_citations.get("credito_publico", []),
        )
    )

    # Presentación concurso (alto nivel)
    steps.append(
        RoadmapItem(
            phase="15–30 días",
            step="Preparar solicitud y anexos del concurso (lista de acreedores, inventario, cuentas, hechos relevantes).",
            priority="ALTA",
            status="pendiente",
            rationale="Paso operativo estándar para iniciar el procedimiento; requiere revisión profesional.",
            evidence=ev,
            legal_basis=legal_citations.get("concurso", []),
        )
    )

    # Calificación culpable (prevención)
    steps.append(
        RoadmapItem(
            phase="1–3 meses",
            step="Preparar estrategia preventiva de calificación (trazabilidad, contabilidad, decisiones societarias).",
            priority="MEDIA",
            status="pendiente",
            rationale=(
                "Mitiga riesgos de calificación: conservar evidencias y justificar decisiones. "
                "Depende de la documentación y del timeline."
            ),
            evidence=ev,
            legal_basis=legal_citations.get("calificacion", []),
        )
    )

    # Exoneración (solo si persona física)
    if debtor_type == "person":
        steps.append(
            RoadmapItem(
                phase="1–3 meses",
                step="Evaluar posible exoneración del pasivo insatisfecho (si procede) y requisitos documentales.",
                priority="MEDIA",
                status="pendiente",
                rationale=(
                    "La exoneración solo se evalúa con datos completos y requisitos. "
                    "El informe aportará citas y dirá 'no hay' si faltan evidencias."
                ),
                evidence=ev,
                legal_basis=legal_citations.get("exoneracion", []),
            )
        )

    return steps


def build_economic_report_bundle(db: Session, *, case_id: str, financial_analysis: FinancialAnalysisResult) -> EconomicReportBundle:
    case = (
        db.query(Case)
        .options(joinedload(Case.documents))
        .filter(Case.case_id == case_id)
        .first()
    )
    if not case:
        raise ValueError(f"Caso '{case_id}' no encontrado")

    debtor_type = _guess_debtor_type(case.name)

    # Alertas técnicas / patrones
    alerts = get_analysis_alerts(case_id=case_id, db=db)

    # --------------------------------------------------
    # Síntesis jurídica determinista (recomendaciones “del abogado” vía reglas)
    # --------------------------------------------------
    risks: list[dict] = []

    # Riesgos a partir de insolvencia (datos fríos)
    if financial_analysis.insolvency:
        for s in (financial_analysis.insolvency.signals_impago or [])[:5]:
            risks.append(
                {
                    "risk_type": "impago_efectivo",
                    "severity": "high",
                    "explanation": s.description,
                }
            )
        for s in (financial_analysis.insolvency.signals_contables or [])[:5]:
            risks.append(
                {
                    "risk_type": "accounting_red_flags",
                    "severity": "high" if "Patrimonio neto negativo" in s.description else "medium",
                    "explanation": s.description,
                }
            )
        if financial_analysis.insolvency.critical_missing_docs:
            risks.append(
                {
                    "risk_type": "documentation_gap",
                    "severity": "high",
                    "explanation": "Faltan documentos críticos: "
                    + ", ".join(financial_analysis.insolvency.critical_missing_docs[:8]),
                }
            )

    # Riesgos por validaciones contables
    if financial_analysis.validation_result and isinstance(financial_analysis.validation_result, dict):
        issues = financial_analysis.validation_result.get("issues") or []
        if issues:
            risks.append(
                {
                    "risk_type": "accounting_red_flags",
                    "severity": "medium",
                    "explanation": f"Validaciones contables con incidencias: {len(issues)} issue(s).",
                }
            )

    # Hallazgos técnicos (alertas) -> legal_findings "fríos"
    legal_findings: list[dict] = [
        {
            "type": (a.alert_type.value if hasattr(a.alert_type, "value") else str(a.alert_type)),
            "description": a.description,
        }
        for a in (alerts or [])
    ]

    # Timeline (convertido a dict)
    timeline_dicts: list[dict] = []
    try:
        for e in (financial_analysis.timeline or [])[:200]:
            if hasattr(e, "model_dump"):
                timeline_dicts.append(e.model_dump())
            else:
                timeline_dicts.append(dict(e))
    except Exception:
        timeline_dicts = []

    # Documentos (resumen)
    documents: list[dict] = []
    try:
        for d in (case.documents or [])[:500]:
            documents.append(
                {
                    "document_id": d.document_id,
                    "filename": d.filename,
                    "doc_type": d.doc_type,
                    "created_at": d.created_at.isoformat() if getattr(d, "created_at", None) else None,
                }
            )
    except Exception:
        documents = []

    legal_synthesis: dict = {}
    try:
        legal_synthesis = synthesize_legal_position(
            risks=risks,
            legal_findings=legal_findings,
            timeline=timeline_dicts,
            documents=documents,
        )
    except Exception:
        # No bloquear el informe por síntesis: degradar
        legal_synthesis = {}

    # Citas legales (RAG legal)
    legal_citations_raw = _get_legal_citations_bundle(debtor_type)

    # Roadmap determinista
    roadmap = _build_roadmap(
        debtor_type=debtor_type,
        financial=financial_analysis,
        alerts_count=len(alerts),
        legal_citations=legal_citations_raw,
    )

    # Añadir recomendaciones estratégicas (si existen) como pasos explícitos
    try:
        recs = (legal_synthesis or {}).get("strategic_recommendations") or []
        for r in recs[:8]:
            action = r.get("action") or "Acción recomendada"
            rationale = r.get("rationale") or ""
            priority = r.get("priority") or "MEDIA"
            roadmap.append(
                RoadmapItem(
                    phase="Plan de acción",
                    step=str(action),
                    priority=str(priority),  # type: ignore[arg-type]
                    status="pendiente",
                    rationale=str(rationale) if rationale else "Recomendación derivada de reglas.",
                    evidence=_pick_any_evidence(financial_analysis),
                    legal_basis=legal_citations_raw.get("concurso", []),
                )
            )
    except Exception:
        pass

    # Resumen cliente determinista
    client_summary = _build_client_summary(financial_analysis, alerts_count=len(alerts))

    # Normalizar legal_citations a tipo correcto
    legal_citations: dict[str, list[LegalCitation]] = {}
    for k, v in (legal_citations_raw or {}).items():
        legal_citations[k] = v

    bundle = EconomicReportBundle(
        report_id=_mk_report_id(case_id),
        case_id=case_id,
        case_name=case.name,
        generated_at=datetime.utcnow(),
        debtor_type=debtor_type,  # type: ignore[arg-type]
        financial_analysis=financial_analysis,
        alerts=alerts,
        legal_synthesis=legal_synthesis,
        roadmap=roadmap,
        legal_citations=legal_citations,
        client_summary=client_summary,
        narrative_md=None,
    )

    # Validación final (fail fast)
    json.dumps(bundle.model_dump(), ensure_ascii=False, default=str)
    return bundle

