"""
API — CAPA 5: Submissions (acto) + snapshot + generación de outputs.

Objetivo:
- Representar el acto (submission) que puede generar múltiples documentos.
- Resolver plantilla → validar → snapshot → generar → descargar.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.case import Case
from app.models.case_central import (
    AuditAction,
    CaseGeneratedDocument,
    CaseRecordAudit,
    CaseSubmission,
    CaseSubmissionTemplate,
    SubmissionStatus,
    SubmissionTarget,
    Template,
)
from app.services.submission_engine import (
    TEMPLATE_CODE_INFORME_ADMIN_CONCURSAL,
    TEMPLATE_CODE_MEMORIA_ECONOMICA_JURIDICA,
    TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ,
    ensure_template_informe_admin_concursal,
    ensure_template_memoria_economica_juridica,
    ensure_template_solicitud_concurso_pj,
    generate_submission_output_docx,
    resolve_template_fields,
    snapshot_submission,
    validate_resolved_fields,
)

router = APIRouter(prefix="/cases/{case_id}/submissions", tags=["submissions"])


def _require_case(db: Session, case_id: str) -> Case:
    c = db.query(Case).filter(Case.case_id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return c


def _get_template(db: Session, template_code: str) -> Template:
    # Seed plantillas conocidas (CAPA 5)
    if template_code == TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ:
        return ensure_template_solicitud_concurso_pj(db)
    if template_code == TEMPLATE_CODE_MEMORIA_ECONOMICA_JURIDICA:
        return ensure_template_memoria_economica_juridica(db)
    if template_code == TEMPLATE_CODE_INFORME_ADMIN_CONCURSAL:
        return ensure_template_informe_admin_concursal(db)

    tpl = db.query(Template).filter(Template.code == template_code).first()
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Plantilla no encontrada: {template_code}")
    return tpl


class CreateSubmissionRequest(BaseModel):
    target: str = Field(..., description="JUZGADO/ADMIN_CONCURSAL/CLIENTE/INTERNO")
    reference: Optional[str] = Field(None, max_length=200)
    created_by: str = Field(..., min_length=2, max_length=100)
    notes: Optional[str] = None

    model_config = {"extra": "forbid"}


class SubmissionSummary(BaseModel):
    submission_id: str
    case_id: str
    target: str
    status: str
    reference: Optional[str] = None
    created_by: str
    created_at: str
    presented_at: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "forbid"}


class ListSubmissionsResponse(BaseModel):
    items: list[SubmissionSummary] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0

    model_config = {"extra": "forbid"}


class ResolveTemplateRequest(BaseModel):
    template_code: str = Field(..., min_length=3, max_length=120)

    model_config = {"extra": "forbid"}


class ResolveTemplateResponse(BaseModel):
    template_code: str
    template_id: str
    resolved_fields: dict[str, Any]
    missing_required: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class ValidateResponse(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class SnapshotResponse(BaseModel):
    snapshot_id: str
    created_items: int

    model_config = {"extra": "forbid"}


class GeneratedDocumentSummary(BaseModel):
    generated_id: str
    submission_id: str
    template_id: str
    snapshot_id: Optional[str] = None
    format: str
    storage_path: str
    content_hash: str
    generated_at: str

    model_config = {"extra": "forbid"}


class GenerateResponse(BaseModel):
    generated: GeneratedDocumentSummary

    model_config = {"extra": "forbid"}


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., min_length=3, max_length=20)
    presented_at: Optional[str] = Field(None, description="ISO date-time opcional")
    actor: Optional[str] = Field(None, min_length=2, max_length=100)
    reason: Optional[str] = Field(None, min_length=10, max_length=500)

    model_config = {"extra": "forbid"}


class SnapshotRequest(BaseModel):
    template_code: str = Field(..., min_length=3, max_length=120)
    actor: Optional[str] = Field(None, min_length=2, max_length=100)
    reason: Optional[str] = Field(None, min_length=10, max_length=500)

    model_config = {"extra": "forbid"}


class GenerateRequest(BaseModel):
    template_code: str = Field(..., min_length=3, max_length=120)
    actor: Optional[str] = Field(None, min_length=2, max_length=100)
    reason: Optional[str] = Field(None, min_length=10, max_length=500)

    model_config = {"extra": "forbid"}


class AddSubmissionTemplateRequest(BaseModel):
    template_code: str = Field(..., min_length=3, max_length=120)
    actor: str = Field(..., min_length=2, max_length=100)
    reason: str = Field(..., min_length=10, max_length=500)

    model_config = {"extra": "forbid"}


class SubmissionTemplateSummary(BaseModel):
    template_id: str
    template_code: str
    added_by: str
    added_at: str

    model_config = {"extra": "forbid"}


class ListSubmissionTemplatesResponse(BaseModel):
    items: list[SubmissionTemplateSummary] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


def _audit_submission(
    *,
    db: Session,
    case_id: str,
    submission_id: str,
    action: str,
    actor: str,
    reason: str,
    before: Optional[dict[str, Any]],
    after: Optional[dict[str, Any]],
) -> None:
    # record_type canónico para submissions: usamos 'other' + record_id=submission_id
    db.add(
        CaseRecordAudit(
            case_id=case_id,
            record_type="other",
            logical_id=None,
            record_id=submission_id,
            action=action,
            actor=actor,
            justification=reason,
            before_json=before,
            after_json=after,
        )
    )


@router.post("", response_model=SubmissionSummary, status_code=status.HTTP_201_CREATED)
def create_submission(
    case_id: str, req: CreateSubmissionRequest, db: Session = Depends(get_db)
) -> SubmissionSummary:
    _require_case(db, case_id)

    if req.target not in {t.value for t in SubmissionTarget}:
        raise HTTPException(status_code=400, detail=f"target inválido: {req.target}")

    row = CaseSubmission(
        case_id=case_id,
        target=req.target,
        status=SubmissionStatus.BORRADOR.value,
        reference=req.reference,
        created_by=req.created_by,
        created_at=datetime.utcnow(),
        notes=req.notes,
    )
    db.add(row)
    db.flush()
    _audit_submission(
        db=db,
        case_id=case_id,
        submission_id=row.submission_id,
        action=AuditAction.SUBMISSION_CREATE.value,
        actor=req.created_by,
        # Blindaje: case_record_audit exige justification >= 10
        reason=(
            (req.notes or "").strip()
            if len((req.notes or "").strip()) >= 10
            else "Crear submission (CAPA 5)"
        ),
        before=None,
        after={
            "submission_id": row.submission_id,
            "target": row.target,
            "status": row.status,
            "reference": row.reference,
        },
    )
    db.commit()
    db.refresh(row)
    return SubmissionSummary(
        submission_id=row.submission_id,
        case_id=row.case_id,
        target=row.target,
        status=row.status,
        reference=row.reference,
        created_by=row.created_by,
        created_at=row.created_at.isoformat(),
        presented_at=row.presented_at.isoformat() if row.presented_at else None,
        notes=row.notes,
    )


@router.get("", response_model=ListSubmissionsResponse)
def list_submissions(
    case_id: str,
    *,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ListSubmissionsResponse:
    _require_case(db, case_id)

    q = db.query(CaseSubmission).filter(CaseSubmission.case_id == case_id)
    total = q.count()
    rows = (
        q.order_by(CaseSubmission.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items: list[SubmissionSummary] = []
    for r in rows:
        items.append(
            SubmissionSummary(
                submission_id=r.submission_id,
                case_id=r.case_id,
                target=r.target,
                status=r.status,
                reference=r.reference,
                created_by=r.created_by,
                created_at=r.created_at.isoformat(),
                presented_at=r.presented_at.isoformat() if r.presented_at else None,
                notes=r.notes,
            )
        )
    return ListSubmissionsResponse(items=items, page=page, page_size=page_size, total=total)


@router.post("/{submission_id}/resolve", response_model=ResolveTemplateResponse)
def resolve_template(
    case_id: str, submission_id: str, req: ResolveTemplateRequest, db: Session = Depends(get_db)
) -> ResolveTemplateResponse:
    _require_case(db, case_id)
    sub = (
        db.query(CaseSubmission)
        .filter(CaseSubmission.case_id == case_id, CaseSubmission.submission_id == submission_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Submission no encontrada")

    tpl = _get_template(db, req.template_code)

    res = resolve_template_fields(db, case_id=case_id, template_code=tpl.code)
    return ResolveTemplateResponse(
        template_code=tpl.code,
        template_id=tpl.template_id,
        resolved_fields=res.resolved_fields,
        missing_required=res.missing_required,
        warnings=res.warnings,
    )


@router.post("/{submission_id}/validate", response_model=ValidateResponse)
def validate_submission(
    case_id: str,
    submission_id: str,
    req: ResolveTemplateRequest,
    db: Session = Depends(get_db),
) -> ValidateResponse:
    _require_case(db, case_id)
    sub = (
        db.query(CaseSubmission)
        .filter(CaseSubmission.case_id == case_id, CaseSubmission.submission_id == submission_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Submission no encontrada")

    tpl = _get_template(db, req.template_code)

    res = resolve_template_fields(db, case_id=case_id, template_code=tpl.code)
    out = validate_resolved_fields(
        db, case_id=case_id, template=tpl, resolved_fields=res.resolved_fields
    )
    return ValidateResponse(ok=bool(out["ok"]), errors=list(out["errors"]))


@router.post("/{submission_id}/snapshot", response_model=SnapshotResponse)
def freeze_snapshot(
    case_id: str,
    submission_id: str,
    req: SnapshotRequest,
    db: Session = Depends(get_db),
) -> SnapshotResponse:
    _require_case(db, case_id)
    sub = (
        db.query(CaseSubmission)
        .filter(CaseSubmission.case_id == case_id, CaseSubmission.submission_id == submission_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Submission no encontrada")

    tpl = _get_template(db, req.template_code)

    res = resolve_template_fields(db, case_id=case_id, template_code=tpl.code)
    validation = validate_resolved_fields(
        db, case_id=case_id, template=tpl, resolved_fields=res.resolved_fields
    )
    if not validation["ok"]:
        raise HTTPException(status_code=409, detail={"errors": validation["errors"]})

    created = snapshot_submission(
        db,
        case_id=case_id,
        submission_id=submission_id,
        template=tpl,
        resolved_fields=res.resolved_fields,
    )
    snapshot_id, created_items = created

    actor = req.actor or sub.created_by
    reason = req.reason or f"SNAPSHOT_CREATE: {tpl.code}"
    _audit_submission(
        db=db,
        case_id=case_id,
        submission_id=submission_id,
        action=AuditAction.SNAPSHOT_CREATE.value,
        actor=actor,
        reason=reason,
        before=None,
        after={
            "template_code": tpl.code,
            "snapshot_id": snapshot_id,
            "created_items": int(created_items),
        },
    )
    # Marcar LISTO (si está en BORRADOR)
    if sub.status == SubmissionStatus.BORRADOR.value:
        before_status = sub.status
        sub.status = SubmissionStatus.LISTO.value
        _audit_submission(
            db=db,
            case_id=case_id,
            submission_id=submission_id,
            action=AuditAction.SUBMISSION_STATUS_CHANGE.value,
            actor=actor,
            reason=reason,
            before={"status": before_status},
            after={"status": sub.status},
        )
        db.commit()
    return SnapshotResponse(snapshot_id=snapshot_id, created_items=int(created_items))


@router.post("/{submission_id}/generate", response_model=GenerateResponse)
def generate_output(
    case_id: str,
    submission_id: str,
    req: GenerateRequest,
    db: Session = Depends(get_db),
) -> GenerateResponse:
    _require_case(db, case_id)
    sub = (
        db.query(CaseSubmission)
        .filter(CaseSubmission.case_id == case_id, CaseSubmission.submission_id == submission_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Submission no encontrada")
    if sub.status not in (SubmissionStatus.LISTO.value, SubmissionStatus.PRESENTADO.value):
        raise HTTPException(status_code=409, detail="Submission debe estar LISTO antes de generar")

    tpl = _get_template(db, req.template_code)

    res = resolve_template_fields(db, case_id=case_id, template_code=tpl.code)

    # Blindaje reproducibilidad: siempre generar snapshot y enlazarlo al output.
    snapshot_id, created_items = snapshot_submission(
        db,
        case_id=case_id,
        submission_id=submission_id,
        template=tpl,
        resolved_fields=res.resolved_fields,
    )
    actor = req.actor or sub.created_by
    reason = req.reason or f"OUTPUT_GENERATE: {tpl.code}"
    _audit_submission(
        db=db,
        case_id=case_id,
        submission_id=submission_id,
        action=AuditAction.SNAPSHOT_CREATE.value,
        actor=actor,
        reason=reason,
        before=None,
        after={
            "template_code": tpl.code,
            "snapshot_id": snapshot_id,
            "created_items": int(created_items),
        },
    )

    gen = generate_submission_output_docx(
        db,
        case_id=case_id,
        submission_id=submission_id,
        template=tpl,
        resolved_fields=res.resolved_fields,
        snapshot_id=snapshot_id,
    )
    _audit_submission(
        db=db,
        case_id=case_id,
        submission_id=submission_id,
        action=AuditAction.OUTPUT_GENERATE.value,
        actor=actor,
        reason=reason,
        before=None,
        after={
            "template_code": tpl.code,
            "generated_id": gen.generated_id,
            "format": gen.format,
            "content_hash": gen.content_hash,
            "snapshot_id": snapshot_id,
        },
    )
    db.commit()

    return GenerateResponse(
        generated=GeneratedDocumentSummary(
            generated_id=gen.generated_id,
            submission_id=gen.submission_id,
            template_id=gen.template_id,
            snapshot_id=getattr(gen, "snapshot_id", None),
            format=gen.format,
            storage_path=gen.storage_path,
            content_hash=gen.content_hash,
            generated_at=gen.generated_at.isoformat(),
        )
    )


@router.patch("/{submission_id}/status", response_model=SubmissionSummary)
def update_submission_status(
    case_id: str,
    submission_id: str,
    req: UpdateStatusRequest,
    db: Session = Depends(get_db),
) -> SubmissionSummary:
    _require_case(db, case_id)
    sub = (
        db.query(CaseSubmission)
        .filter(CaseSubmission.case_id == case_id, CaseSubmission.submission_id == submission_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Submission no encontrada")

    if req.status not in {s.value for s in SubmissionStatus}:
        raise HTTPException(status_code=400, detail=f"status inválido: {req.status}")
    actor = (req.actor or "").strip()
    reason = (req.reason or "").strip()
    if req.status != sub.status:
        if len(actor) < 2 or len(reason) < 10:
            raise HTTPException(
                status_code=422, detail="actor y reason son obligatorios para cambiar status"
            )
        before = {
            "status": sub.status,
            "presented_at": sub.presented_at.isoformat() if sub.presented_at else None,
        }
        sub.status = req.status
        after = {"status": sub.status}
    else:
        before = None
        after = None

    if req.status == SubmissionStatus.PRESENTADO.value and not sub.presented_at:
        sub.presented_at = datetime.utcnow()
        if after is not None:
            after["presented_at"] = sub.presented_at.isoformat()
    if req.status != sub.status:
        # (nunca ocurre; protegido arriba)
        pass
    if before is not None or after is not None:
        _audit_submission(
            db=db,
            case_id=case_id,
            submission_id=submission_id,
            action=AuditAction.SUBMISSION_STATUS_CHANGE.value,
            actor=actor,
            reason=reason,
            before=before,
            after=after,
        )
    db.commit()
    db.refresh(sub)
    return SubmissionSummary(
        submission_id=sub.submission_id,
        case_id=sub.case_id,
        target=sub.target,
        status=sub.status,
        reference=sub.reference,
        created_by=sub.created_by,
        created_at=sub.created_at.isoformat(),
        presented_at=sub.presented_at.isoformat() if sub.presented_at else None,
        notes=sub.notes,
    )


@router.get("/{submission_id}/generated", response_model=list[GeneratedDocumentSummary])
def list_generated_documents(
    case_id: str,
    submission_id: str,
    db: Session = Depends(get_db),
) -> list[GeneratedDocumentSummary]:
    _require_case(db, case_id)
    rows = (
        db.query(CaseGeneratedDocument)
        .filter(
            CaseGeneratedDocument.case_id == case_id,
            CaseGeneratedDocument.submission_id == submission_id,
        )
        .order_by(CaseGeneratedDocument.generated_at.desc())
        .all()
    )
    out: list[GeneratedDocumentSummary] = []
    for r in rows:
        out.append(
            GeneratedDocumentSummary(
                generated_id=r.generated_id,
                submission_id=r.submission_id,
                template_id=r.template_id,
                snapshot_id=getattr(r, "snapshot_id", None),
                format=r.format,
                storage_path=r.storage_path,
                content_hash=r.content_hash,
                generated_at=r.generated_at.isoformat() if r.generated_at else "",
            )
        )
    return out


@router.post("/{submission_id}/templates", response_model=SubmissionTemplateSummary)
def add_submission_template(
    case_id: str,
    submission_id: str,
    req: AddSubmissionTemplateRequest,
    db: Session = Depends(get_db),
) -> SubmissionTemplateSummary:
    _require_case(db, case_id)
    sub = (
        db.query(CaseSubmission)
        .filter(CaseSubmission.case_id == case_id, CaseSubmission.submission_id == submission_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Submission no encontrada")

    tpl = _get_template(db, req.template_code)

    existing = (
        db.query(CaseSubmissionTemplate)
        .filter(
            CaseSubmissionTemplate.submission_id == submission_id,
            CaseSubmissionTemplate.template_id == tpl.template_id,
        )
        .first()
    )
    if existing:
        return SubmissionTemplateSummary(
            template_id=tpl.template_id,
            template_code=tpl.code,
            added_by=existing.added_by,
            added_at=existing.added_at.isoformat() if existing.added_at else "",
        )

    link = CaseSubmissionTemplate(
        submission_id=submission_id,
        case_id=case_id,
        template_id=tpl.template_id,
        added_by=req.actor,
    )
    db.add(link)
    db.flush()
    _audit_submission(
        db=db,
        case_id=case_id,
        submission_id=submission_id,
        action=AuditAction.UPDATE.value,
        actor=req.actor,
        reason=req.reason,
        before=None,
        after={
            "submission_template_add": {"template_code": tpl.code, "template_id": tpl.template_id}
        },
    )
    db.commit()
    db.refresh(link)
    return SubmissionTemplateSummary(
        template_id=tpl.template_id,
        template_code=tpl.code,
        added_by=link.added_by,
        added_at=link.added_at.isoformat() if link.added_at else "",
    )


@router.get("/{submission_id}/templates", response_model=ListSubmissionTemplatesResponse)
def list_submission_templates(
    case_id: str,
    submission_id: str,
    db: Session = Depends(get_db),
) -> ListSubmissionTemplatesResponse:
    _require_case(db, case_id)
    sub = (
        db.query(CaseSubmission)
        .filter(CaseSubmission.case_id == case_id, CaseSubmission.submission_id == submission_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Submission no encontrada")

    rows = (
        db.query(CaseSubmissionTemplate, Template.code)
        .join(Template, Template.template_id == CaseSubmissionTemplate.template_id)
        .filter(
            CaseSubmissionTemplate.submission_id == submission_id,
            CaseSubmissionTemplate.case_id == case_id,
        )
        .order_by(CaseSubmissionTemplate.added_at.desc())
        .all()
    )
    items: list[SubmissionTemplateSummary] = []
    for link, code in rows:
        items.append(
            SubmissionTemplateSummary(
                template_id=link.template_id,
                template_code=str(code),
                added_by=link.added_by,
                added_at=link.added_at.isoformat() if link.added_at else "",
            )
        )
    return ListSubmissionTemplatesResponse(items=items)


@router.get("/{submission_id}/generated/{generated_id}/download", response_class=FileResponse)
def download_generated_document(
    case_id: str,
    submission_id: str,
    generated_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    _require_case(db, case_id)
    gen = (
        db.query(CaseGeneratedDocument)
        .filter(
            CaseGeneratedDocument.case_id == case_id,
            CaseGeneratedDocument.submission_id == submission_id,
            CaseGeneratedDocument.generated_id == generated_id,
        )
        .first()
    )
    if not gen:
        raise HTTPException(status_code=404, detail="Documento generado no encontrado")
    if not gen.storage_path or not os.path.exists(gen.storage_path):
        raise HTTPException(status_code=404, detail="Fichero no disponible en disco")

    filename = os.path.basename(gen.storage_path)
    return FileResponse(
        gen.storage_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )
