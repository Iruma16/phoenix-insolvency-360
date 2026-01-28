"""
Informe de Situación Económica (para cliente) - Opción A (modo estricto).

POLÍTICA A (estricta):
- El informe SIEMPRE usa LLM + RAG (no es opcional)
- SI OpenAI falla o no está configurado -> error (no hay informe)
- SI falla indexado -> error (no hay informe)
- No se duplica en RAG: se sobrescribe la versión ACTIVE

Endpoints:
- POST /api/cases/{case_id}/economic-report/generate -> Generar + indexar (sin descargar)
- GET  /api/cases/{case_id}/economic-report/pdf      -> Descargar PDF YA generado (no regenera)
- POST /api/cases/{case_id}/economic-report/email    -> Enviar PDF YA generado (no regenera)
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.financial_analysis import get_financial_analysis
from app.core.config import settings
from app.core.auth import User, get_current_user
from app.core.database import get_db
from app.models.case import Case
from app.models.economic_report import EconomicReportBundle
from app.reports.pdf.economic_pdf import generate_economic_report_pdf
from app.services.economic_report_builder import build_economic_report_bundle
from app.services.economic_report_narrative import build_economic_report_narrative_md
from app.services.email_sender import send_email_with_attachment
from app.services.report_indexing import index_economic_report_bundle

router = APIRouter(prefix="/cases/{case_id}", tags=["economic-report"])

REPORTS_BASE_DIR = Path(__file__).parent.parent.parent / "reports"


def _ensure_reports_dir(case_id: str) -> Path:
    case_dir = REPORTS_BASE_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


def _active_pdf_path(case_id: str) -> Path:
    return _ensure_reports_dir(case_id) / "economic_report_ACTIVE.pdf"


def _active_json_path(case_id: str) -> Path:
    return _ensure_reports_dir(case_id) / "economic_report_ACTIVE.json"


class EmailReportRequest(BaseModel):
    to_email: str = Field(..., min_length=5)


def _require_llm_strict() -> None:
    if not settings.llm_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM obligatorio para generar el informe (LLM_ENABLED=1 y OPENAI_API_KEY requerida).",
        )


def _generate_bundle_strict(
    *,
    case_id: str,
    request: Request,
    db: Session,
    current_user: User,
) -> EconomicReportBundle:
    _require_llm_strict()

    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado"
        )

    financial = get_financial_analysis(
        case_id=case_id, request=request, db=db, current_user=current_user
    )

    bundle = build_economic_report_bundle(db, case_id=case_id, financial_analysis=financial)

    # LLM SIEMPRE (Política A)
    try:
        bundle.narrative_md = build_economic_report_narrative_md(db, bundle=bundle)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error generando narrativa LLM (obligatorio): {e}",
        )

    return bundle


@router.post(
    "/economic-report/generate",
    summary="Generar informe económico (sin descarga) e indexar en RAG",
)
def generate_economic_report(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    bundle = _generate_bundle_strict(case_id=case_id, request=request, db=db, current_user=current_user)

    try:
        index_economic_report_bundle(db, bundle=bundle, ensure_case_embeddings=True)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error indexando informe (obligatorio): {e}",
        )

    # Persistir JSON + PDF (ACTIVE) para descarga posterior SIN regenerar
    try:
        out_dir = _ensure_reports_dir(case_id)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        # Auditoría (timestamp)
        json_path = out_dir / f"economic_report_{bundle.report_id}_{ts}.json"
        json_payload = bundle.model_dump_json(indent=2, ensure_ascii=False)
        json_path.write_text(json_payload, encoding="utf-8")

        # ACTIVE (overwrite)
        _active_json_path(case_id).write_text(json_payload, encoding="utf-8")

        pdf_bytes = generate_economic_report_pdf(bundle)
        # Auditoría (timestamp)
        (out_dir / f"economic_report_{bundle.report_id}_{ts}.pdf").write_bytes(pdf_bytes)
        # ACTIVE (overwrite)
        _active_pdf_path(case_id).write_bytes(pdf_bytes)
    except Exception:
        pass

    return {"status": "ok", "case_id": case_id, "report_id": bundle.report_id}


@router.get(
    "/economic-report/pdf",
    summary="Descargar informe de situación económica en PDF (ya generado, no regenera)",
)
def download_economic_report_pdf(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    # Mantener deps de auth/DB aunque el endpoint no regenere.
    _ = request
    _ = db
    _ = current_user

    pdf_path = _active_pdf_path(case_id)
    if not pdf_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay un informe generado. Ejecuta primero /economic-report/generate.",
        )

    pdf_bytes = pdf_path.read_bytes()

    filename = f"informe_situacion_economica_{case_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.post(
    "/economic-report/email",
    summary="Enviar informe económico por email (Gmail SMTP)",
)
def email_economic_report(
    case_id: str,
    payload: EmailReportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Mantener deps de auth/DB aunque el endpoint no regenere.
    _ = request
    _ = db
    _ = current_user

    # Enviar PDF YA generado (no regenera)
    pdf_path = _active_pdf_path(case_id)
    if not pdf_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay un informe generado. Ejecuta primero /economic-report/generate.",
        )
    pdf_bytes = pdf_path.read_bytes()

    # Asunto básico (sin necesidad de regenerar bundle)
    filename = f"informe_situacion_economica_{case_id}.pdf"
    subject = f"Informe de situación económica — Caso {case_id}"
    body = (
        "Adjunto encontrarás el informe de situación económica.\n\n"
        "Aviso: informe automatizado (requiere revisión profesional).\n"
    )

    send_email_with_attachment(
        to_email=payload.to_email,
        subject=subject,
        body_text=body,
        attachment_filename=filename,
        attachment_bytes=pdf_bytes,
    )

    return {"status": "ok", "to": payload.to_email, "filename": filename}

