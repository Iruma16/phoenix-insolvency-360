"""
ALERTAS (voz despacho) — Persistencia + regeneración bajo demanda (Opción B).

Principios:
- No se recalcula en cada render: se persiste un bundle por caso.
- Se regenera solo cuando el usuario pulsa "Reanalizar" (endpoint generate).
- Si entran documentos nuevos, el status marca "dirty" (sin auto-regenerar).
- Se preserva trabajo del abogado (status/nota/para_informe) entre regeneraciones.

Nota:
- Sin migraciones/BD nueva: persistencia en disco, igual que economic_report.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.case import Case
from app.models.document import Document
from app.models.analysis_alert import AnalysisAlert
from app.models.document_chunk import DocumentChunk
from app.api.analysis_alerts import get_analysis_alerts
from app.services.alert_merge_policy import compute_fingerprint
from app.services.assistant_alert_voice import AlertDomain, EvidenceRef, Relevance, VoiceInput
from app.services.assistant_alert_voice_llm import PROMPT_VERSION as VOICE_PROMPT_VERSION, generate_voice_llm


router = APIRouter(prefix="/cases/{case_id}/alerts-voice", tags=["alerts-voice"])

REPORTS_BASE_DIR = Path(__file__).parent.parent.parent / "reports"
STATE_FILENAME = "alerts_voice_STATE.json"
BUNDLE_FILENAME = "alerts_voice_ACTIVE.json"


def _ensure_case_dir(case_id: str) -> Path:
    p = REPORTS_BASE_DIR / case_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _state_path(case_id: str) -> Path:
    return _ensure_case_dir(case_id) / STATE_FILENAME


def _bundle_path(case_id: str) -> Path:
    return _ensure_case_dir(case_id) / BUNDLE_FILENAME


class AlertVoiceCardState(BaseModel):
    status: Literal["pendiente", "revisada", "descartada", "para_informe"] = "pendiente"
    lawyer_note: str = ""
    para_informe: bool = False
    updated_at: Optional[str] = None  # ISO
    updated_by: str = "abogado"
    changed_since_last_review: bool = False

    class Config:
        extra = "forbid"


class AlertsVoiceState(BaseModel):
    case_id: str
    generated_at: Optional[str] = None  # ISO
    dirty_since_last_generation: bool = True
    overrides_version: int = 0
    cards: dict[str, AlertVoiceCardState] = Field(default_factory=dict)  # key=card_id
    last_docs_uploaded_at: Optional[str] = None  # ISO snapshot

    class Config:
        extra = "forbid"


class EvidenceOut(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    location: dict
    content: str

    class Config:
        extra = "forbid"


class AlertVoiceCard(BaseModel):
    card_id: str
    source_alert_id: str
    domain: str
    relevance: str
    title_human: str
    summary_human: str
    disclaimer_detail: str
    to_clarify: list[str] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)  # lista de AlertEvidence (dict) para UI
    fingerprint: str
    created_at: str  # ISO

    class Config:
        extra = "forbid"


class AlertsVoiceBundle(BaseModel):
    case_id: str
    generated_at: str  # ISO
    schema_version: str = "1.0.0"
    voice_prompt_version: str = VOICE_PROMPT_VERSION
    cards: list[AlertVoiceCard] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class AlertsVoiceStatusResponse(BaseModel):
    case_id: str
    has_generated: bool
    generated_at: Optional[str] = None
    dirty_since_last_generation: bool = True
    overrides_version: int = 0
    documents_newer_than_generation: bool = False
    last_docs_uploaded_at: Optional[str] = None

    class Config:
        extra = "forbid"


class UpdateCardRequest(BaseModel):
    status: Optional[Literal["pendiente", "revisada", "descartada", "para_informe"]] = None
    lawyer_note: Optional[str] = None
    para_informe: Optional[bool] = None
    updated_by: str = "abogado"

    class Config:
        extra = "forbid"


def _load_state(case_id: str) -> AlertsVoiceState:
    p = _state_path(case_id)
    if not p.exists():
        return AlertsVoiceState(case_id=case_id)
    try:
        return AlertsVoiceState.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return AlertsVoiceState(case_id=case_id)


def _save_state(case_id: str, state_obj: AlertsVoiceState) -> None:
    p = _state_path(case_id)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(state_obj.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _save_bundle(case_id: str, bundle: AlertsVoiceBundle) -> None:
    p = _bundle_path(case_id)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(bundle.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _load_bundle(case_id: str) -> Optional[AlertsVoiceBundle]:
    p = _bundle_path(case_id)
    if not p.exists():
        return None
    try:
        return AlertsVoiceBundle.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _infer_domain(alert: AnalysisAlert) -> AlertDomain:
    text = (alert.description or "").lower()
    fn_text = " ".join([(e.filename or "") for e in (alert.evidence or [])]).lower()
    blob = text + " " + fn_text
    if any(k in blob for k in ["tgss", "seguridad social", "apremio", "providencia", "rnt", "rlc"]):
        return AlertDomain.TGSS
    if any(k in blob for k in ["extracto", "banc", "iban", "transfer", "comisión", "reintegro", "cajero"]):
        return AlertDomain.BANCO
    if any(k in blob for k in ["factura", "iva", "472", "libro mayor", "sumas", "saldos", "contabilidad"]):
        return AlertDomain.CONTABILIDAD
    if any(k in blob for k in ["vinculad", "grupo", "socio", "administrador", "entregables"]):
        return AlertDomain.VINCULADAS
    return AlertDomain.DOCS


def _score_like(alert: AnalysisAlert) -> int:
    # Replica conservadora del scoring interno (no expuesto) para elegir relevancia.
    base = {
        "SUSPICIOUS_PATTERN": 70,
        "TEMPORAL_INCONSISTENCY": 55,
        "INCONSISTENT_DATA": 50,
        "DUPLICATED_DATA": 35,
        "MISSING_DATA": 30,
    }.get(alert.alert_type.value, 40)
    bonus = min(20, len(alert.evidence or []) * 4)
    d = (alert.description or "").lower()
    if "tgss" in d or "apremio" in d or "providencia" in d:
        bonus += 6
    if "vinculad" in d or "grupo" in d:
        bonus += 6
    if "efectivo" in d or "cajero" in d or "reintegro" in d:
        bonus += 6
    if "iva" in d:
        bonus += 4
    return max(0, min(100, base + bonus))


def _relevance_from_score(score: int) -> Relevance:
    if score >= 60:
        return Relevance.ALTA
    if score >= 25:
        return Relevance.MEDIA
    return Relevance.BAJA


def _findings_from_technical_description(desc: str) -> list[str]:
    """
    Convertir description técnica en findings no-robóticos (sin 'se detecta').
    """
    d = (desc or "").strip()
    if not d:
        return []
    # Reescrituras mínimas
    d = re.sub(r"^Detectad[oa]s?\s+", "aparecen ", d, flags=re.IGNORECASE)
    d = re.sub(r"^Duplicidad rara:\s+", "hay varias copias del mismo archivo; ", d, flags=re.IGNORECASE)
    d = d.replace("Señal de manipulación/calidad:", "calidad de extracción a revisar:")
    # Evitar “puede indicar” categórico
    d = d.replace("Puede indicar", "Conviene revisar si esto responde a")
    return [d]


def _default_checklist(domain: AlertDomain) -> list[str]:
    if domain == AlertDomain.TGSS:
        return [
            "RNT/RLC de los meses afectados (y justificantes de pago si existen).",
            "Certificado TGSS actualizado (deuda/estado).",
            "Soporte de aplazamiento/fraccionamiento si existe.",
            "Conciliación bancaria del periodo.",
        ]
    if domain == AlertDomain.BANCO:
        return [
            "Extractos completos del periodo (no solo resúmenes).",
            "Conciliación bancaria y explicación de conceptos genéricos.",
            "Contrato/soporte de los pagos (servicios, préstamos, etc.).",
        ]
    if domain == AlertDomain.CONTABILIDAD:
        return [
            "Factura + justificante + extracto bancario (conciliación).",
            "Soporte y asiento del IVA (si aplica).",
            "Confirmar si hubo rectificativa o pago posterior.",
        ]
    if domain == AlertDomain.VINCULADAS:
        return [
            "Contrato y entregables/soporte del servicio prestado.",
            "Criterio de precios y relación con el grupo.",
            "Conciliación bancaria de los pagos.",
        ]
    return [
        "Confirmar si la documentación existe y, si existe, incorporarla al expediente.",
        "Aportar soporte adicional si este punto va a informe.",
    ]


def _voice_input_from_alert(alert: AnalysisAlert) -> VoiceInput:
    domain = _infer_domain(alert)
    score = _score_like(alert)
    relevance = _relevance_from_score(score)

    evidences = []
    for ev in (alert.evidence or [])[:2]:
        loc = ev.location or {}
        evidences.append(
            EvidenceRef(
                filename=ev.filename,
                page_start=loc.page_start,
                page_end=loc.page_end,
                snippet=(ev.content or "")[:240],
            )
        )

    return VoiceInput(
        domain=domain,
        findings=_findings_from_technical_description(alert.description),
        evidences=evidences,
        to_clarify=_default_checklist(domain),
        temporal_window_note=None,
        relevance=relevance,
    )


@router.get("/status", response_model=AlertsVoiceStatusResponse)
def get_alerts_voice_status(case_id: str, db: Session = Depends(get_db)) -> AlertsVoiceStatusResponse:
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado")

    state_obj = _load_state(case_id)
    bundle = _load_bundle(case_id)
    has_generated = bool(bundle is not None)

    # Detectar si hay documentos nuevos desde la última generación (sin auto-regenerar)
    last_doc_dt = (
        db.query(func.max(Document.uploaded_at))
        .filter(Document.case_id == case_id, Document.deleted_at.is_(None))
        .scalar()
    )
    last_docs_uploaded_at = last_doc_dt.isoformat() if last_doc_dt else None

    documents_newer = False
    if bundle and last_doc_dt:
        try:
            gen_dt = datetime.fromisoformat(bundle.generated_at.replace("Z", "+00:00"))
            # uploaded_at puede ser tz-aware; normalizamos a naive UTC si hace falta
            documents_newer = last_doc_dt > gen_dt  # type: ignore[operator]
        except Exception:
            documents_newer = False

    dirty = bool(state_obj.dirty_since_last_generation or documents_newer)

    return AlertsVoiceStatusResponse(
        case_id=case_id,
        has_generated=has_generated,
        generated_at=(bundle.generated_at if bundle else state_obj.generated_at),
        dirty_since_last_generation=dirty,
        overrides_version=int(state_obj.overrides_version or 0),
        documents_newer_than_generation=bool(documents_newer),
        last_docs_uploaded_at=last_docs_uploaded_at,
    )


@router.post("/generate", summary="Generar/regenerar alertas con voz (bajo demanda)")
def generate_alerts_voice(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado")

    # 1) Generar alertas técnicas actuales
    alerts: list[AnalysisAlert] = get_analysis_alerts(case_id=case_id, db=db)

    # 2) Bundle anterior (para detectar cambios por fingerprint)
    prev_bundle = _load_bundle(case_id)
    prev_fp: dict[str, str] = {}
    if prev_bundle:
        for c in prev_bundle.cards:
            prev_fp[c.card_id] = c.fingerprint

    # 3) Estado editorial (preservar)
    state_obj = _load_state(case_id)

    now_iso = datetime.utcnow().isoformat() + "Z"

    cards: list[AlertVoiceCard] = []
    for a in alerts:
        payload = _voice_input_from_alert(a)
        voice = generate_voice_llm(payload, strict_language=True)

        # Fingerprint estable (para changed_since_last_review)
        chunk_ids = sorted({ev.chunk_id for ev in (a.evidence or [])})
        fp = compute_fingerprint(
            kind="alerts_voice_card_v1",
            key_parts=[
                payload.domain.value,
                a.alert_id,
                *chunk_ids,
                *(payload.findings or []),
            ],
        )

        card_id = a.alert_id
        cards.append(
            AlertVoiceCard(
                card_id=card_id,
                source_alert_id=a.alert_id,
                domain=payload.domain.value,
                relevance=(payload.relevance.value if payload.relevance else "MEDIA"),
                title_human=voice.title_human,
                summary_human=voice.summary_human,
                disclaimer_detail=voice.disclaimer_detail,
                to_clarify=voice.to_clarify,
                evidence=[e.model_dump() for e in (a.evidence or [])],
                fingerprint=fp,
                created_at=now_iso,
            )
        )

        # Preservar estado por card_id si existe
        state_obj.cards.setdefault(card_id, AlertVoiceCardState())

        # changed_since_last_review: si cambió fingerprint y estaba revisada/para_informe
        prev = prev_fp.get(card_id)
        st = state_obj.cards.get(card_id)
        if prev and prev != fp and st and st.status in ("revisada", "para_informe"):
            st.changed_since_last_review = True

    bundle = AlertsVoiceBundle(case_id=case_id, generated_at=now_iso, cards=cards)
    _save_bundle(case_id, bundle)

    # snapshot de documentos
    last_doc_dt = (
        db.query(func.max(Document.uploaded_at))
        .filter(Document.case_id == case_id, Document.deleted_at.is_(None))
        .scalar()
    )
    state_obj.last_docs_uploaded_at = last_doc_dt.isoformat() if last_doc_dt else None
    state_obj.generated_at = now_iso
    state_obj.dirty_since_last_generation = False
    _save_state(case_id, state_obj)

    return {"status": "ok", "case_id": case_id, "generated_at": now_iso, "cards": len(cards)}


@router.get("", summary="Obtener bundle de alertas con voz (persistido)")
def get_alerts_voice(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado")

    bundle = _load_bundle(case_id)
    if not bundle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay bundle generado. Ejecuta /generate.")

    state_obj = _load_state(case_id)

    # Merge: adjuntar estado editorial por card
    cards_out = []
    for c in bundle.cards:
        st = state_obj.cards.get(c.card_id, AlertVoiceCardState())
        d = c.model_dump()
        d["status"] = st.status
        d["lawyer_note"] = st.lawyer_note
        d["para_informe"] = st.para_informe
        d["changed_since_last_review"] = st.changed_since_last_review
        cards_out.append(d)

    return {
        "case_id": case_id,
        "generated_at": bundle.generated_at,
        "voice_prompt_version": bundle.voice_prompt_version,
        "schema_version": bundle.schema_version,
        "overrides_version": state_obj.overrides_version,
        "dirty_since_last_generation": state_obj.dirty_since_last_generation,
        "cards": cards_out,
    }


@router.patch("/{card_id}", summary="Actualizar estado/nota del abogado en una tarjeta")
def update_alert_voice_card(
    case_id: str,
    card_id: str,
    payload: UpdateCardRequest,
    db: Session = Depends(get_db),
) -> dict:
    _ = db
    state_obj = _load_state(case_id)
    st = state_obj.cards.get(card_id) or AlertVoiceCardState()

    if payload.status is not None:
        st.status = payload.status
    if payload.lawyer_note is not None:
        st.lawyer_note = payload.lawyer_note
    if payload.para_informe is not None:
        st.para_informe = bool(payload.para_informe)
        if st.para_informe and st.status != "descartada":
            st.status = "para_informe"
    st.updated_by = payload.updated_by or "abogado"
    st.updated_at = datetime.utcnow().isoformat() + "Z"

    state_obj.cards[card_id] = st
    state_obj.overrides_version = int(state_obj.overrides_version or 0) + 1
    _save_state(case_id, state_obj)

    return {"status": "ok", "card_id": card_id, "overrides_version": state_obj.overrides_version}

