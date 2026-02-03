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
    if bundle.narrative_contract is not None:
        return bundle.narrative_contract.model_dump_json(ensure_ascii=False)

    # Fallback (compatibilidad): si no existe contrato, usar payload mínimo
    fin = bundle.financial_analysis
    payload = {
        "case": {
            "case_id": bundle.case_id,
            "case_name": bundle.case_name,
            "debtor_type": bundle.debtor_type,
        },
        "client_summary": bundle.client_summary.model_dump(),
        "documents": {
            "presented_count": len(bundle.documents_presented or []),
            "missing": list(bundle.documents_missing or []),
            "recommended": list(bundle.documents_recommended or []),
        },
        "financial": {
            "analysis_date": fin.analysis_date.isoformat(),
            "ratios": [r.model_dump() for r in (fin.ratios or [])][:10],
            "insolvency": fin.insolvency.model_dump() if fin.insolvency else None,
            "credit_classification": [c.model_dump() for c in (fin.credit_classification or [])][
                :20
            ],
            "total_debt": fin.total_debt,
        },
        "legal_citations": {
            k: [c.model_dump() for c in v[:3]] for k, v in (bundle.legal_citations or {}).items()
        },
        "lawyer_signature": bundle.lawyer_signature.model_dump()
        if bundle.lawyer_signature
        else None,
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def build_economic_report_narrative_md(db: Session, *, bundle: EconomicReportBundle) -> str:
    """
    Genera un Markdown narrativo con LLM (redacción).

    Regla: el LLM solo redacta; la base factual y legal proviene del bundle.
    """
    # Recuperar contexto del caso (chunks) para citar evidencias
    query = (
        "Situación económica: insolvencia, embargos, deudas con Hacienda o Seguridad Social, "
        "facturas vencidas, balance, pérdidas y pagos. Extraer solo lo que esté explícito."
    )
    case_context = query_case_rag(db=db, case_id=bundle.case_id, query=query) or ""

    context_text = (
        "CONTRATO_NARRATIVO_JSON (fuente principal; no inventar fuera de este JSON):\n"
        + _bundle_for_llm(bundle)
        + "\n\n"
        + "FRAGMENTOS_LITERALES_DEL_EXPEDIENTE (solo para reforzar comprensión; no introducir hechos nuevos):\n"
        + case_context[:20000]
    )

    question = (
        "Eres una abogada concursalista en España. Redactas un informe para un cliente no experto.\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "1) Usa SOLO los hechos y artículos que aparecen en la ENTRADA. No inventes datos, fechas, importes, ni artículos.\n"
        '2) Si falta información relevante escribe EXACTAMENTE: "No consta en la documentación aportada".\n'
        "3) No menciones IA, RAG, LLM, modelos, embeddings, ni automatización.\n"
        '4) Cita la base legal indicando "TRLC art. X" únicamente si el artículo aparece en la lista proporcionada.\n'
        '5) No hagas acusaciones de delito. Si hay indicios, usa lenguaje condicional: "podrían apreciarse indicios".\n'
        "6) Cuando uses cifras, copia el valor exactamente tal como aparece en la ENTRADA (no redondees ni estimes).\n\n"
        "FORMATO:\n"
        "- Título\n"
        "- Resumen ejecutivo con línea temporal (máx. 25 líneas)\n"
        "- Inventario documental (aportados / faltantes / recomendados)\n"
        "- Situación económica y ratios (con interpretación)\n"
        "- Señales de insolvencia (solo detectadas)\n"
        "- Alertas del expediente\n"
        '- Opciones legales y recomendación (si no se puede concluir: "No consta...")\n'
        "- Pasos a seguir (cliente / abogada / administración concursal)\n"
        "- Firma (Nombre + Nº colegiado + fecha)\n\n"
        "ENTRADA:\n"
        "- Hechos del caso (JSON)\n"
        "- Artículos aplicables (lista con extracto)\n"
    )

    return build_llm_answer(question=question, context_text=context_text)
