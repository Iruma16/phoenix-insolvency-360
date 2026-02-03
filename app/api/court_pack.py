from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.case import Case
from app.services import court_pack_service
from app.services.submission_engine import (
    TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ,
    ensure_template_solicitud_concurso_pj,
    resolve_template_fields,
)

router = APIRouter(prefix="/cases/{case_id}/court-pack", tags=["court-pack"])


def _require_case(db: Session, case_id: str) -> Case:
    c = db.query(Case).filter(Case.case_id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return c


class CaseProfileSnapshotResponse(BaseModel):
    case_id: str
    template_code: str
    created_at_utc: str
    storage_path: str
    resolved_fields: dict[str, Any]
    missing_required: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


@router.post("/case-profile/snapshot", response_model=CaseProfileSnapshotResponse)
def snapshot_case_profile(
    case_id: str, db: Session = Depends(get_db)
) -> CaseProfileSnapshotResponse:
    """
    Genera un snapshot determinista desde BD para rellenar la solicitud:
    - Fuente: submission_engine.resolve_template_fields sobre TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ
    - Persistencia: clients_data/cases/<case_id>/court_pack/inputs/case_profile.json
    """
    _require_case(db, case_id)

    # Ensure template catalog exists
    _ = ensure_template_solicitud_concurso_pj(db)

    rr = resolve_template_fields(
        db, case_id=case_id, template_code=TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ
    )

    case_root = settings.data_dir / "cases" / case_id
    paths = court_pack_service.ensure_court_pack_dirs(case_root)
    out_path = paths["inputs_dir"] / "case_profile.json"

    payload = {
        "case_id": case_id,
        "template_code": TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "resolved_fields": rr.resolved_fields,
        "missing_required": rr.missing_required,
        "warnings": rr.warnings,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return CaseProfileSnapshotResponse(
        case_id=case_id,
        template_code=TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ,
        created_at_utc=payload["created_at_utc"],
        storage_path=str(out_path),
        resolved_fields=rr.resolved_fields,
        missing_required=rr.missing_required,
        warnings=rr.warnings,
    )


@router.get("/files")
def get_court_pack_file(
    case_id: str,
    rel_path: str = Query(
        ..., description="Ruta relativa dentro de court_pack/, p.ej. attachments/<id>__file.pdf"
    ),
) -> FileResponse:
    """
    Servir ficheros del court_pack por HTTP (para previsualización en UI).
    Seguridad:
      - Solo permite prefijos: attachments/ y generated/
      - Bloquea path traversal y rutas absolutas
    """
    case_root = settings.data_dir / "cases" / case_id
    court_pack_root = case_root / "court_pack"

    # Normalize and validate rel_path
    rel_path = (rel_path or "").lstrip("/").replace("\\", "/")
    if not (rel_path.startswith("attachments/") or rel_path.startswith("generated/")):
        raise HTTPException(status_code=400, detail="rel_path fuera de scope")
    if ".." in rel_path.split("/"):
        raise HTTPException(status_code=400, detail="rel_path inválido")

    target = (court_pack_root / rel_path).resolve()
    if not str(target).startswith(str(court_pack_root.resolve())):
        raise HTTPException(status_code=400, detail="rel_path inválido")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Fichero no encontrado")

    # Best-effort media type
    suffix = target.suffix.lower()
    media_type = "application/octet-stream"
    if suffix == ".pdf":
        media_type = "application/pdf"
    elif suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        media_type = f"image/{suffix.lstrip('.')}".replace("jpg", "jpeg")
    elif suffix in (".txt", ".md"):
        media_type = "text/plain; charset=utf-8"
    elif suffix == ".json":
        media_type = "application/json; charset=utf-8"
    elif suffix == ".csv":
        media_type = "text/csv; charset=utf-8"

    # Inline so iframe/object can render it
    headers = {"Content-Disposition": f'inline; filename="{target.name}"'}
    return FileResponse(path=str(target), media_type=media_type, headers=headers)
