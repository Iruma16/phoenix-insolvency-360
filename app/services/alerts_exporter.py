"""
Export de alertas despacho a informe (solo alertas validadas).

Reglas:
- Solo exportar: status in ('revisada', 'para_informe')
- Incluir: texto humano + evidencias trazables + notas abogado
- Plantilla: sección por categoría (domain), orden por relevancia
- Trazabilidad fuerte: registro global de evidencias incluidas
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.models.alert import Alert as AlertORM
from app.models.alert_evidence import AlertEvidence as AlertEvidenceORM

logger = get_logger()

REPORTS_BASE_DIR = Path(__file__).parent.parent.parent / "reports"


def _ensure_case_dir(case_id: str) -> Path:
    p = REPORTS_BASE_DIR / case_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _relevance_rank(r: str) -> int:
    return {"ALTA": 0, "MEDIA": 1, "BAJA": 2}.get(str(r or "MEDIA"), 9)


def _default_checklist(domain: str) -> list[str]:
    d = str(domain or "DOCS").upper()
    if d == "TGSS":
        return [
            "RNT/RLC de los meses afectados (y justificantes de pago si existen).",
            "Certificado TGSS actualizado (deuda/estado).",
            "Soporte de aplazamiento/fraccionamiento si existe.",
            "Conciliación bancaria del periodo.",
        ]
    if d == "BANCO":
        return [
            "Extractos completos del periodo (no solo resúmenes).",
            "Conciliación bancaria y explicación de conceptos genéricos.",
            "Contrato/soporte de los pagos (servicios, préstamos, etc.).",
        ]
    if d == "CONTABILIDAD":
        return [
            "Factura + justificante + extracto bancario (conciliación).",
            "Soporte y asiento del IVA (si aplica).",
            "Confirmar si hubo rectificativa o pago posterior.",
        ]
    if d == "VINCULADAS":
        return [
            "Contrato y entregables/soporte del servicio prestado.",
            "Criterio de precios y relación con el grupo.",
            "Conciliación bancaria de los pagos.",
        ]
    return [
        "Confirmar si la documentación existe y, si existe, incorporarla al expediente.",
        "Aportar soporte adicional si este punto va a informe.",
    ]


def _md_escape(s: str) -> str:
    # Escape mínimo para evitar romper markdown; mantenemos legibilidad.
    return (s or "").replace("\r", "").strip()


@dataclass(frozen=True)
class AlertsExportResult:
    case_id: str
    generated_at: str
    included_alerts: int
    markdown: str
    markdown_filename: str
    evidence_registry: list[dict[str, Any]]


def export_validated_alerts_to_markdown(*, case_id: str, db: Session) -> AlertsExportResult:
    now = datetime.utcnow().isoformat() + "Z"

    rows: list[AlertORM] = (
        db.query(AlertORM)
        .filter(
            AlertORM.case_id == case_id,
            AlertORM.status.in_(["revisada", "para_informe"]),
        )
        .order_by(AlertORM.domain.asc(), AlertORM.relevance.asc(), AlertORM.updated_at.desc())
        .all()
    )

    # Agrupar por dominio
    by_domain: dict[str, list[AlertORM]] = {}
    for r in rows:
        by_domain.setdefault(r.domain or "DOCS", []).append(r)

    # Reordenar por relevancia (ALTA->MEDIA->BAJA) dentro de cada dominio
    for d in by_domain:
        by_domain[d].sort(
            key=lambda a: (_relevance_rank(a.relevance), a.updated_at or a.created_at),
            reverse=False,
        )

    evidence_registry: list[dict[str, Any]] = []
    seen_ev: set[str] = set()

    def _add_registry(alert_id: str, ev: AlertEvidenceORM) -> None:
        key = "|".join(
            [
                str(ev.document_id or ""),
                str(ev.filename or ""),
                str(ev.page_start or ""),
                str(ev.page_end or ""),
                str(ev.chunk_id or ""),
                (ev.snippet or "")[:160],
            ]
        )
        if key in seen_ev:
            return
        seen_ev.add(key)
        evidence_registry.append(
            {
                "alert_id": alert_id,
                "document_id": ev.document_id,
                "filename": ev.filename,
                "chunk_id": ev.chunk_id,
                "page_start": ev.page_start,
                "page_end": ev.page_end,
                "start_char": ev.start_char,
                "end_char": ev.end_char,
                "snippet": ev.snippet,
                "signal": getattr(ev, "signal", None),
            }
        )

    # Construir markdown
    lines: list[str] = []
    lines.append("# Informe de alertas validadas (despacho)\n")
    lines.append(f"- **case_id**: `{case_id}`")
    lines.append(f"- **generado_at**: `{now}`")
    lines.append(f"- **incluidas**: {len(rows)} alerta(s) (status revisada/para_informe)\n")

    # Secciones por categoría
    for domain in sorted(by_domain.keys()):
        alerts = by_domain[domain]
        lines.append(f"## {domain}\n")

        for a in alerts:
            changed = (
                " (cambió desde la última revisión)" if bool(a.changed_since_last_review) else ""
            )
            lines.append(f"### {a.title_human} — {a.relevance} — {a.status}{changed}\n")
            if a.summary_human:
                lines.append(_md_escape(a.summary_human) + "\n")

            # Nota abogado
            if (a.lawyer_note or "").strip():
                lines.append("**Nota del abogado**")
                lines.append(_md_escape(a.lawyer_note) + "\n")

            # Evidencias trazables
            ev_rows: list[AlertEvidenceORM] = (
                db.query(AlertEvidenceORM)
                .filter(AlertEvidenceORM.alert_id == a.alert_id)
                .order_by(AlertEvidenceORM.evidence_id.asc())
                .all()
            )
            if ev_rows:
                lines.append("**Evidencias incluidas**")
                for ev in ev_rows:
                    pages = ""
                    if ev.page_start is not None:
                        pages = (
                            f"pág. {ev.page_start}"
                            if (ev.page_end is None or ev.page_end == ev.page_start)
                            else f"pág. {ev.page_start}-{ev.page_end}"
                        )
                    loc = " · ".join(
                        [p for p in [pages, (f"chunk {ev.chunk_id}" if ev.chunk_id else "")] if p]
                    )
                    loc = f" ({loc})" if loc else ""
                    lines.append(f"- **{ev.filename}**{loc}")
                    if (ev.snippet or "").strip():
                        lines.append(f"  - _Snippet_: {(_md_escape(ev.snippet)[:400])}")
                    _add_registry(a.alert_id, ev)
                lines.append("")

            # Checklist (pendiente) — no hay “aclarado” persistido todavía.
            checklist_items = []
            if a.to_clarify:
                for it in (a.to_clarify or [])[:10]:
                    checklist_items.append(str(it.get("item_text") or "").strip())
            if not checklist_items:
                checklist_items = _default_checklist(a.domain)

            if checklist_items:
                lines.append("**Checklist (pendiente de aclarar, si aplica)**")
                for it in checklist_items:
                    lines.append(f"- {it}")
                lines.append("")

            # Disclaimer (por alerta, si existe)
            if (a.disclaimer_detail or "").strip():
                lines.append("**Nota legal (disclaimer)**")
                lines.append(_md_escape(a.disclaimer_detail) + "\n")

        lines.append("")

    # Registro global de evidencias
    lines.append("## Registro de evidencias incluidas\n")
    if not evidence_registry:
        lines.append("_No se incluyeron evidencias._\n")
    else:
        for idx, ev in enumerate(evidence_registry, 1):
            pages = ""
            if ev.get("page_start") is not None:
                p1 = ev.get("page_start")
                p2 = ev.get("page_end")
                pages = f"pág. {p1}" if (p2 is None or p2 == p1) else f"pág. {p1}-{p2}"
            lines.append(
                f"{idx}. **{ev.get('filename') or '—'}** {pages} "
                f"(doc_id: `{str(ev.get('document_id') or '')[:16]}` · alert_id: `{str(ev.get('alert_id') or '')[:16]}`)"
            )
            sn = (ev.get("snippet") or "").strip()
            if sn:
                lines.append(f"   - _Snippet_: {(_md_escape(sn)[:400])}")
        lines.append("")

    # Disclaimer general
    lines.append("## Nota legal general\n")
    lines.append(
        "Este documento es un resumen operativo basado en alertas validadas y evidencias trazables. "
        "No sustituye el análisis jurídico del abogado ni constituye valoración concluyente.\n"
    )

    md = "\n".join(lines).strip() + "\n"

    # Persistir a reports/{case_id}/
    out_dir = _ensure_case_dir(case_id)
    filename = "alerts_export_validated.md"
    path = out_dir / filename
    path.write_text(md, encoding="utf-8")

    logger.info(
        "Alerts export generated",
        case_id=case_id,
        action="alerts_export_generated",
        included_alerts=int(len(rows)),
        evidence_count=int(len(evidence_registry)),
        path=str(path),
    )

    return AlertsExportResult(
        case_id=case_id,
        generated_at=now,
        included_alerts=len(rows),
        markdown=md,
        markdown_filename=filename,
        evidence_registry=evidence_registry,
    )
