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

import hashlib
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.alert import Alert as AlertORM
from app.models.alert_evidence import AlertEvidence as AlertEvidenceORM
from app.models.case import Case
from app.api.analysis_alerts import get_analysis_alerts
from app.services.alert_merge_policy import compute_fingerprint
from app.services.assistant_alert_voice import AlertDomain, EvidenceRef, Relevance, VoiceInput
from app.services.assistant_alert_voice_llm import PROMPT_VERSION as VOICE_PROMPT_VERSION, generate_voice_llm


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

    model_config = {"extra": "forbid"}


class AlertOut(BaseModel):
    alert_id: str
    case_id: str
    domain: str
    relevance: Literal["ALTA", "MEDIA", "BAJA"]
    title_human: str
    summary_human: str
    disclaimer_detail: str
    status: Literal["pendiente", "revisada", "descartada", "para_informe"]
    lawyer_note: str
    para_informe: bool
    changed_since_last_review: bool
    updated_by: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"extra": "forbid"}


class AlertDetailOut(AlertOut):
    evidences: list[AlertEvidenceOut] = Field(default_factory=list)
    source_alert_ids: list[str] = Field(default_factory=list)
    fingerprint: str
    rules_version: Optional[str] = None
    voice_prompt_version: Optional[str] = None

    model_config = {"extra": "forbid"}


class GenerateAlertsResponse(BaseModel):
    status: str = "ok"
    case_id: str
    generated_count: int

    model_config = {"extra": "forbid"}


class UpdateAlertRequest(BaseModel):
    status: Optional[Literal["pendiente", "revisada", "descartada", "para_informe"]] = None
    lawyer_note: Optional[str] = None
    para_informe: Optional[bool] = None
    updated_by: str = "abogado"

    model_config = {"extra": "forbid"}


def _infer_domain(desc: str, evidence_filenames: list[str]) -> str:
    blob = (desc or "").lower() + " " + " ".join(evidence_filenames).lower()
    if any(k in blob for k in ["tgss", "seguridad social", "apremio", "providencia", "rnt", "rlc"]):
        return "TGSS"
    if any(k in blob for k in ["extracto", "banc", "iban", "transfer", "comisión", "reintegro", "cajero"]):
        return "BANCO"
    if any(k in blob for k in ["factura", "iva", "472", "libro mayor", "sumas", "saldos", "contabilidad"]):
        return "CONTABILIDAD"
    if any(k in blob for k in ["vinculad", "grupo", "socio", "administrador", "entregables"]):
        return "VINCULADAS"
    return "DOCS"


def _score_like(desc: str, evidence_count: int, technical_type: str) -> int:
    base = {
        "SUSPICIOUS_PATTERN": 70,
        "TEMPORAL_INCONSISTENCY": 55,
        "INCONSISTENT_DATA": 50,
        "DUPLICATED_DATA": 35,
        "MISSING_DATA": 30,
    }.get(technical_type, 40)
    bonus = min(20, int(evidence_count) * 4)
    d = (desc or "").lower()
    if "tgss" in d or "apremio" in d or "providencia" in d:
        bonus += 6
    if "vinculad" in d or "grupo" in d:
        bonus += 6
    if "efectivo" in d or "cajero" in d or "reintegro" in d:
        bonus += 6
    if "iva" in d:
        bonus += 4
    return max(0, min(100, base + bonus))


def _relevance_from_score(score: int) -> str:
    if score >= 60:
        return "ALTA"
    if score >= 25:
        return "MEDIA"
    return "BAJA"


def _alert_id_from_case_and_source(case_id: str, source_alert_id: str) -> str:
    # Estable: 1 alerta despacho por alerta técnica (por ahora).
    raw = f"{case_id}|{source_alert_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _voice_input_from_analysis_alert(a: dict[str, Any]) -> VoiceInput:
    desc = str(a.get("description") or "")
    evidence = list(a.get("evidence") or [])
    filenames = [str(e.get("filename") or "") for e in evidence]
    domain_str = _infer_domain(desc, filenames)
    score = _score_like(desc, len(evidence), str(a.get("alert_type") or ""))
    relevance_str = _relevance_from_score(score)

    ev_refs = []
    for e in evidence[:2]:
        loc = e.get("location") or {}
        ev_refs.append(
            EvidenceRef(
                filename=str(e.get("filename") or ""),
                page_start=loc.get("page_start"),
                page_end=loc.get("page_end"),
                snippet=str(e.get("content") or "")[:240],
            )
        )

    # Checklist por dominio (mínimo; se puede enriquecer en FASE 5)
    if domain_str == "TGSS":
        to_clarify = [
            "RNT/RLC de los meses afectados (y justificantes de pago si existen).",
            "Certificado TGSS actualizado (deuda/estado).",
            "Soporte de aplazamiento/fraccionamiento si existe.",
            "Conciliación bancaria del periodo.",
        ]
    elif domain_str == "BANCO":
        to_clarify = [
            "Extractos completos del periodo (no solo resúmenes).",
            "Conciliación bancaria y explicación de conceptos genéricos.",
            "Contrato/soporte de los pagos (servicios, préstamos, etc.).",
        ]
    elif domain_str == "CONTABILIDAD":
        to_clarify = [
            "Factura + justificante + extracto bancario (conciliación).",
            "Soporte y asiento del IVA (si aplica).",
            "Confirmar si hubo rectificativa o pago posterior.",
        ]
    elif domain_str == "VINCULADAS":
        to_clarify = [
            "Contrato y entregables/soporte del servicio prestado.",
            "Criterio de precios y relación con el grupo.",
            "Conciliación bancaria de los pagos.",
        ]
    else:
        to_clarify = [
            "Confirmar si la documentación existe y, si existe, incorporarla al expediente.",
            "Aportar soporte adicional si este punto va a informe.",
        ]

    domain = AlertDomain(domain_str)
    relevance = Relevance(relevance_str)
    return VoiceInput(
        domain=domain,
        findings=[desc] if desc else [],
        evidences=ev_refs,
        to_clarify=to_clarify,
        temporal_window_note=None,
        relevance=relevance,
    )


@router_cases.get("", response_model=list[AlertOut])
def list_case_alerts(case_id: str, db: Session = Depends(get_db)) -> list[AlertOut]:
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado")

    rows = (
        db.query(AlertORM)
        .filter(AlertORM.case_id == case_id)
        .order_by(AlertORM.created_at.desc())
        .all()
    )

    out: list[AlertOut] = []
    for r in rows:
        out.append(
            AlertOut(
                alert_id=r.alert_id,
                case_id=r.case_id,
                domain=r.domain,
                relevance=r.relevance,  # type: ignore[arg-type]
                title_human=r.title_human,
                summary_human=r.summary_human,
                disclaimer_detail=r.disclaimer_detail or "",
                status=r.status,  # type: ignore[arg-type]
                lawyer_note=r.lawyer_note or "",
                para_informe=bool(r.para_informe),
                changed_since_last_review=bool(r.changed_since_last_review),
                updated_by=r.updated_by,
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

    # 1) Obtener alertas técnicas (fuente)
    tech_alerts = get_analysis_alerts(case_id=case_id, db=db)

    generated = 0
    for a in tech_alerts:
        source_id = str(a.alert_id)
        alert_id = _alert_id_from_case_and_source(case_id, source_id)

        evidence = list(a.evidence or [])
        filenames = [str(e.filename or "") for e in evidence]
        domain = _infer_domain(a.description, filenames)
        score = _score_like(a.description, len(evidence), a.alert_type.value)
        relevance = _relevance_from_score(score)

        # Fingerprint (estable): dominio + source + chunk_ids
        ev_parts: list[str] = []
        for ev in evidence:
            loc = ev.location
            ev_parts.append(str(ev.document_id or ""))
            ev_parts.append(str(ev.filename or ""))
            ev_parts.append(str(getattr(ev, "chunk_id", "") or ""))
            ev_parts.append(str(getattr(loc, "page_start", "") or ""))
            ev_parts.append(str(getattr(loc, "page_end", "") or ""))
        fp = compute_fingerprint(kind="alert_v1", key_parts=[domain, source_id, *ev_parts])

        # Voz (LLM+reglas con fallback) — NO inventa hechos; solo reescribe.
        voice_in = _voice_input_from_analysis_alert(
            {
                "alert_type": a.alert_type.value,
                "description": a.description,
                "evidence": [ev.model_dump() for ev in (a.evidence or [])],
            }
        )
        voice = generate_voice_llm(voice_in, strict_language=True)

        existing: Optional[AlertORM] = db.query(AlertORM).filter(AlertORM.alert_id == alert_id).first()
        if existing:
            # Merge editorial: NO machacar status/nota/para_informe/updated_by
            old_fp = existing.fingerprint
            old_status = existing.status
            old_note = existing.lawyer_note
            old_para = bool(existing.para_informe)
            old_updated_by = existing.updated_by

            existing.domain = domain
            existing.relevance = relevance
            existing.title_human = voice.title_human
            existing.summary_human = voice.summary_human
            existing.disclaimer_detail = voice.disclaimer_detail
            existing.fingerprint = fp
            existing.source_alert_ids = [source_id]
            existing.rules_version = "analysis_alerts_v1"
            existing.voice_prompt_version = VOICE_PROMPT_VERSION
            # Preservar editorial
            existing.status = old_status
            existing.lawyer_note = old_note
            existing.para_informe = old_para
            existing.updated_by = old_updated_by
            # changed_since_last_review si estaba revisada/para_informe y cambió fingerprint
            if old_fp and old_fp != fp and old_status in ("revisada", "para_informe"):
                existing.changed_since_last_review = True

            row = existing
        else:
            row = AlertORM(
                alert_id=alert_id,
                case_id=case_id,
                domain=domain,
                relevance=relevance,
                title_human=voice.title_human,
                summary_human=voice.summary_human,
                disclaimer_detail=voice.disclaimer_detail,
                fingerprint=fp,
                source_alert_ids=[source_id],
                status="pendiente",
                lawyer_note="",
                para_informe=False,
                changed_since_last_review=False,
                updated_by=None,
                rules_version="analysis_alerts_v1",
                voice_prompt_version=VOICE_PROMPT_VERSION,
            )
            db.add(row)
            db.flush()

        # Reescribir evidencias normalizadas (simple: delete+insert)
        db.query(AlertEvidenceORM).filter(AlertEvidenceORM.alert_id == row.alert_id).delete()
        for ev in evidence:
            loc = ev.location
            db.add(
                AlertEvidenceORM(
                    alert_id=row.alert_id,
                    document_id=ev.document_id,
                    filename=ev.filename,
                    chunk_id=ev.chunk_id,
                    page_start=getattr(loc, "page_start", None),
                    page_end=getattr(loc, "page_end", None),
                    start_char=getattr(loc, "start_char", None),
                    end_char=getattr(loc, "end_char", None),
                    snippet=(ev.content or "")[:400],
                )
            )

        generated += 1

    db.commit()
    return GenerateAlertsResponse(case_id=case_id, generated_count=generated)


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
        )
        for e in ev_rows
    ]

    return AlertDetailOut(
        alert_id=row.alert_id,
        case_id=row.case_id,
        domain=row.domain,
        relevance=row.relevance,  # type: ignore[arg-type]
        title_human=row.title_human,
        summary_human=row.summary_human,
        disclaimer_detail=row.disclaimer_detail or "",
        status=row.status,  # type: ignore[arg-type]
        lawyer_note=row.lawyer_note or "",
        para_informe=bool(row.para_informe),
        changed_since_last_review=bool(row.changed_since_last_review),
        updated_by=row.updated_by,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
        evidences=evidences,
        source_alert_ids=list(row.source_alert_ids or []),
        fingerprint=row.fingerprint,
        rules_version=row.rules_version,
        voice_prompt_version=row.voice_prompt_version,
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

