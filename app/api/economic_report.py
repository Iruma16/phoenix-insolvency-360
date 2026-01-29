"""
Informe de Situación Económica (para cliente).

Política:
- El informe se genera con datos deterministas a partir del expediente.
- La narrativa y el indexado interno pueden estar disponibles si hay configuración, pero no son obligatorios
  para generar y descargar el PDF.

Endpoints:
- POST /api/cases/{case_id}/economic-report/generate -> Generar + indexar (sin descargar)
- GET  /api/cases/{case_id}/economic-report/pdf      -> Descargar PDF YA generado (no regenera)
- POST /api/cases/{case_id}/economic-report/email    -> Enviar PDF YA generado (no regenera)
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Literal, Optional
import json
import re

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
from app.legal.checker.narrative_checker import check_narrative
from app.legal.checker.export_checker import check_export
from app.services.economic_report_builder import (
    _build_lawyer_signature_from_settings,
    build_economic_report_bundle,
)
from app.services.economic_report_narrative import build_economic_report_narrative_md
from app.services.email_sender import send_email_with_attachment
from app.services.report_indexing import index_economic_report_bundle

router = APIRouter(prefix="/cases/{case_id}", tags=["economic-report"])

REPORTS_BASE_DIR = Path(__file__).parent.parent.parent / "reports"

CLIENT_STATE_FILENAME = "economic_report_CLIENT_STATE.json"
CLIENT_VALIDATED_PDF_FILENAME = "economic_report_CLIENT_VALIDATED.pdf"


class ClientExportViolation(BaseModel):
    rule_id: str
    severity: str
    message: str
    action: str
    section: str


class ClientExportValidation(BaseModel):
    status: Literal["PASS", "FAIL", "UNKNOWN"] = "UNKNOWN"
    validated_at: Optional[str] = None  # ISO
    reasons: list[ClientExportViolation] = Field(default_factory=list)


class ClientHistoryEvent(BaseModel):
    at: str  # ISO
    actor: str = "abogado"
    action: str
    detail: str


class ClientAddendum(BaseModel):
    text: str = ""
    include_in_pdf: bool = True
    placement: Literal["before_signature", "after_block_8"] = "before_signature"
    edited_by: str = "abogado"
    edited_at: Optional[str] = None  # ISO


class ClientReportState(BaseModel):
    case_id: str
    report_id: Optional[str] = None
    generated_at: Optional[str] = None  # ISO
    dirty_since_last_validation: bool = True
    validation: ClientExportValidation = Field(default_factory=ClientExportValidation)
    addendum: ClientAddendum = Field(default_factory=ClientAddendum)
    overrides_version: int = 0
    debt_overrides: list[dict] = Field(default_factory=list)
    timeline_overrides: list[dict] = Field(default_factory=list)
    history: list[ClientHistoryEvent] = Field(default_factory=list)


class SaveAddendumRequest(BaseModel):
    text: str = Field("", max_length=6000)
    include_in_pdf: bool = True
    placement: Literal["before_signature", "after_block_8"] = "before_signature"
    edited_by: str = "abogado"


class ApplyOverridesRequest(BaseModel):
    expected_version: int = 0
    edited_by: str = "abogado"
    # Deudas: debt_id + campos editables + evidencia obligatoria
    debt_overrides: list[dict] = Field(default_factory=list)
    # Timeline: event_key + campos editables + evidencia obligatoria
    timeline_overrides: list[dict] = Field(default_factory=list)


def _event_key(ev: object) -> str:
    """
    Key estable (best-effort) para un evento de timeline dentro del bundle (no tiene event_id).
    """
    try:
        # Preferir event_id si existe (más robusto para overrides)
        eid = str(getattr(ev, "event_id", "") or "").strip()
        if eid:
            return eid
        d = getattr(ev, "date", None) or getattr(ev, "event_date", None)
        et = (getattr(ev, "event_type", None) or "").strip().lower()
        desc = (getattr(ev, "description", None) or "").strip().replace("\n", " ")
        amt = getattr(ev, "amount", None)
        evid = getattr(ev, "evidence", None)
        doc_id = ""
        chunk_id = ""
        page = ""
        try:
            doc_id = str(getattr(evid, "document_id", "") or "")
            chunk_id = str(getattr(evid, "chunk_id", "") or "")
            page = str(getattr(evid, "page", "") or "")
        except Exception:
            doc_id = ""
            chunk_id = ""
            page = ""
        ds = ""
        if isinstance(d, datetime):
            ds = d.date().isoformat()
        elif d:
            ds = str(d)[:10]
        head = re.sub(r"\s+", " ", desc)[:80]
        return f"{ds}|{et}|{doc_id[:12]}|{chunk_id[:12]}|{page}|{str(amt)[:16]}|{head}"
    except Exception:
        return "unknown|unknown|unknown"


def _apply_structured_overrides(bundle: EconomicReportBundle, state: ClientReportState) -> None:
    """
    Aplica overrides estructurados al bundle (solo para vista previa/validación/export cliente).
    - debt_overrides: modifica debt_legal_applications por debt_id
    - timeline_overrides: modifica/elimina eventos por event_key
    """
    # Deudas
    try:
        contract = getattr(bundle, "narrative_contract", None)
        apps = list(getattr(contract, "debt_legal_applications", None) or []) if contract else []
        by_id: dict[str, object] = {str(getattr(d, "debt_id", "") or ""): d for d in apps if getattr(d, "debt_id", None)}
        for o in (state.debt_overrides or [])[:300]:
            debt_id = str((o or {}).get("debt_id") or "").strip()
            if not debt_id or debt_id not in by_id:
                continue
            target = by_id[debt_id]
            # Campos editables (best-effort)
            for field in [
                "creditor_name",
                "creditor_type",
                "amount_eur",
                "proposed_trlc_bucket",
                "period_start",
                "period_end",
                "period_note",
                "has_security",
                "security_type",
                "security_note",
            ]:
                if field in o:
                    try:
                        setattr(target, field, o.get(field))
                    except Exception:
                        pass
    except Exception:
        pass

    # Timeline
    try:
        tl = list(getattr(bundle.financial_analysis, "timeline", None) or [])
        if not tl:
            return
        ov = {str((x or {}).get("event_key") or ""): x for x in (state.timeline_overrides or []) if (x or {}).get("event_key")}
        out = []
        for ev in tl:
            k = _event_key(ev)
            o = ov.get(k)
            if o and bool(o.get("exclude_from_client")):
                continue
            if o:
                if "description" in o and o.get("description") is not None:
                    try:
                        setattr(ev, "description", str(o.get("description") or ""))
                    except Exception:
                        pass
                if "date" in o and o.get("date") is not None:
                    # Fecha ISO YYYY-MM-DD o "Fecha no determinada"
                    try:
                        ds = str(o.get("date") or "").strip()
                        if not ds or ds.lower().startswith("fecha"):
                            setattr(ev, "date", None)
                        else:
                            setattr(ev, "date", datetime.fromisoformat(ds))
                    except Exception:
                        pass
            out.append(ev)
        setattr(bundle.financial_analysis, "timeline", out)
    except Exception:
        pass

    # Recalcular insolvencia tras cambios de timeline (coherencia aguas abajo)
    try:
        from app.services.financial_analysis import detect_insolvency_signals

        fin = bundle.financial_analysis
        balance = getattr(fin, "balance", None)
        profit_loss = getattr(fin, "profit_loss", None)
        timeline_events = list(getattr(fin, "timeline", None) or [])
        fin.insolvency = detect_insolvency_signals(balance, profit_loss, timeline_events)
    except Exception:
        pass


def _client_state_path(case_id: str) -> Path:
    return _ensure_reports_dir(case_id) / CLIENT_STATE_FILENAME


def _client_validated_pdf_path(case_id: str) -> Path:
    return _ensure_reports_dir(case_id) / CLIENT_VALIDATED_PDF_FILENAME


def _load_client_state(case_id: str) -> ClientReportState:
    p = _client_state_path(case_id)
    if not p.exists():
        return ClientReportState(case_id=case_id)
    try:
        return ClientReportState.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        # Fallback conservador si el JSON se corrompe
        return ClientReportState(case_id=case_id)


def _save_client_state(case_id: str, state: ClientReportState) -> None:
    p = _client_state_path(case_id)
    tmp = p.with_suffix(p.suffix + ".tmp")
    payload = state.model_dump_json(indent=2, ensure_ascii=False)
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(p)


def _compute_client_mode(state: ClientReportState) -> Literal["BORRADOR", "PUBLICABLE"]:
    if state.dirty_since_last_validation:
        return "BORRADOR"
    if state.validation.status != "PASS":
        return "BORRADOR"
    return "PUBLICABLE"


def _append_history(state: ClientReportState, *, actor: str, action: str, detail: str) -> None:
    state.history.append(
        ClientHistoryEvent(
            at=datetime.utcnow().isoformat(),
            actor=(actor or "abogado"),
            action=action,
            detail=detail,
        )
    )
    # mantener tamaño acotado
    state.history = state.history[-80:]


def _mark_client_dirty(state: ClientReportState, *, actor: str, action: str, detail: str) -> None:
    state.dirty_since_last_validation = True
    state.validation = ClientExportValidation(status="UNKNOWN", validated_at=None, reasons=[])
    _append_history(state, actor=actor, action=action, detail=detail)


def _sanitize_bundle_for_client(bundle: EconomicReportBundle) -> None:
    """
    Sanitización defensiva para audience=client:
    - Nunca exponer “puntos clave / qué hacer / confianza / metadata / ocr / chunks”
    - Nunca exponer alertas técnicas en exportación cliente
    - Timeline: eliminar rastros epoch/microsegundos en descripciones
    """
    try:
        cs = bundle.client_summary
        cs.key_points = []
        cs.next_7_days = []
    except Exception:
        pass
    try:
        bundle.alerts = []
    except Exception:
        pass
    try:
        for ev in (bundle.financial_analysis.timeline or []):
            desc = (getattr(ev, "description", None) or "")
            desc = desc.replace("1970-01-01 00:00:00.000000150", "").strip()
            desc = desc.replace("1970-01-01", "").strip()
            if not desc:
                desc = "Hecho relevante (fecha no determinada)"
            setattr(ev, "description", desc)
    except Exception:
        pass
    try:
        ins = bundle.financial_analysis.insolvency
        if ins:
            for s in (ins.signals_impago or []) + (ins.signals_contables or []) + (ins.signals_exigibilidad or []):
                d = (getattr(s, "description", None) or "")
                if "Metadata:" in d:
                    d = d.replace("Metadata:", "").strip()
                setattr(s, "description", d)
    except Exception:
        pass


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
    # Compatibilidad: antes este endpoint era "estricto".
    # Actualmente el PDF puede generarse sin LLM; si no hay LLM disponible,
    # simplemente se omitirá la narrativa.
    return None


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

    # Narrativa (opcional): si falla, no bloquea el informe.
    if settings.llm_available:
        try:
            draft = build_economic_report_narrative_md(db, bundle=bundle)
            check = check_narrative(draft, bundle=bundle)
            if check.status == "PASS":
                bundle.narrative_md = draft
            elif check.action == "RETRY":
                # Un reintento máximo
                draft2 = build_economic_report_narrative_md(db, bundle=bundle)
                check2 = check_narrative(draft2, bundle=bundle)
                bundle.narrative_md = draft2 if check2.status == "PASS" else None
            else:
                bundle.narrative_md = None
        except Exception:
            bundle.narrative_md = None

    return bundle


@router.post(
    "/economic-report/generate",
    summary="Generar informe económico (sin descarga) e indexar",
)
def generate_economic_report(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    bundle = _generate_bundle_strict(case_id=case_id, request=request, db=db, current_user=current_user)

    # Indexado interno (opcional): nunca debe bloquear el PDF.
    try:
        index_economic_report_bundle(db, bundle=bundle, ensure_case_embeddings=True)
    except Exception:
        pass

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

        # Default: internal
        pdf_bytes = generate_economic_report_pdf(bundle, audience="internal")
        # Auditoría (timestamp)
        (out_dir / f"economic_report_{bundle.report_id}_{ts}.pdf").write_bytes(pdf_bytes)
        # ACTIVE (overwrite)
        _active_pdf_path(case_id).write_bytes(pdf_bytes)
    except Exception:
        pass

    # Estado de edición/validación cliente
    try:
        state = _load_client_state(case_id)
        state.report_id = bundle.report_id
        state.generated_at = bundle.generated_at.isoformat()
        _mark_client_dirty(
            state,
            actor=str(getattr(current_user, "email", None) or "abogado"),
            action="generate",
            detail="Generación/regeneración del informe (borrador).",
        )
        _save_client_state(case_id, state)
    except Exception:
        pass

    return {"status": "ok", "case_id": case_id, "report_id": bundle.report_id}

@router.get(
    "/economic-report/status",
    summary="Estado del informe (borrador/publicable) + validación + adenda",
)
def get_economic_report_status(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ = request
    _ = db
    _ = current_user

    pdf_path = _active_pdf_path(case_id)
    json_path = _active_json_path(case_id)
    state = _load_client_state(case_id)

    has_generated = pdf_path.exists() and json_path.exists()
    case_name = None
    report_id = state.report_id
    generated_at = state.generated_at
    if has_generated:
        try:
            bundle = EconomicReportBundle.model_validate_json(json_path.read_text(encoding="utf-8"))
            case_name = bundle.case_name
            report_id = bundle.report_id
            generated_at = bundle.generated_at.isoformat()
        except Exception:
            pass

    mode = _compute_client_mode(state)
    return {
        "case_id": case_id,
        "case_name": case_name,
        "has_generated": has_generated,
        "report_id": report_id,
        "generated_at": generated_at,
        "dirty_since_last_validation": state.dirty_since_last_validation,
        "validation": state.validation.model_dump(),
        "mode": mode,
        "addendum": state.addendum.model_dump(),
        "overrides_version": state.overrides_version,
        "history": [h.model_dump() for h in state.history[-30:]],
        "client_pdf_ready": _client_validated_pdf_path(case_id).exists() and mode == "PUBLICABLE",
    }


@router.get(
    "/economic-report/sections",
    summary="Vista previa por secciones (markdown) del último informe + adenda",
)
def get_economic_report_sections(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ = request
    _ = db
    _ = current_user

    json_path = _active_json_path(case_id)
    if not json_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay un informe generado. Ejecuta primero /economic-report/generate.",
        )
    bundle = EconomicReportBundle.model_validate_json(json_path.read_text(encoding="utf-8"))
    state = _load_client_state(case_id)

    # Vista previa "cliente": aplicar sanitización defensiva para no mostrar epoch/tecnicismos.
    _sanitize_bundle_for_client(bundle)
    _apply_structured_overrides(bundle, state)

    # preview determinista (UI): NO es el PDF, pero sigue el orden 1..9
    def _md(s: str) -> str:
        return (s or "").strip()

    def _fmt_date(d: object) -> str:
        if d is None:
            return "Fecha no determinada"
        try:
            if isinstance(d, datetime):
                if d.year < 2000 or d.year > 2100:
                    return "Fecha no determinada"
                return d.strftime("%d/%m/%Y")
            s = str(d)
            if s.startswith("1970-01-01"):
                return "Fecha no determinada"
            if len(s) >= 10 and s[4] == "-" and s[7] == "-":
                yyyy = int(s[0:4])
                mm = int(s[5:7])
                dd = int(s[8:10])
                if yyyy < 2000 or yyyy > 2100:
                    return "Fecha no determinada"
                return f"{dd:02d}/{mm:02d}/{yyyy:04d}"
        except Exception:
            return "Fecha no determinada"
        return "Fecha no determinada"

    # Block 1
    b1 = f"**{_md(bundle.client_summary.headline)}**\n"
    if bundle.client_summary.warnings:
        b1 += "\n**Advertencias:**\n" + "\n".join([f"- {x}" for x in bundle.client_summary.warnings[:8]])

    # Block 2
    tl = []
    try:
        for ev in (bundle.financial_analysis.timeline or [])[:12]:
            d = getattr(ev, "date", None) or getattr(ev, "event_date", None)
            desc = getattr(ev, "description", None) or getattr(ev, "event", None) or ""
            tl.append(f"- {_fmt_date(d)} — {_md(desc)}")
    except Exception:
        pass
    b2 = "\n".join(tl) if tl else "No hay hitos legibles con los datos actuales."

    # Block 3
    docs = [f"- {d.filename}" for d in (bundle.documents_presented or [])[:18]]
    b3 = "**Documentos aportados (muestra):**\n" + ("\n".join(docs) if docs else "- No hay") + "\n\n"
    b3 += "**Documentos faltantes (críticos):**\n" + (
        "\n".join([f"- {x}" for x in (bundle.documents_missing or [])[:12]]) if bundle.documents_missing else "- No hay"
    )
    b3 += "\n\n**Documentación recomendada:**\n" + (
        "\n".join([f"- {x}" for x in (bundle.documents_recommended or [])[:12]]) if bundle.documents_recommended else "- No hay"
    )

    # Block 4
    ratios = []
    try:
        for r in (bundle.financial_analysis.ratios or [])[:10]:
            name = getattr(r, "name", "ratio")
            val = getattr(r, "value", None)
            try:
                sval = f"{float(val):.2f}" if val is not None else "No consta"
            except Exception:
                sval = "No consta"
            ratios.append(f"- {name}: {sval}")
    except Exception:
        pass
    b4 = "**Ratios (muestra):**\n" + ("\n".join(ratios) if ratios else "- No consta") + "\n\n"
    try:
        ins = bundle.financial_analysis.insolvency
        if ins and getattr(ins, "overall_assessment", None):
            b4 += f"**Señales decisivas:** {_md(ins.overall_assessment)}\n"
    except Exception:
        pass

    # Block 5
    debts = []
    try:
        contract = bundle.narrative_contract
        apps = list(getattr(contract, "debt_legal_applications", None) or []) if contract else []
        for d in apps[:12]:
            debts.append(f"- {getattr(d,'creditor_name','?')} — {getattr(d,'amount_eur',None)} € — {getattr(d,'proposed_trlc_bucket','no_determinable')}")
    except Exception:
        pass
    b5 = "\n".join(debts) if debts else "No hay clasificación deuda-a-deuda disponible con los datos actuales."

    # Block 6-8 (roadmap)
    steps = []
    for s in (bundle.roadmap or [])[:20]:
        steps.append(f"- ({getattr(s,'actor','no_determinable')}) {getattr(s,'phase','')} — {getattr(s,'step','')}")
    b8 = "\n".join(steps) if steps else "No hay hoja de ruta estructurada con los datos actuales."

    # Block 9 (firma)
    sig = bundle.lawyer_signature
    b9 = "Firma no disponible."
    if sig:
        b9 = (
            f"- Despacho: {getattr(sig,'law_firm', '')}\n"
            f"- Abogado/a: {getattr(sig,'lawyer_name','')}\n"
            f"- Nº colegiado: {getattr(sig,'collegiate_number','')}\n"
            f"- Fecha de firma: {getattr(sig,'signature_date','')}\n"
        )

    add = state.addendum
    add_md = ""
    if add and add.include_in_pdf and (add.text or "").strip():
        add_md = f"**Adenda del abogado:**\n\n{add.text.strip()}"

    return {
        "case_id": case_id,
        "report_id": bundle.report_id,
        "generated_at": bundle.generated_at.isoformat(),
        "sections": [
            {"id": "1", "title": "1. Resumen ejecutivo", "content_md": b1},
            {"id": "2", "title": "2. Evolución (línea temporal)", "content_md": b2},
            {"id": "3", "title": "3. Inventario documental", "content_md": b3},
            {"id": "4", "title": "4. Situación económica", "content_md": b4},
            {"id": "5", "title": "5. Clasificación de deudas", "content_md": b5},
            {"id": "8", "title": "8. Hoja de ruta", "content_md": b8},
            {"id": "9", "title": "9. Firma del abogado", "content_md": b9},
            {"id": "addendum", "title": "Adenda del abogado (si aplica)", "content_md": add_md or "—"},
        ],
    }


@router.get(
    "/economic-report/editables",
    summary="Datos editables (deudas/hitos) + versión de overrides",
)
def get_economic_report_editables(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ = request
    _ = db
    _ = current_user

    json_path = _active_json_path(case_id)
    if not json_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay un informe generado. Ejecuta primero /economic-report/generate.",
        )
    bundle = EconomicReportBundle.model_validate_json(json_path.read_text(encoding="utf-8"))
    state = _load_client_state(case_id)

    _sanitize_bundle_for_client(bundle)
    _apply_structured_overrides(bundle, state)

    debts: list[dict] = []
    try:
        contract = bundle.narrative_contract
        apps = list(getattr(contract, "debt_legal_applications", None) or []) if contract else []
        for d in apps[:200]:
            debts.append(
                {
                    "debt_id": getattr(d, "debt_id", ""),
                    "creditor_name": getattr(d, "creditor_name", ""),
                    "creditor_type": getattr(d, "creditor_type", ""),
                    "amount_eur": getattr(d, "amount_eur", None),
                    "proposed_trlc_bucket": getattr(d, "proposed_trlc_bucket", "no_determinable"),
                    "period_start": getattr(d, "period_start", None),
                    "period_end": getattr(d, "period_end", None),
                    "period_note": getattr(d, "period_note", ""),
                    "has_security": getattr(d, "has_security", None),
                    "security_type": getattr(d, "security_type", None),
                    "security_note": getattr(d, "security_note", ""),
                    "evidence": "",
                }
            )
    except Exception:
        pass

    timeline: list[dict] = []
    try:
        for ev in (bundle.financial_analysis.timeline or [])[:200]:
            timeline.append(
                {
                    "event_key": _event_key(ev),
                    "date": getattr(ev, "date", None).date().isoformat() if getattr(ev, "date", None) else "",
                    "event_type": getattr(ev, "event_type", ""),
                    "description": getattr(ev, "description", ""),
                    "exclude_from_client": False,
                    "evidence": "",
                }
            )
    except Exception:
        pass

    return {
        "case_id": case_id,
        "overrides_version": state.overrides_version,
        "debts": debts,
        "timeline": timeline,
    }


@router.post(
    "/economic-report/overrides",
    summary="Aplicar overrides estructurados (deudas/hitos) con lock optimista",
)
def apply_economic_report_overrides(
    case_id: str,
    payload: ApplyOverridesRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ = request
    _ = db
    _ = current_user

    state = _load_client_state(case_id)
    if state.overrides_version != int(payload.expected_version or 0):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "CONCURRENT_MODIFICATION",
                "message": "Otro usuario modificó las correcciones. Recarga y reintenta.",
                "current_version": state.overrides_version,
                "expected_version": payload.expected_version,
            },
        )

    # Validación mínima: evidencia obligatoria en cada override
    debt_overrides_in = payload.debt_overrides or []
    timeline_overrides_in = payload.timeline_overrides or []

    cleaned_debts: list[dict] = []
    for o in debt_overrides_in[:300]:
        if not isinstance(o, dict):
            continue
        if not str(o.get("debt_id") or "").strip():
            continue
        ev = str(o.get("evidence") or "").strip()
        if len(ev) < 10:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Evidencia/justificación obligatoria (mínimo 10 caracteres) en correcciones de deudas.",
            )
        cleaned_debts.append(o)

    cleaned_tl: list[dict] = []
    for o in timeline_overrides_in[:300]:
        if not isinstance(o, dict):
            continue
        if not str(o.get("event_key") or "").strip():
            continue
        ev = str(o.get("evidence") or "").strip()
        if len(ev) < 10:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Evidencia/justificación obligatoria (mínimo 10 caracteres) en correcciones del timeline.",
            )
        cleaned_tl.append(o)

    state.debt_overrides = cleaned_debts
    state.timeline_overrides = cleaned_tl
    state.overrides_version = int(state.overrides_version or 0) + 1
    _mark_client_dirty(
        state,
        actor=payload.edited_by or str(getattr(current_user, "email", None) or "abogado"),
        action="overrides_apply",
        detail=f"Correcciones estructuradas aplicadas (deudas={len(cleaned_debts)}, hitos={len(cleaned_tl)}).",
    )
    _save_client_state(case_id, state)

    return {"status": "ok", "overrides_version": state.overrides_version, "mode": _compute_client_mode(state)}


@router.post(
    "/economic-report/addendum",
    summary="Guardar adenda del abogado (marca BORRADOR)",
)
def save_economic_report_addendum(
    case_id: str,
    payload: SaveAddendumRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ = request
    _ = db
    _ = current_user

    state = _load_client_state(case_id)
    state.addendum = ClientAddendum(
        text=payload.text or "",
        include_in_pdf=bool(payload.include_in_pdf),
        placement=payload.placement,
        edited_by=payload.edited_by or "abogado",
        edited_at=datetime.utcnow().isoformat(),
    )
    _mark_client_dirty(
        state,
        actor=payload.edited_by or str(getattr(current_user, "email", None) or "abogado"),
        action="addendum_save",
        detail="Adenda guardada (borrador marcado como pendiente de validación).",
    )
    _save_client_state(case_id, state)
    return {"status": "ok", "mode": _compute_client_mode(state)}


@router.post(
    "/economic-report/validate",
    summary="Validar exportación a cliente (checker) y preparar PDF validado",
)
def validate_economic_report_client_export(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ = request
    _ = db
    _ = current_user

    json_path = _active_json_path(case_id)
    if not json_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay un informe generado. Ejecuta primero /economic-report/generate.",
        )

    try:
        bundle = EconomicReportBundle.model_validate_json(json_path.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No se pudo cargar el informe.")

    # Refrescar firma desde settings
    try:
        bundle.lawyer_signature = _build_lawyer_signature_from_settings()
    except Exception:
        pass

    _sanitize_bundle_for_client(bundle)

    state = _load_client_state(case_id)
    _apply_structured_overrides(bundle, state)

    # Nota: el checker no conoce “adenda” como campo; para validación la colocamos en narrative_md
    # (y para el PDF cliente, en legal_synthesis para render determinista).
    add = state.addendum
    if add and add.include_in_pdf and (add.text or "").strip():
        add_text = (add.text or "").strip()
        bundle.narrative_md = "## Adenda del abogado\n\n" + add_text + "\n"
        try:
            bundle.legal_synthesis = bundle.legal_synthesis or {}
            bundle.legal_synthesis["lawyer_addendum"] = {
                "text": add_text,
                "placement": getattr(add, "placement", "before_signature"),
                "edited_by": getattr(add, "edited_by", "abogado"),
                "edited_at": getattr(add, "edited_at", None),
            }
        except Exception:
            pass

    report = check_export(bundle, audience="client")
    violations = [
        ClientExportViolation(
            rule_id=x.rule_id,
            severity=x.severity,
            message=x.message,
            action=x.action,
            section=x.section,
        )
        for x in (report.violations or [])
        if x.action == "BLOCK_CLIENT_OUTPUT"
    ]

    state.dirty_since_last_validation = False
    state.validation = ClientExportValidation(
        status="PASS" if report.ok else "FAIL",
        validated_at=datetime.utcnow().isoformat(),
        reasons=violations[:50],
    )
    _append_history(
        state,
        actor=str(getattr(current_user, "email", None) or "abogado"),
        action="validate",
        detail="Validación export cliente ejecutada.",
    )
    _save_client_state(case_id, state)

    if report.ok:
        # Preparar y persistir PDF cliente validado (misma base que se ha validado)
        pdf_bytes = generate_economic_report_pdf(
            bundle,
            audience="client",
        )
        try:
            _client_validated_pdf_path(case_id).write_bytes(pdf_bytes)
        except Exception:
            pass

    return {
        "status": "ok",
        "validation_status": state.validation.status,
        "validated_at": state.validation.validated_at,
        "mode": _compute_client_mode(state),
        "reasons": [r.model_dump() for r in state.validation.reasons[:12]],
    }


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

    audience = (request.query_params.get("audience") or "internal").strip().lower()
    if audience not in ("internal", "client"):
        audience = "internal"

    pdf_path = _active_pdf_path(case_id)
    json_path = _active_json_path(case_id)
    if not pdf_path.exists() or not json_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay un informe generado. Ejecuta primero /economic-report/generate.",
        )

    if audience == "internal":
        pdf_bytes = pdf_path.read_bytes()
    else:
        # Guardrail: PDF cliente SOLO si está validado (PASS) y no hay cambios pendientes.
        state = _load_client_state(case_id)
        mode = _compute_client_mode(state)
        if mode != "PUBLICABLE" or state.validation.status != "PASS" or state.dirty_since_last_validation:
            reasons = [f"{x.rule_id}: {x.message}" for x in (state.validation.reasons or [])[:12]]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "Debes validar la exportación a cliente antes de descargar", "reasons": reasons},
            )
        p = _client_validated_pdf_path(case_id)
        if not p.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "No existe PDF cliente validado. Ejecuta /economic-report/validate.", "reasons": []},
            )
        pdf_bytes = p.read_bytes()

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

    # Guardrail: email SOLO si está validado (PASS) y con PDF cliente validado.
    state = _load_client_state(case_id)
    mode = _compute_client_mode(state)
    if mode != "PUBLICABLE" or state.validation.status != "PASS" or state.dirty_since_last_validation:
        reasons = [f"{x.rule_id}: {x.message}" for x in (state.validation.reasons or [])[:12]]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Debes validar la exportación a cliente antes de enviar por email", "reasons": reasons},
        )
    pdf_path = _client_validated_pdf_path(case_id)
    if not pdf_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No existe PDF cliente validado. Ejecuta primero /economic-report/validate.",
        )
    pdf_bytes = pdf_path.read_bytes()

    # Asunto básico (sin necesidad de regenerar bundle)
    filename = f"informe_situacion_economica_{case_id}.pdf"
    subject = f"Informe de situación económica — Caso {case_id}"
    body = "Adjunto encontrarás el informe de situación económica (versión validada para entrega).\n"

    send_email_with_attachment(
        to_email=payload.to_email,
        subject=subject,
        body_text=body,
        attachment_filename=filename,
        attachment_bytes=pdf_bytes,
    )

    try:
        _append_history(
            state,
            actor=str(getattr(current_user, "email", None) or "abogado"),
            action="email",
            detail=f"Envío por email a {payload.to_email}.",
        )
        _save_client_state(case_id, state)
    except Exception:
        pass

    return {"status": "ok", "to": payload.to_email, "filename": filename}


def mark_client_report_dirty(case_id: str, *, actor: str, detail: str) -> None:
    """
    Marca el informe cliente como BORRADOR por cambios aguas arriba (documentos/expediente).
    Uso: desde otros endpoints cuando el expediente cambia.
    """
    try:
        state = _load_client_state(case_id)
        _mark_client_dirty(state, actor=actor or "system", action="upstream_change", detail=detail)
        _save_client_state(case_id, state)
    except Exception:
        return None

