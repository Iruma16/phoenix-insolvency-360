"""
Indexado de informes en el RAG del caso.

Diseño:
- NO se mezcla con la colección "chunks" porque el retrieval actual asume DocumentChunk en BD.
- Se usa una colección separada: "reports" dentro del mismo Chroma PersistentClient (misma versión ACTIVE).
- Se provee un endpoint dedicado para consultar informes.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

import chromadb
from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.variables import EMBEDDING_MODEL
from app.models.economic_report import EconomicReportBundle
from app.services.embeddings_pipeline import build_embeddings_for_case
from app.services.vectorstore_versioning import get_active_version_path


def _get_openai_client() -> Optional[OpenAI]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def _get_reports_collection(case_id: str):
    active = get_active_version_path(case_id)
    if not active:
        raise RuntimeError(
            f"No existe vectorstore ACTIVE para case_id={case_id}. "
            "Genera embeddings antes o habilita autogeneración."
        )
    index_path = active / "index"
    client = chromadb.PersistentClient(path=str(index_path))
    return client.get_or_create_collection(name="reports", metadata={"case_id": case_id, "type": "reports"})


def _embed(openai_client: OpenAI, texts: list[str]) -> list[list[float]]:
    resp = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [x.embedding for x in resp.data]


def index_economic_report_bundle(
    db: Session,
    *,
    bundle: EconomicReportBundle,
    ensure_case_embeddings: bool = True,
) -> dict[str, Any]:
    """
    Indexa el informe (bundle + narrativa si existe) en el vectorstore del caso (colección "reports").

    Returns:
        dict con status y métricas.
    """
    case_id = bundle.case_id

    # Asegurar ACTIVE (obligatorio en Política A si ensure_case_embeddings=True)
    if ensure_case_embeddings and not get_active_version_path(case_id):
        openai_client = _get_openai_client()
        if not openai_client:
            raise RuntimeError("OPENAI_API_KEY no definida (embeddings obligatorios).")
        build_embeddings_for_case(db=db, case_id=case_id, openai_client=openai_client)

    openai_client = _get_openai_client()
    if not openai_client:
        raise RuntimeError("OPENAI_API_KEY no definida (embeddings obligatorios).")

    collection = _get_reports_collection(case_id)

    def _cap(s: str, max_chars: int = 6000) -> str:
        s = (s or "").strip()
        return s if len(s) <= max_chars else s[: max_chars - 50] + "\n...[TRUNCADO]..."

    # Construir secciones indexables (COMPACTAS) para no exceder el límite del modelo de embeddings
    fin = bundle.financial_analysis

    client_summary_txt = _cap(bundle.client_summary.model_dump_json(ensure_ascii=False), 3000)

    ratios_txt = []
    for r in (fin.ratios or [])[:8]:
        val = "N/A" if r.value is None else f"{r.value:.2f}"
        ratios_txt.append(f"- {r.name}: {val} ({r.status.value}) — {r.interpretation}")

    insolvency_txt = ""
    if fin.insolvency:
        insolvency_txt = (
            f"{fin.insolvency.overall_assessment}\n"
            f"Confianza: {fin.insolvency.confidence_level.value}\n"
            f"Impago: {len(fin.insolvency.signals_impago or [])} | "
            f"Exigibilidad: {len(fin.insolvency.signals_exigibilidad or [])} | "
            f"Contable: {len(fin.insolvency.signals_contables or [])}\n"
        )
        for s in (fin.insolvency.signals_impago or [])[:2]:
            insolvency_txt += f"- (Impago) {s.description}\n"
        for s in (fin.insolvency.signals_contables or [])[:2]:
            insolvency_txt += f"- (Contable) {s.description}\n"

    financial_txt = _cap(
        "ANÁLISIS FINANCIERO (resumen):\n"
        + "\n".join(ratios_txt)
        + ("\n\nINSOLVENCIA:\n" + insolvency_txt if insolvency_txt else "\n\nINSOLVENCIA: N/A\n"),
        6000,
    )

    alerts_txt = "ALERTAS:\n" + "\n".join(
        [
            f"- {a.alert_type.value if hasattr(a.alert_type,'value') else str(a.alert_type)}: {a.description}"
            for a in (bundle.alerts or [])[:20]
        ]
    )
    alerts_txt = _cap(alerts_txt, 6000)

    roadmap_txt = "HOJA DE RUTA:\n" + "\n".join(
        [f"- [{r.phase}] {r.step} (prio={r.priority}, estado={r.status})" for r in (bundle.roadmap or [])[:15]]
    )
    roadmap_txt = _cap(roadmap_txt, 6000)

    legal_txt = "BASE LEGAL (citas):\n" + "\n".join(
        [
            f"- {c.citation}"
            for _, cs in (bundle.legal_citations or {}).items()
            for c in (cs or [])[:3]
        ][:20]
    )
    legal_txt = _cap(legal_txt, 6000)

    narrative_txt = _cap(bundle.narrative_md or "", 6000) if bundle.narrative_md else ""

    sections: list[tuple[str, str]] = [
        ("client_summary", client_summary_txt),
        ("financial_summary", financial_txt),
        ("alerts", alerts_txt),
        ("roadmap", roadmap_txt),
        ("legal_citations", legal_txt),
    ]
    if narrative_txt:
        sections.append(("narrative_md", narrative_txt))

    ids = []
    docs = []
    metas = []
    for section_name, text in sections:
        if not text or not str(text).strip():
            continue
        # Sin duplicar: sobrescribir siempre la versión ACTIVE del informe en RAG
        ids.append(f"eco_report:ACTIVE:{section_name}")
        docs.append(str(text))
        metas.append(
            {
                "case_id": case_id,
                "report_id": bundle.report_id,  # se actualiza cada generación
                "section": section_name,
                "generated_at": bundle.generated_at.isoformat(),
                "schema_version": bundle.schema_version,
                "type": "economic_report",
            }
        )

    if not ids:
        raise RuntimeError("No hay contenido indexable (unexpected).")

    vectors = _embed(openai_client, docs)
    collection.upsert(ids=ids, embeddings=vectors, documents=docs, metadatas=metas)

    logger.info(
        f"[REPORT_INDEX] Indexed economic report: case_id={case_id} report_id={bundle.report_id} sections={len(ids)}"
    )

    return {
        "status": "ok",
        "case_id": case_id,
        "report_id": bundle.report_id,
        "sections_indexed": len(ids),
        "indexed_at": datetime.utcnow().isoformat(),
    }


def query_reports_rag(
    *,
    case_id: str,
    question: str,
    top_k: int = 6,
) -> dict[str, Any]:
    """
    Consulta semántica sobre los informes indexados del caso.
    Devuelve (answer) vacío: esta función solo recupera contexto y fuentes (sin LLM).
    """
    openai_client = _get_openai_client()
    if not openai_client:
        return {"status": "NO_EMBEDDINGS", "context_text": "", "sources": []}

    collection = _get_reports_collection(case_id)
    if collection.count() == 0:
        return {"status": "NO_REPORTS", "context_text": "", "sources": []}

    qv = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=[question]).data[0].embedding
    res = collection.query(query_embeddings=[qv], n_results=top_k, include=["documents", "metadatas", "distances"])

    docs_found = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    distances = res.get("distances", [[]])[0]

    sources = []
    blocks = []
    for text, meta, dist in zip(docs_found, metas, distances):
        if not text or not meta:
            continue
        sources.append(
            {
                "report_id": meta.get("report_id"),
                "section": meta.get("section"),
                "generated_at": meta.get("generated_at"),
                "distance": float(dist),
            }
        )
        blocks.append(f"[REPORT {meta.get('report_id')} | {meta.get('section')}]\n{text}")

    return {"status": "OK" if blocks else "NO_RELEVANT_CONTEXT", "context_text": "\n\n".join(blocks), "sources": sources}

