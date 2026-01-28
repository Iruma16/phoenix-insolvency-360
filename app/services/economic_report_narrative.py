"""
Generación opcional de narrativa (Markdown) con LLM para el informe económico.

Principio:
- El LLM SOLO redacta; no calcula ni inventa.
- Se le pasa como "contexto documental" un resumen estructurado del bundle + contexto recuperado por RAG.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.agents.base.response_builder import build_llm_answer
from app.models.economic_report import EconomicReportBundle
from app.rag.case_rag.service import query_case_rag


def _bundle_for_llm(bundle: EconomicReportBundle) -> str:
    """
    Reducir el bundle a un payload compacto para LLM (evitar ruido y tokens excesivos).
    """
    fin = bundle.financial_analysis
    payload = {
        "case": {"case_id": bundle.case_id, "case_name": bundle.case_name, "debtor_type": bundle.debtor_type},
        "client_summary": bundle.client_summary.model_dump(),
        "financial": {
            "analysis_date": fin.analysis_date.isoformat(),
            "ratios": [r.model_dump() for r in (fin.ratios or [])][:10],
            "insolvency": fin.insolvency.model_dump() if fin.insolvency else None,
            "credit_classification": [c.model_dump() for c in (fin.credit_classification or [])][:20],
            "total_debt": fin.total_debt,
            "timeline_patterns": fin.timeline_patterns,
            "timeline_statistics": fin.timeline_statistics,
        },
        "alerts": [
            {
                "alert_type": (a.alert_type.value if hasattr(a.alert_type, "value") else str(a.alert_type)),
                "description": a.description,
                "evidence_count": len(a.evidence or []),
            }
            for a in (bundle.alerts or [])[:20]
        ],
        "legal_synthesis": bundle.legal_synthesis,
        "roadmap": [r.model_dump() for r in (bundle.roadmap or [])][:15],
        "legal_citations": {k: [c.model_dump() for c in v[:3]] for k, v in (bundle.legal_citations or {}).items()},
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def build_economic_report_narrative_md(db: Session, *, bundle: EconomicReportBundle) -> str:
    """
    Genera un Markdown narrativo con LLM apoyado por RAG del caso.
    """
    # Recuperar contexto del caso (chunks) para citar evidencias
    query = (
        "Situación económica: insolvencia, embargos, deudas con Hacienda o Seguridad Social, "
        "facturas vencidas, balance, pérdidas y pagos. Extraer solo lo que esté explícito."
    )
    case_context = query_case_rag(db=db, case_id=bundle.case_id, query=query) or ""

    context_text = (
        "BUNDLE_ESTRUCTURADO (fuente principal, datos ya validados por el sistema):\n"
        + _bundle_for_llm(bundle)
        + "\n\n"
        + "CONTEXTO_RECUPERADO_RAG_DEL_CASO (fragmentos literales):\n"
        + case_context[:20000]
    )

    question = (
        "Redacta un informe en Markdown, en español, orientado a cliente, con el siguiente índice:\n"
        "1) Resumen ejecutivo (3-6 bullets)\n"
        "2) Situación económica (explicación en lenguaje llano)\n"
        "3) Alertas y evidencias (qué significa y qué revisar)\n"
        "4) Opciones (qué puede hacer) incluyendo AEAT/TGSS: planes de pago, aplazamientos, y si aplica exoneración\n"
        "5) Hoja de ruta (pasos 0-7 días, 7-15 días, 15-30 días, 1-3 meses)\n"
        "6) Base legal (citas disponibles; si no hay, decir 'no hay')\n\n"
        "REGLAS:\n"
        "- No inventes cifras, fechas ni artículos. Si no están en el contexto, di 'No hay evidencia suficiente...'\n"
        "- Si el deudor parece empresa, sé claro con exoneración (puede no aplicar) y dilo.\n"
        "- Usa un tono claro y práctico."
    )

    return build_llm_answer(question=question, context_text=context_text)

