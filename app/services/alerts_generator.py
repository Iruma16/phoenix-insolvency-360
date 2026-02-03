"""
Generador de alertas de despacho (persistidas) — reutilizable por API y background tasks.

Objetivo:
- Evitar acoplar endpoints entre sí (documents -> alerts).
- Centralizar la lógica de merge/regeneración preservando trabajo editorial.
"""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.api.analysis_alerts import get_analysis_alerts
from app.core.database import get_session_factory
from app.core.logger import get_logger
from app.models.alert import Alert as AlertORM
from app.models.alert_evidence import AlertEvidence as AlertEvidenceORM
from app.services.alert_merge_policy import compute_fingerprint
from app.services.assistant_alert_voice import AlertDomain, EvidenceRef, Relevance, VoiceInput
from app.services.assistant_alert_voice_llm import (
    PROMPT_VERSION as VOICE_PROMPT_VERSION,
    generate_voice_llm,
)

logger = get_logger()

GENERATOR_VERSION = "alerts_generator_v2"
DATASET_VERSION: str | None = None


_ROBOTIC_PHRASES = [
    r"\bse detecta\b",
    r"\bse detectan\b",
    r"\bse ha detectado\b",
    r"\bel sistema\b",
]


def _de_robotize_desc(desc: str) -> str:
    """
    Convierte descripciones técnicas (p.ej. 'se detecta...') en una forma neutra y no-robótica
    antes de pasar por guardarraíles estrictos.
    """
    t = (desc or "").strip()
    if not t:
        return t
    # Sustituciones prudentes (sin añadir conclusiones)
    repl = {
        r"\bse detectan\b": "se observan",
        r"\bse detecta\b": "se observa",
        r"\bse ha detectado\b": "se ha observado",
        r"\bel sistema\b": "en el expediente",
    }
    for pat, rpl in repl.items():
        t = re.sub(pat, rpl, t, flags=re.IGNORECASE)
    return t

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
    desc_raw = str(a.get("description") or "")
    desc = _de_robotize_desc(desc_raw)
    evidence = list(a.get("evidence") or [])
    filenames = [str(e.get("filename") or "") for e in evidence]
    domain_str = _infer_domain(desc, filenames)
    score = _score_like(desc, len(evidence), str(a.get("alert_type") or ""))
    relevance_str = _relevance_from_score(score)

    ev_refs: list[EvidenceRef] = []
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


def _to_clarify_struct(domain: str, items: list[str]) -> list[dict[str, Any]]:
    """
    Convierte checklist simple (lista de strings) a contrato enriquecido.
    """
    out: list[dict[str, Any]] = []
    for it in items or []:
        txt = (it or "").strip()
        if not txt:
            continue
        low = txt.lower()
        blocking = "bloquea" if any(k in low for k in ["certificado", "rnt", "rlc", "conciliac"]) else "no_bloquea"
        out.append({"item_text": txt, "why_needed": "", "blocking_level": blocking})
    return out[:8]


def _recommended_actions_from_to_clarify(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, it in enumerate(items[:3], 1):
        out.append(
            {
                "action_text": str(it.get("item_text") or ""),
                "priority": idx,
                "why": str(it.get("why_needed") or ""),
            }
        )
    return out


def _evidence_signal(domain: str, desc: str) -> str:
    d = (domain or "DOCS").upper()
    if d == "TGSS":
        return "Soporta referencia TGSS/apremio/periodos/importe en documentación."
    if d == "BANCO":
        return "Soporta movimiento bancario relevante (concepto/contraparte/fecha/importe)."
    if d == "CONTABILIDAD":
        return "Soporta dato contable/factura/pago para contraste."
    if d == "VINCULADAS":
        return "Soporta operación con vinculada (contraparte) y su contexto."
    # DOCS
    if "faltante" in (desc or "").lower():
        return "Soporta la referencia que ancla la falta documental."
    return "Soporta el hecho descrito en la alerta."


def generate_persisted_alerts_for_case(*, case_id: str, db: Session) -> int:
    """
    Genera/regenera alertas de despacho para un caso.

    Nota:
    - NO hace commit: el caller decide (API vs background task).
    - Preserva status/nota/para_informe/updated_by en regeneraciones.
    """
    tech_alerts = get_analysis_alerts(case_id=case_id, db=db)

    generated = 0
    missing_pdf_pages = 0

    for a in tech_alerts:
        source_id = str(a.alert_id)
        alert_id = _alert_id_from_case_and_source(case_id, source_id)

        evidence = list(a.evidence or [])
        filenames = [str(e.filename or "") for e in evidence]
        domain = _infer_domain(a.description, filenames)
        score = _score_like(a.description, len(evidence), a.alert_type.value)
        relevance = _relevance_from_score(score)

        # Fingerprint (estable): dominio + source + evidencia (doc/chunk/pags)
        ev_parts: list[str] = []
        for ev in evidence:
            loc = ev.location
            ev_parts.append(str(ev.document_id or ""))
            ev_parts.append(str(ev.filename or ""))
            ev_parts.append(str(getattr(ev, "chunk_id", "") or ""))
            ev_parts.append(str(getattr(loc, "page_start", "") or ""))
            ev_parts.append(str(getattr(loc, "page_end", "") or ""))
        fp = compute_fingerprint(kind="alert_v1", key_parts=[domain, source_id, *ev_parts])

        # Voz (LLM+reglas con fallback): reescritura sin inventar hechos.
        voice_in = _voice_input_from_analysis_alert(
            {
                "alert_type": a.alert_type.value,
                "description": a.description,
                "evidence": [ev.model_dump() for ev in (a.evidence or [])],
            }
        )
        try:
            voice = generate_voice_llm(voice_in, strict_language=True)
        except ValueError as e:
            # Hardening: algunas evidencias/findings pueden contener frases "robóticas" (p.ej. 'se detecta')
            # que el guardarraíl estricto rechaza. No es un término legal prohibido, así que degradamos
            # SOLO en ese caso a un modo de reescritura conservadora.
            msg = str(e)
            if "frase robótica prohibida" in msg or "se detecta" in msg:
                voice = generate_voice_llm(voice_in, strict_language=False)
            else:
                raise
        except Exception:
            raise

        to_clarify_struct = _to_clarify_struct(domain, list(voice_in.to_clarify or []))
        recommended_actions = _recommended_actions_from_to_clarify(to_clarify_struct)

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
            existing.score = int(score)
            existing.title_human = voice.title_human
            existing.summary_human = voice.summary_human
            existing.disclaimer_detail = voice.disclaimer_detail
            existing.to_clarify = to_clarify_struct
            existing.recommended_actions = recommended_actions
            existing.fingerprint = fp
            existing.source_alert_ids = [source_id]
            existing.rules_version = "analysis_alerts_v1"
            existing.voice_prompt_version = VOICE_PROMPT_VERSION
            existing.generator_version = GENERATOR_VERSION
            existing.dataset_version = DATASET_VERSION
            existing.generated_at = datetime.utcnow()
            existing.generated_by = "system"
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
                score=int(score),
                title_human=voice.title_human,
                summary_human=voice.summary_human,
                disclaimer_detail=voice.disclaimer_detail,
                to_clarify=to_clarify_struct,
                recommended_actions=recommended_actions,
                fingerprint=fp,
                source_alert_ids=[source_id],
                status="pendiente",
                lawyer_note="",
                para_informe=False,
                changed_since_last_review=False,
                updated_by=None,
                rules_version="analysis_alerts_v1",
                voice_prompt_version=VOICE_PROMPT_VERSION,
                generator_version=GENERATOR_VERSION,
                dataset_version=DATASET_VERSION,
                generated_at=datetime.utcnow(),
                generated_by="system",
            )
            db.add(row)
            db.flush()

        # Reescribir evidencias normalizadas (simple: delete+insert)
        db.query(AlertEvidenceORM).filter(AlertEvidenceORM.alert_id == row.alert_id).delete()
        for ev in evidence:
            loc = ev.location
            extraction_method = getattr(loc, "extraction_method", None)
            page_start = getattr(loc, "page_start", None)
            page_end = getattr(loc, "page_end", None)
            if extraction_method == "pdf_text" and page_start is None:
                missing_pdf_pages += 1

            db.add(
                AlertEvidenceORM(
                    alert_id=row.alert_id,
                    document_id=ev.document_id,
                    filename=ev.filename,
                    chunk_id=ev.chunk_id,
                    page_start=page_start,
                    page_end=page_end,
                    start_char=getattr(loc, "start_char", None),
                    end_char=getattr(loc, "end_char", None),
                    snippet=(ev.content or "")[:400],
                    signal=_evidence_signal(domain, a.description),
                )
            )

        generated += 1

    if missing_pdf_pages:
        logger.warning(
            "Alert evidence without page_start for pdf_text extraction_method",
            case_id=case_id,
            action="alerts_evidence_contract",
            missing_pdf_page_evidences=int(missing_pdf_pages),
        )

    return generated


def generate_persisted_alerts_for_case_in_new_session(*, case_id: str) -> int:
    """
    Wrapper para BackgroundTasks: abre su propia sesión y hace commit.
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        generated = generate_persisted_alerts_for_case(case_id=case_id, db=db)
        db.commit()
        return generated
    except Exception as e:
        db.rollback()
        logger.error(
            "Failed to generate persisted alerts in background task",
            case_id=case_id,
            action="alerts_generate_background_failed",
            error=e,
        )
        return 0
    finally:
        db.close()

