"""
ALERTAS DE DESPACHO (persistidas) — FASE 4

Endpoints:
- GET  /api/cases/{case_id}/alerts
- POST /api/cases/{case_id}/alerts/generate   (bajo demanda: botón Reanalizar)
- GET  /api/alerts/{alert_id}
- PATCH /api/alerts/{alert_id}

Convivencia:
- Mantiene /analysis/alerts como salida técnica (no se toca).
- /alerts se alimenta de /analysis/alerts + voz (LLM+reglas con fallback).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logger import logger
from app.models.alert import Alert as AlertORM
from app.models.alert_evidence import AlertEvidence as AlertEvidenceORM
from app.models.case import Case
from app.services.alerts_exporter import export_validated_alerts_to_markdown
from app.services.alerts_generator import generate_persisted_alerts_for_case


router_cases = APIRouter(prefix="/cases/{case_id}/alerts", tags=["alerts"])
router_alerts = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertEvidenceOut(BaseModel):
    evidence_id: str
    document_id: Optional[str] = None
    filename: str
    chunk_id: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    snippet: str
    signal: Optional[str] = None

    model_config = {"extra": "forbid"}


class AlertOut(BaseModel):
    alert_id: str
    case_id: str
    domain: str
    relevance: Literal["ALTA", "MEDIA", "BAJA"]
    score: Optional[int] = None
    title_human: str
    summary_human: str
    disclaimer_detail: str
    status: Literal["pendiente", "revisada", "descartada", "para_informe"]
    lawyer_note: str
    para_informe: bool
    changed_since_last_review: bool
    updated_by: Optional[str] = None
    rules_version: Optional[str] = None
    voice_prompt_version: Optional[str] = None
    generator_version: Optional[str] = None
    dataset_version: Optional[str] = None
    generated_at: Optional[str] = None
    generated_by: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"extra": "forbid"}


class AlertDetailOut(AlertOut):
    evidences: list[AlertEvidenceOut] = Field(default_factory=list)
    source_alert_ids: list[str] = Field(default_factory=list)
    fingerprint: str
    to_clarify: list[dict] = Field(default_factory=list)
    recommended_actions: list[dict] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class GenerateAlertsResponse(BaseModel):
    status: str = "ok"
    case_id: str
    generated_count: int

    model_config = {"extra": "forbid"}


class ExportAlertsResponse(BaseModel):
    status: str = "ok"
    case_id: str
    generated_at: str
    included_alerts: int
    markdown_filename: str
    download_url: str
    evidence_registry: list[dict] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class UpdateAlertRequest(BaseModel):
    status: Optional[Literal["pendiente", "revisada", "descartada", "para_informe"]] = None
    lawyer_note: Optional[str] = None
    para_informe: Optional[bool] = None
    updated_by: str = "abogado"

    model_config = {"extra": "forbid"}

@router_cases.get("", response_model=list[AlertOut])
def list_case_alerts(case_id: str, db: Session = Depends(get_db)) -> list[AlertOut]:
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado")

    try:
        rows = (
            db.query(AlertORM)
            .filter(AlertORM.case_id == case_id)
            .order_by(AlertORM.created_at.desc())
            .all()
        )
    except OperationalError as e:
        # Caso típico: DB sin migrar aún (no existe tabla `alerts`)
        logger.error(
            "Failed to query alerts table (DB likely not initialized)",
            case_id=case_id,
            action="alerts_list_db_missing",
            error=e,
        )
        return []

    out: list[AlertOut] = []
    for r in rows:
        out.append(
            AlertOut(
                alert_id=r.alert_id,
                case_id=r.case_id,
                domain=r.domain,
                relevance=r.relevance,  # type: ignore[arg-type]
                score=r.score,
                title_human=r.title_human,
                summary_human=r.summary_human,
                disclaimer_detail=r.disclaimer_detail or "",
                status=r.status,  # type: ignore[arg-type]
                lawyer_note=r.lawyer_note or "",
                para_informe=bool(r.para_informe),
                changed_since_last_review=bool(r.changed_since_last_review),
                updated_by=r.updated_by,
                rules_version=r.rules_version,
                voice_prompt_version=r.voice_prompt_version,
                generator_version=r.generator_version,
                dataset_version=r.dataset_version,
                generated_at=(r.generated_at.isoformat() if getattr(r, "generated_at", None) else None),
                generated_by=r.generated_by,
                created_at=r.created_at.isoformat(),
                updated_at=r.updated_at.isoformat(),
            )
        )
    return out


@router_cases.post("/generate", response_model=GenerateAlertsResponse)
def generate_case_alerts(case_id: str, db: Session = Depends(get_db)) -> GenerateAlertsResponse:
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado")
    try:
        generated = generate_persisted_alerts_for_case(case_id=case_id, db=db)
        db.commit()
        return GenerateAlertsResponse(case_id=case_id, generated_count=generated)
    except Exception as e:
        db.rollback()
        logger.error(
            "Error generating alerts",
            action="alerts_generate_failed",
            case_id=case_id,
            error=e,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al regenerar alertas: {type(e).__name__}: {str(e)}",
        )


@router_cases.get("/export", response_model=ExportAlertsResponse)
def export_case_alerts(case_id: str, db: Session = Depends(get_db)) -> ExportAlertsResponse:
    """
    Export a informe (solo alertas validadas: revisada/para_informe).

    Genera un Markdown en reports/{case_id}/alerts_export_validated.md y devuelve
    además un registro de evidencias incluidas (tangible/trazable).
    """
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado")

    res = export_validated_alerts_to_markdown(case_id=case_id, db=db)

    return ExportAlertsResponse(
        case_id=case_id,
        generated_at=res.generated_at,
        included_alerts=int(res.included_alerts),
        markdown_filename=res.markdown_filename,
        download_url=f"/reports/download/{case_id}/{res.markdown_filename}",
        evidence_registry=list(res.evidence_registry or []),
    )


@router_alerts.get("/{alert_id}", response_model=AlertDetailOut)
def get_alert_detail(alert_id: str, db: Session = Depends(get_db)) -> AlertDetailOut:
    row = db.query(AlertORM).filter(AlertORM.alert_id == alert_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada")

    ev_rows = (
        db.query(AlertEvidenceORM)
        .filter(AlertEvidenceORM.alert_id == alert_id)
        .order_by(AlertEvidenceORM.evidence_id.asc())
        .all()
    )
    evidences = [
        AlertEvidenceOut(
            evidence_id=e.evidence_id,
            document_id=e.document_id,
            filename=e.filename,
            chunk_id=e.chunk_id,
            page_start=e.page_start,
            page_end=e.page_end,
            start_char=e.start_char,
            end_char=e.end_char,
            snippet=e.snippet,
            signal=getattr(e, "signal", None),
        )
        for e in ev_rows
    ]

    return AlertDetailOut(
        alert_id=row.alert_id,
        case_id=row.case_id,
        domain=row.domain,
        relevance=row.relevance,  # type: ignore[arg-type]
        score=row.score,
        title_human=row.title_human,
        summary_human=row.summary_human,
        disclaimer_detail=row.disclaimer_detail or "",
        status=row.status,  # type: ignore[arg-type]
        lawyer_note=row.lawyer_note or "",
        para_informe=bool(row.para_informe),
        changed_since_last_review=bool(row.changed_since_last_review),
        updated_by=row.updated_by,
        rules_version=row.rules_version,
        voice_prompt_version=row.voice_prompt_version,
        generator_version=row.generator_version,
        dataset_version=row.dataset_version,
        generated_at=(row.generated_at.isoformat() if getattr(row, "generated_at", None) else None),
        generated_by=row.generated_by,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
        evidences=evidences,
        source_alert_ids=list(row.source_alert_ids or []),
        fingerprint=row.fingerprint,
        to_clarify=list(row.to_clarify or []),
        recommended_actions=list(row.recommended_actions or []),
    )


@router_alerts.patch("/{alert_id}")
def update_alert(alert_id: str, payload: UpdateAlertRequest, db: Session = Depends(get_db)) -> dict:
    row = db.query(AlertORM).filter(AlertORM.alert_id == alert_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada")

    if payload.status is not None:
        row.status = payload.status
    if payload.lawyer_note is not None:
        row.lawyer_note = payload.lawyer_note
    if payload.para_informe is not None:
        row.para_informe = bool(payload.para_informe)
        if row.para_informe and row.status != "descartada":
            row.status = "para_informe"

    row.updated_by = payload.updated_by or "abogado"
    row.updated_at = datetime.utcnow()

    db.commit()
    return {"status": "ok", "alert_id": alert_id}

