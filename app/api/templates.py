"""
API — Catálogo de plantillas + valores manuales por caso.

MVP:
- Plantilla: Solicitud de concurso voluntario PJ
- Gestionar campos manuales (form_field_values)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.case import Case
from app.models.case_central import FieldMapping, FormFieldValue, MappingSourceKind, Template, TemplateField
from app.services.submission_engine import (
    TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ,
    TEMPLATE_CODE_MEMORIA_ECONOMICA_JURIDICA,
    TEMPLATE_CODE_INFORME_ADMIN_CONCURSAL,
    ensure_template_solicitud_concurso_pj,
    ensure_template_memoria_economica_juridica,
    ensure_template_informe_admin_concursal,
)


router = APIRouter(prefix="/cases/{case_id}/templates", tags=["templates"])


def _require_case(db: Session, case_id: str) -> Case:
    c = db.query(Case).filter(Case.case_id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return c


def _get_template(db: Session, template_code: str) -> Template:
    if template_code == TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ:
        return ensure_template_solicitud_concurso_pj(db)
    if template_code == TEMPLATE_CODE_MEMORIA_ECONOMICA_JURIDICA:
        return ensure_template_memoria_economica_juridica(db)
    if template_code == TEMPLATE_CODE_INFORME_ADMIN_CONCURSAL:
        return ensure_template_informe_admin_concursal(db)
    tpl = db.query(Template).filter(Template.code == template_code, Template.is_active.is_(True)).first()
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Plantilla no encontrada: {template_code}")
    return tpl


def _is_no_consta_value(value_json: dict) -> bool:
    inner = value_json.get("text", value_json.get("value", value_json.get("number")))
    if inner is None:
        return False
    return str(inner).strip().upper() == "NO CONSTA"


class TemplateFieldView(BaseModel):
    field_key: str
    label: str
    data_type: str
    required: bool
    value_json: Optional[dict] = None
    evidence_id: Optional[str] = None
    justification: Optional[str] = None

    model_config = {"extra": "forbid"}


class TemplateFieldsResponse(BaseModel):
    template_id: str
    template_code: str
    fields: list[TemplateFieldView]

    model_config = {"extra": "forbid"}


class UpsertFieldValue(BaseModel):
    field_key: str = Field(..., min_length=2, max_length=120)
    value_json: dict = Field(..., description="Ej: {'text':'...'} o {'value':'...'} o {'number': 123}")
    evidence_id: Optional[str] = None
    justification: Optional[str] = None
    updated_by: str = Field(..., min_length=2, max_length=100)

    model_config = {"extra": "forbid"}


class UpsertValuesRequest(BaseModel):
    values: list[UpsertFieldValue] = Field(..., min_length=1)

    model_config = {"extra": "forbid"}


class UpsertValuesResponse(BaseModel):
    updated: int

    model_config = {"extra": "forbid"}


class FormFieldValueSummary(BaseModel):
    """
    Resumen de un valor manual (form_field_values) existente para poder enlazar evidencia.
    """

    value_id: str
    template_code: str
    field_key: str
    field_label: Optional[str] = None
    updated_by: str
    updated_at: str

    model_config = {"extra": "forbid"}


class ListFormFieldValuesResponse(BaseModel):
    items: list[FormFieldValueSummary] = Field(default_factory=list)
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=200)
    total: int = Field(0, ge=0)

    model_config = {"extra": "forbid"}


class TemplateFieldCatalogItem(BaseModel):
    field_id: str
    template_code: str
    field_key: str
    label: str

    model_config = {"extra": "forbid"}


class ListTemplateFieldsResponse(BaseModel):
    items: list[TemplateFieldCatalogItem] = Field(default_factory=list)
    total: int = Field(0, ge=0)
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

    model_config = {"extra": "forbid"}


@router.get("/{template_code}/fields", response_model=TemplateFieldsResponse)
def get_template_fields(case_id: str, template_code: str, db: Session = Depends(get_db)) -> TemplateFieldsResponse:
    _require_case(db, case_id)
    tpl = _get_template(db, template_code)
    fields = db.query(TemplateField).filter(TemplateField.template_id == tpl.template_id).all()
    existing = (
        db.query(FormFieldValue)
        .filter(FormFieldValue.case_id == case_id, FormFieldValue.template_id == tpl.template_id)
        .all()
    )
    by_key = {v.field_key: v for v in existing}
    out: list[TemplateFieldView] = []
    for f in fields:
        v = by_key.get(f.field_key)
        out.append(
            TemplateFieldView(
                field_key=f.field_key,
                label=f.label,
                data_type=f.data_type,
                required=bool(f.required),
                value_json=v.value_json if v else None,
                evidence_id=v.evidence_id if v else None,
                justification=v.justification if v else None,
            )
        )
    return TemplateFieldsResponse(template_id=tpl.template_id, template_code=tpl.code, fields=out)


@router.put("/{template_code}/values", response_model=UpsertValuesResponse)
def upsert_template_values(
    case_id: str, template_code: str, req: UpsertValuesRequest, db: Session = Depends(get_db)
) -> UpsertValuesResponse:
    _require_case(db, case_id)
    tpl = _get_template(db, template_code)
    # Cargar definición de campos para reglas de NO_CONSTA crítico
    fields = db.query(TemplateField).filter(TemplateField.template_id == tpl.template_id).all()
    by_key = {f.field_key: f for f in fields}
    updated = 0
    for entry in req.values:
        f = by_key.get(entry.field_key)
        if not f:
            raise HTTPException(status_code=404, detail=f"Campo no encontrado en plantilla: {entry.field_key}")
        if isinstance(entry.value_json, dict) and _is_no_consta_value(entry.value_json):
            vcfg = f.validation_json or {}
            if vcfg.get("critical"):
                rule = (vcfg.get("no_consta") or {}) if isinstance(vcfg.get("no_consta"), dict) else {}
                min_len = int(rule.get("justification_min") or 20)
                evidence_required = bool(rule.get("evidence_required"))
                just = (entry.justification or "").strip()
                if len(just) < min_len:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Campo crítico {entry.field_key}: NO CONSTA requiere justification (mín {min_len})",
                    )
                if evidence_required and not entry.evidence_id:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Campo crítico {entry.field_key}: NO CONSTA requiere evidence_id",
                    )
        row = (
            db.query(FormFieldValue)
            .filter(
                FormFieldValue.case_id == case_id,
                FormFieldValue.template_id == tpl.template_id,
                FormFieldValue.field_key == entry.field_key,
            )
            .first()
        )
        if not row:
            row = FormFieldValue(
                case_id=case_id,
                template_id=tpl.template_id,
                field_key=entry.field_key,
                value_json=entry.value_json,
                evidence_id=entry.evidence_id,
                justification=entry.justification,
                updated_by=entry.updated_by,
            )
            db.add(row)
        else:
            row.value_json = entry.value_json
            row.evidence_id = entry.evidence_id
            row.justification = entry.justification
            row.updated_by = entry.updated_by
        updated += 1
    db.commit()
    return UpsertValuesResponse(updated=updated)


class FieldMappingView(BaseModel):
    field_key: str
    label: Optional[str] = None
    required: bool
    source_kind: str
    source_spec_json: dict
    fallback: str
    critical: bool = False
    validation_json: Optional[dict] = None

    model_config = {"extra": "forbid"}


class TemplateMappingResponse(BaseModel):
    template_id: str
    template_code: str
    items: list[FieldMappingView]
    missing_mappings: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


@router.get("/{template_code}/mapping", response_model=TemplateMappingResponse)
def get_template_mapping(case_id: str, template_code: str, db: Session = Depends(get_db)) -> TemplateMappingResponse:
    _require_case(db, case_id)
    tpl = _get_template(db, template_code)
    fields = db.query(TemplateField).filter(TemplateField.template_id == tpl.template_id).all()
    mappings = db.query(FieldMapping).filter(FieldMapping.template_id == tpl.template_id).all()
    mapping_by_key = {m.field_key: m for m in mappings}

    items: list[FieldMappingView] = []
    missing: list[str] = []
    for f in fields:
        m = mapping_by_key.get(f.field_key)
        if not m:
            missing.append(f.field_key)
            # Regla explícita: si falta mapping, se considera MANUAL para depuración.
            items.append(
                FieldMappingView(
                    field_key=f.field_key,
                    label=f.label,
                    required=bool(f.required),
                    source_kind=MappingSourceKind.MANUAL.value,
                    source_spec_json={"kind": "manual"},
                    fallback="MANUAL_REQUIRED" if f.required else "EMPTY",
                    critical=bool((f.validation_json or {}).get("critical")),
                    validation_json=f.validation_json,
                )
            )
            continue
        items.append(
            FieldMappingView(
                field_key=f.field_key,
                label=f.label,
                required=bool(f.required),
                source_kind=m.source_kind,
                source_spec_json=m.source_spec_json,
                fallback=m.fallback,
                critical=bool((f.validation_json or {}).get("critical")),
                validation_json=f.validation_json,
            )
        )

    return TemplateMappingResponse(
        template_id=tpl.template_id,
        template_code=tpl.code,
        items=items,
        missing_mappings=missing,
    )


@router.get("/fields", response_model=ListTemplateFieldsResponse)
def list_template_fields_catalog(
    case_id: str,
    q: str = Query("", max_length=200, description="Busca en template_code, field_key, label"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    active_only: bool = Query(True, description="Si true, solo plantillas activas"),
    db: Session = Depends(get_db),
) -> ListTemplateFieldsResponse:
    """
    Catálogo global de TemplateFields (para enlazar evidencia a form_field sin depender de FormFieldValue).
    record_id canónico = TemplateField.field_id
    """
    _require_case(db, case_id)

    qn = (q or "").strip()
    q_like = f"%{qn}%"

    base = db.query(TemplateField, Template.code).join(Template, Template.template_id == TemplateField.template_id)
    if active_only:
        base = base.filter(Template.is_active.is_(True))
    if qn:
        base = base.filter(
            (Template.code.ilike(q_like)) | (TemplateField.field_key.ilike(q_like)) | (TemplateField.label.ilike(q_like))
        )

    total = int(base.count())
    rows = (
        base.order_by(Template.code.asc(), TemplateField.field_key.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items: list[TemplateFieldCatalogItem] = []
    for tf, template_code in rows:
        items.append(
            TemplateFieldCatalogItem(
                field_id=tf.field_id,
                template_code=str(template_code),
                field_key=tf.field_key,
                label=tf.label,
            )
        )
    return ListTemplateFieldsResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/form-field-values", response_model=ListFormFieldValuesResponse)
def list_form_field_values(
    case_id: str,
    q: str = Query("", max_length=200, description="Filtro opcional (template_code/field_key/label)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ListFormFieldValuesResponse:
    """
    Lista valores manuales existentes (`form_field_values`) para el caso, con info de plantilla/campo.

    Nota: esto NO crea ni modifica valores. Solo sirve para poder enlazar evidencia a un form_field real.
    """
    _require_case(db, case_id)

    qn = (q or "").strip().lower()

    base = (
        db.query(FormFieldValue, Template.code, TemplateField.label)
        .join(Template, Template.template_id == FormFieldValue.template_id)
        .outerjoin(
            TemplateField,
            (TemplateField.template_id == FormFieldValue.template_id)
            & (TemplateField.field_key == FormFieldValue.field_key),
        )
        .filter(FormFieldValue.case_id == case_id)
    )

    if qn:
        # Filtro simple por template_code / field_key / label
        base = base.filter(
            (Template.code.ilike(f"%{qn}%"))
            | (FormFieldValue.field_key.ilike(f"%{qn}%"))
            | (TemplateField.label.ilike(f"%{qn}%"))
        )

    total = int(base.count())

    rows = (
        base.order_by(FormFieldValue.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items: list[FormFieldValueSummary] = []
    for ffv, template_code, field_label in rows:
        updated_at = ffv.updated_at.isoformat() if isinstance(ffv.updated_at, datetime) else str(ffv.updated_at)
        items.append(
            FormFieldValueSummary(
                value_id=ffv.value_id,
                template_code=str(template_code),
                field_key=ffv.field_key,
                field_label=field_label,
                updated_by=ffv.updated_by,
                updated_at=updated_at,
            )
        )

    return ListFormFieldValuesResponse(items=items, page=page, page_size=page_size, total=total)

