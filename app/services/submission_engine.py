from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.case_central import (
    CaseGeneratedDocument,
    CaseRecordEvidence,
    CaseSubmissionItem,
    FieldMapping,
    FormFieldValue,
    MappingFallback,
    MappingSourceKind,
    OutputFormat,
    SubmissionTarget,
    Template,
    TemplateField,
    stable_json_hash,
)
from app.models.situation import (
    SituationAsset,
    SituationCourtRecord,
    SituationCredit,
    SituationInvoice,
    SituationPublicDebt,
)

TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ = "JUZ_SOL_CONCURSO_VOLUNTARIO_PJ"
TEMPLATE_CODE_MEMORIA_ECONOMICA_JURIDICA = "MEMORIA_ECONOMICA_JURIDICA"
TEMPLATE_CODE_INFORME_ADMIN_CONCURSAL = "INFORME_ADMIN_CONCURSAL"
GENERATOR_VERSION = "submissions_v1"


def _is_no_consta_value(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip().upper() == "NO CONSTA"
    if isinstance(v, dict):
        inner = v.get("text", v.get("value", v.get("number")))
        if inner is None:
            return False
        return str(inner).strip().upper() == "NO CONSTA"
    return False


def _get_manual_value_row(
    db: Session, *, case_id: str, template_id: str, field_key: str
) -> Optional[FormFieldValue]:
    return (
        db.query(FormFieldValue)
        .filter(
            FormFieldValue.case_id == case_id,
            FormFieldValue.template_id == template_id,
            FormFieldValue.field_key == field_key,
        )
        .first()
    )


@dataclass
class ResolveResult:
    template: Template
    resolved_fields: dict[str, Any]
    missing_required: list[str]
    warnings: list[str]


def ensure_template_solicitud_concurso_pj(db: Session) -> Template:
    """
    Crea (si no existe) el catálogo mínimo de:
    - templates
    - template_fields
    - field_mapping

    para la plantilla: Solicitud concurso voluntario (persona jurídica).
    """
    tpl = db.query(Template).filter(Template.code == TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ).first()
    if tpl:
        # Migración suave para instalaciones existentes:
        # En versiones previas, debtor.tax_id y debtor.address se marcaban como MANUAL.
        # Ahora intentamos resolverlos desde BD (situation_*), manteniendo MANUAL como fallback.
        try:
            existing = {
                m.field_key: m
                for m in db.query(FieldMapping)
                .filter(FieldMapping.template_id == tpl.template_id)
                .all()
            }
            desired: dict[str, tuple[str, dict, str]] = {
                "debtor.tax_id": (
                    MappingSourceKind.AGGREGATION.value,
                    {"kind": "debtor_tax_id_best_effort"},
                    MappingFallback.MANUAL_REQUIRED.value,
                ),
                "debtor.address": (
                    MappingSourceKind.AGGREGATION.value,
                    {"kind": "debtor_address_best_effort"},
                    MappingFallback.MANUAL_REQUIRED.value,
                ),
            }
            changed = False
            for field_key, (sk, spec, fb) in desired.items():
                cur = existing.get(field_key)
                if cur:
                    if (
                        cur.source_kind != sk
                        or (cur.source_spec_json or {}).get("kind") != spec.get("kind")
                        or cur.fallback != fb
                    ):
                        cur.source_kind = sk
                        cur.source_spec_json = spec
                        cur.fallback = fb
                        changed = True
                else:
                    db.add(
                        FieldMapping(
                            template_id=tpl.template_id,
                            field_key=field_key,
                            source_kind=sk,
                            source_spec_json=spec,
                            fallback=fb,
                        )
                    )
                    changed = True
            if changed:
                db.commit()
        except Exception:
            db.rollback()
        return tpl

    tpl = Template(
        code=TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ,
        target=SubmissionTarget.JUZGADO.value,
        version="v1",
        name="Solicitud de concurso voluntario (persona jurídica)",
        is_active=True,
    )
    db.add(tpl)
    db.flush()

    # Campos mínimos (MVP) basados en el formulario PJ:
    fields: list[tuple[str, str, str, bool]] = [
        ("debtor.name", "Denominación social", "string", True),
        ("debtor.tax_id", "CIF", "string", True),
        ("debtor.register_data", "Datos registrales", "string", False),
        ("debtor.object_activity", "Objeto / actividad principal", "string", False),
        ("debtor.address", "Domicilio social", "string", True),
        ("insolvency.kind", "Clase de insolvencia (ACTUAL/INMINENTE)", "string", True),
        ("insolvency.facts", "Hechos que derivan la insolvencia (breve)", "string", True),
        ("company.ceased_activity", "¿Ha cesado su actividad? (SI/NO)", "string", False),
        ("workers.count", "Número de trabajadores", "number", True),
        ("totals.asset_value", "Valoración del activo", "number", True),
        ("totals.cash", "Tesorería", "number", True),
        ("totals.passive_amount", "Cuantía del pasivo", "number", True),
        ("creditors.count", "Número de acreedores", "number", True),
    ]

    # Validación por campo (si quieres endurecer fallback NO_CONSTA, marca critical + requisitos)
    critical_cfg: dict[str, dict[str, Any]] = {
        "debtor.tax_id": {
            "critical": True,
            "no_consta": {"justification_min": 20, "evidence_required": True},
        },
        "debtor.address": {
            "critical": True,
            "no_consta": {"justification_min": 20, "evidence_required": False},
        },
        "insolvency.kind": {
            "critical": True,
            "no_consta": {"justification_min": 20, "evidence_required": False},
        },
        "insolvency.facts": {
            "critical": True,
            "no_consta": {"justification_min": 20, "evidence_required": False},
        },
        "workers.count": {
            "critical": True,
            "no_consta": {"justification_min": 20, "evidence_required": False},
        },
        "totals.passive_amount": {
            "critical": True,
            "no_consta": {"justification_min": 20, "evidence_required": False},
        },
        "creditors.count": {
            "critical": True,
            "no_consta": {"justification_min": 20, "evidence_required": False},
        },
        "totals.asset_value": {
            "critical": False,
            "no_consta": {"justification_min": 20, "evidence_required": False},
        },
        "totals.cash": {
            "critical": True,
            "no_consta": {"justification_min": 20, "evidence_required": False},
        },
    }

    for field_key, label, dtype, required in fields:
        db.add(
            TemplateField(
                template_id=tpl.template_id,
                field_key=field_key,
                label=label,
                data_type=dtype,
                required=bool(required),
                validation_json=critical_cfg.get(field_key),
            )
        )

    # Mapping:
    # - debtor.name: del Case.name (si existe)
    # - totales: agregaciones sobre situation_* (vigentes)
    # - el resto: MANUAL (porque hoy no existe en Case/BD)
    mappings: list[tuple[str, str, dict, str]] = [
        (
            "debtor.name",
            MappingSourceKind.AGGREGATION.value,
            {"kind": "case_name"},
            MappingFallback.MANUAL_REQUIRED.value,
        ),
        (
            "totals.passive_amount",
            MappingSourceKind.AGGREGATION.value,
            {"kind": "sum_passive"},
            MappingFallback.NO_CONSTA.value,
        ),
        (
            "totals.asset_value",
            MappingSourceKind.AGGREGATION.value,
            {"kind": "sum_assets_best_valuation"},
            MappingFallback.NO_CONSTA.value,
        ),
        (
            "creditors.count",
            MappingSourceKind.AGGREGATION.value,
            {"kind": "count_creditors_distinct"},
            MappingFallback.NO_CONSTA.value,
        ),
        # tesorería no existe estructurada en MVP
        (
            "totals.cash",
            MappingSourceKind.MANUAL.value,
            {"kind": "manual"},
            MappingFallback.MANUAL_REQUIRED.value,
        ),
        # Deudor: intentar desde BD (best-effort) y dejar manual como fallback
        (
            "debtor.tax_id",
            MappingSourceKind.AGGREGATION.value,
            {"kind": "debtor_tax_id_best_effort"},
            MappingFallback.MANUAL_REQUIRED.value,
        ),
        (
            "debtor.register_data",
            MappingSourceKind.MANUAL.value,
            {"kind": "manual"},
            MappingFallback.EMPTY.value,
        ),
        (
            "debtor.object_activity",
            MappingSourceKind.MANUAL.value,
            {"kind": "manual"},
            MappingFallback.EMPTY.value,
        ),
        (
            "debtor.address",
            MappingSourceKind.AGGREGATION.value,
            {"kind": "debtor_address_best_effort"},
            MappingFallback.MANUAL_REQUIRED.value,
        ),
        (
            "insolvency.kind",
            MappingSourceKind.MANUAL.value,
            {"kind": "manual"},
            MappingFallback.MANUAL_REQUIRED.value,
        ),
        (
            "insolvency.facts",
            MappingSourceKind.MANUAL.value,
            {"kind": "manual"},
            MappingFallback.MANUAL_REQUIRED.value,
        ),
        (
            "company.ceased_activity",
            MappingSourceKind.MANUAL.value,
            {"kind": "manual"},
            MappingFallback.EMPTY.value,
        ),
        (
            "workers.count",
            MappingSourceKind.MANUAL.value,
            {"kind": "manual"},
            MappingFallback.MANUAL_REQUIRED.value,
        ),
    ]

    for field_key, source_kind, spec, fallback in mappings:
        db.add(
            FieldMapping(
                template_id=tpl.template_id,
                field_key=field_key,
                source_kind=source_kind,
                source_spec_json=spec,
                fallback=fallback,
            )
        )

    db.commit()
    db.refresh(tpl)
    return tpl


def ensure_template_memoria_economica_juridica(db: Session) -> Template:
    tpl = (
        db.query(Template).filter(Template.code == TEMPLATE_CODE_MEMORIA_ECONOMICA_JURIDICA).first()
    )
    if tpl:
        return tpl

    tpl = Template(
        code=TEMPLATE_CODE_MEMORIA_ECONOMICA_JURIDICA,
        target=SubmissionTarget.JUZGADO.value,
        version="v1",
        name="Memoria económica y jurídica (esqueleto)",
        is_active=True,
    )
    db.add(tpl)
    db.flush()

    fields: list[tuple[str, str, str, bool, Optional[dict[str, Any]]]] = [
        (
            "debtor.name",
            "Denominación social",
            "string",
            True,
            {"critical": True, "no_consta": {"justification_min": 20, "evidence_required": False}},
        ),
        (
            "debtor.tax_id",
            "CIF/NIF",
            "string",
            True,
            {"critical": True, "no_consta": {"justification_min": 20, "evidence_required": True}},
        ),
        (
            "totals.passive_amount",
            "Cuantía del pasivo (estimación)",
            "number",
            True,
            {"critical": True, "no_consta": {"justification_min": 20, "evidence_required": False}},
        ),
        (
            "totals.asset_value",
            "Valoración del activo (mejor estimación)",
            "number",
            True,
            {"critical": True, "no_consta": {"justification_min": 20, "evidence_required": False}},
        ),
        (
            "creditors.count",
            "Número de acreedores (estimación)",
            "number",
            True,
            {"critical": True, "no_consta": {"justification_min": 20, "evidence_required": False}},
        ),
        ("invoices.list", "Listado de facturas vigentes (resumen)", "json", False, None),
        ("credits.list", "Listado de créditos vigentes (resumen)", "json", False, None),
        ("notes", "Notas / observaciones", "string", False, None),
    ]

    for field_key, label, dtype, required, vjson in fields:
        db.add(
            TemplateField(
                template_id=tpl.template_id,
                field_key=field_key,
                label=label,
                data_type=dtype,
                required=bool(required),
                validation_json=vjson,
            )
        )

    mappings: list[tuple[str, str, dict, str]] = [
        (
            "debtor.name",
            MappingSourceKind.AGGREGATION.value,
            {"kind": "case_name"},
            MappingFallback.MANUAL_REQUIRED.value,
        ),
        (
            "debtor.tax_id",
            MappingSourceKind.MANUAL.value,
            {"kind": "manual"},
            MappingFallback.MANUAL_REQUIRED.value,
        ),
        (
            "totals.passive_amount",
            MappingSourceKind.AGGREGATION.value,
            {"kind": "sum_passive"},
            MappingFallback.NO_CONSTA.value,
        ),
        (
            "totals.asset_value",
            MappingSourceKind.AGGREGATION.value,
            {"kind": "sum_assets_best_valuation"},
            MappingFallback.NO_CONSTA.value,
        ),
        (
            "creditors.count",
            MappingSourceKind.AGGREGATION.value,
            {"kind": "count_creditors_distinct"},
            MappingFallback.NO_CONSTA.value,
        ),
        (
            "invoices.list",
            MappingSourceKind.SQL_QUERY.value,
            {
                "entity": "invoice",
                "aggregation": "list",
                "fields": [
                    "supplier",
                    "invoice_number",
                    "issue_date",
                    "due_date",
                    "currency",
                    "amount_total",
                ],
                "limit": 200,
            },
            MappingFallback.EMPTY.value,
        ),
        (
            "credits.list",
            MappingSourceKind.SQL_QUERY.value,
            {
                "entity": "loan",
                "aggregation": "list",
                "fields": [
                    "creditor",
                    "contract_ref",
                    "currency",
                    "amount_total",
                    "secured",
                    "maturity_date",
                ],
                "limit": 200,
            },
            MappingFallback.EMPTY.value,
        ),
        ("notes", MappingSourceKind.MANUAL.value, {"kind": "manual"}, MappingFallback.EMPTY.value),
    ]

    for field_key, source_kind, spec, fallback in mappings:
        db.add(
            FieldMapping(
                template_id=tpl.template_id,
                field_key=field_key,
                source_kind=source_kind,
                source_spec_json=spec,
                fallback=fallback,
            )
        )

    db.commit()
    db.refresh(tpl)
    return tpl


def ensure_template_informe_admin_concursal(db: Session) -> Template:
    tpl = db.query(Template).filter(Template.code == TEMPLATE_CODE_INFORME_ADMIN_CONCURSAL).first()
    if tpl:
        return tpl

    tpl = Template(
        code=TEMPLATE_CODE_INFORME_ADMIN_CONCURSAL,
        target=SubmissionTarget.ADMIN_CONCURSAL.value,
        version="v1",
        name="Informe de Administración Concursal (esqueleto)",
        is_active=True,
    )
    db.add(tpl)
    db.flush()

    fields: list[tuple[str, str, str, bool, Optional[dict[str, Any]]]] = [
        (
            "case.name",
            "Identificación del caso",
            "string",
            True,
            {"critical": True, "no_consta": {"justification_min": 20, "evidence_required": False}},
        ),
        (
            "totals.passive_amount",
            "Total pasivo (estimación)",
            "number",
            True,
            {"critical": True, "no_consta": {"justification_min": 20, "evidence_required": False}},
        ),
        ("public_debt.total", "Total deuda pública (estimación)", "number", False, None),
        ("assets.list", "Listado de bienes (resumen)", "json", False, None),
        (
            "court_claims.list",
            "Listado de actuaciones/procedimientos (resumen)",
            "json",
            False,
            None,
        ),
        ("observations", "Observaciones AC", "string", False, None),
    ]

    for field_key, label, dtype, required, vjson in fields:
        db.add(
            TemplateField(
                template_id=tpl.template_id,
                field_key=field_key,
                label=label,
                data_type=dtype,
                required=bool(required),
                validation_json=vjson,
            )
        )

    mappings: list[tuple[str, str, dict, str]] = [
        (
            "case.name",
            MappingSourceKind.AGGREGATION.value,
            {"kind": "case_name"},
            MappingFallback.MANUAL_REQUIRED.value,
        ),
        (
            "totals.passive_amount",
            MappingSourceKind.AGGREGATION.value,
            {"kind": "sum_passive"},
            MappingFallback.NO_CONSTA.value,
        ),
        (
            "public_debt.total",
            MappingSourceKind.SQL_QUERY.value,
            {"entity": "public_debt", "aggregation": "sum", "column": "amount_total"},
            MappingFallback.NO_CONSTA.value,
        ),
        (
            "assets.list",
            MappingSourceKind.SQL_QUERY.value,
            {
                "entity": "asset",
                "aggregation": "list",
                "fields": [
                    "asset_type",
                    "description",
                    "currency",
                    "valuation_admin_concursal",
                    "valuation_external",
                ],
                "limit": 200,
            },
            MappingFallback.EMPTY.value,
        ),
        (
            "court_claims.list",
            MappingSourceKind.SQL_QUERY.value,
            {
                "entity": "court_claim",
                "aggregation": "list",
                "fields": ["court", "procedure_number", "action_type", "action_date", "status"],
                "limit": 200,
            },
            MappingFallback.EMPTY.value,
        ),
        (
            "observations",
            MappingSourceKind.MANUAL.value,
            {"kind": "manual"},
            MappingFallback.EMPTY.value,
        ),
    ]

    for field_key, source_kind, spec, fallback in mappings:
        db.add(
            FieldMapping(
                template_id=tpl.template_id,
                field_key=field_key,
                source_kind=source_kind,
                source_spec_json=spec,
                fallback=fallback,
            )
        )

    db.commit()
    db.refresh(tpl)
    return tpl


def _get_case(db: Session, case_id: str) -> Case:
    c = db.query(Case).filter(Case.case_id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return c


def _manual_value(db: Session, case_id: str, template_id: str, field_key: str) -> Optional[dict]:
    row = (
        db.query(FormFieldValue)
        .filter(
            FormFieldValue.case_id == case_id,
            FormFieldValue.template_id == template_id,
            FormFieldValue.field_key == field_key,
        )
        .first()
    )
    return row.value_json if row else None


def _agg_case_name(db: Session, case_id: str) -> Optional[str]:
    return _get_case(db, case_id).name


def _first_non_empty(values: list[object]) -> Optional[str]:
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if not s or s.lower() == "none":
            continue
        return s
    return None


def _agg_debtor_tax_id_best_effort(db: Session, case_id: str) -> Optional[str]:
    """
    CIF/NIF del deudor desde BD (best-effort).
    Regla:
    - Preferir deuda pública (taxpayer_tax_id)
    - Fallback a facturas (buyer_tax_id)
    """
    try:
        rows = (
            db.query(SituationPublicDebt.taxpayer_tax_id)
            .filter(
                SituationPublicDebt.case_id == case_id, SituationPublicDebt.is_current.is_(True)
            )
            .order_by(SituationPublicDebt.created_at.desc())
            .limit(200)
            .all()
        )
        got = _first_non_empty([x[0] for x in rows if x])
        if got:
            return got
    except Exception:
        pass

    try:
        rows = (
            db.query(SituationInvoice.buyer_tax_id)
            .filter(SituationInvoice.case_id == case_id, SituationInvoice.is_current.is_(True))
            .order_by(SituationInvoice.created_at.desc())
            .limit(200)
            .all()
        )
        got = _first_non_empty([x[0] for x in rows if x])
        if got:
            return got
    except Exception:
        pass

    return None


def _agg_debtor_address_best_effort(db: Session, case_id: str) -> Optional[str]:
    """
    Domicilio del deudor desde BD (best-effort).
    Regla:
    - Facturas (buyer_address)
    """
    try:
        rows = (
            db.query(SituationInvoice.buyer_address)
            .filter(SituationInvoice.case_id == case_id, SituationInvoice.is_current.is_(True))
            .order_by(SituationInvoice.created_at.desc())
            .limit(200)
            .all()
        )
        got = _first_non_empty([x[0] for x in rows if x])
        if got:
            return got
    except Exception:
        pass
    return None


def _sum_passive(db: Session, case_id: str) -> float:
    inv = (
        db.query(SituationInvoice.amount_total)
        .filter(SituationInvoice.case_id == case_id, SituationInvoice.is_current.is_(True))
        .all()
    )
    cred = (
        db.query(SituationCredit.amount_total)
        .filter(SituationCredit.case_id == case_id, SituationCredit.is_current.is_(True))
        .all()
    )
    pub = (
        db.query(SituationPublicDebt.amount_total)
        .filter(SituationPublicDebt.case_id == case_id, SituationPublicDebt.is_current.is_(True))
        .all()
    )
    court = (
        db.query(SituationCourtRecord.amount_claimed)
        .filter(SituationCourtRecord.case_id == case_id, SituationCourtRecord.is_current.is_(True))
        .all()
    )
    total = 0.0
    total += sum(float(x[0] or 0.0) for x in inv)
    total += sum(float(x[0] or 0.0) for x in cred)
    total += sum(float(x[0] or 0.0) for x in pub)
    total += sum(float(x[0] or 0.0) for x in court)
    return float(total)


def _sum_assets_best_valuation(db: Session, case_id: str) -> float:
    rows = (
        db.query(
            SituationAsset.valuation_admin_concursal,
            SituationAsset.valuation_external,
        )
        .filter(SituationAsset.case_id == case_id, SituationAsset.is_current.is_(True))
        .all()
    )
    total = 0.0
    for val_ac, val_ext in rows:
        best = val_ac if val_ac is not None else val_ext
        total += float(best or 0.0)
    return float(total)


def _count_creditors_distinct(db: Session, case_id: str) -> int:
    suppliers = (
        db.query(SituationInvoice.supplier)
        .filter(SituationInvoice.case_id == case_id, SituationInvoice.is_current.is_(True))
        .all()
    )
    creditors = (
        db.query(SituationCredit.creditor)
        .filter(SituationCredit.case_id == case_id, SituationCredit.is_current.is_(True))
        .all()
    )
    pub = (
        db.query(SituationPublicDebt.authority)
        .filter(SituationPublicDebt.case_id == case_id, SituationPublicDebt.is_current.is_(True))
        .all()
    )
    names = set()
    names.update([x[0].strip() for x in suppliers if x and x[0] and x[0].strip()])
    names.update([x[0].strip() for x in creditors if x and x[0] and x[0].strip()])
    names.update([x[0].strip() for x in pub if x and x[0] and x[0].strip()])
    return int(len(names))


def resolve_template_fields(db: Session, *, case_id: str, template_code: str) -> ResolveResult:
    tpl = (
        db.query(Template)
        .filter(Template.code == template_code, Template.is_active.is_(True))
        .first()
    )
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Plantilla no encontrada: {template_code}")

    fields = db.query(TemplateField).filter(TemplateField.template_id == tpl.template_id).all()
    mappings = {
        m.field_key: m
        for m in db.query(FieldMapping).filter(FieldMapping.template_id == tpl.template_id).all()
    }

    resolved: dict[str, Any] = {}
    missing_required: list[str] = []
    warnings: list[str] = []

    for f in fields:
        # Regla de oro: si el abogado ya guardó un valor manual para este field_key,
        # debe prevalecer SIEMPRE sobre cualquier auto-resolución (BD/aggregations/SQL).
        try:
            mv = _manual_value(db, case_id, tpl.template_id, f.field_key)
            if isinstance(mv, dict):
                inner = mv.get("value", mv.get("text", mv.get("number")))
                if inner is not None:
                    if not (isinstance(inner, str) and not inner.strip()):
                        resolved[f.field_key] = mv
                        continue
        except Exception:
            pass

        mapping = mappings.get(f.field_key)
        if not mapping:
            # Sin mapping => regla explícita: manual por defecto.
            val = _manual_value(db, case_id, tpl.template_id, f.field_key)
            if val is None and f.required:
                missing_required.append(f.field_key)
            resolved[f.field_key] = val
            continue

        if mapping.source_kind == MappingSourceKind.MANUAL.value:
            val = _manual_value(db, case_id, tpl.template_id, f.field_key)
            if val is None:
                if mapping.fallback == MappingFallback.NO_CONSTA.value:
                    warnings.append(
                        f"{f.field_key}: fallback NO_CONSTA (requiere valor manual 'NO CONSTA')"
                    )
                if f.required and mapping.fallback in (
                    MappingFallback.MANUAL_REQUIRED.value,
                    MappingFallback.NO_CONSTA.value,
                ):
                    missing_required.append(f.field_key)
                resolved[f.field_key] = None
            else:
                resolved[f.field_key] = val
            continue

        if mapping.source_kind == MappingSourceKind.CONSTANT.value:
            resolved[f.field_key] = mapping.source_spec_json.get("value")
            continue

        if mapping.source_kind == MappingSourceKind.AGGREGATION.value:
            kind = (mapping.source_spec_json or {}).get("kind")
            try:
                if kind == "case_name":
                    resolved[f.field_key] = _agg_case_name(db, case_id)
                elif kind == "debtor_tax_id_best_effort":
                    resolved[f.field_key] = _agg_debtor_tax_id_best_effort(db, case_id)
                elif kind == "debtor_address_best_effort":
                    resolved[f.field_key] = _agg_debtor_address_best_effort(db, case_id)
                elif kind == "sum_passive":
                    resolved[f.field_key] = _sum_passive(db, case_id)
                elif kind == "sum_assets_best_valuation":
                    resolved[f.field_key] = _sum_assets_best_valuation(db, case_id)
                elif kind == "count_creditors_distinct":
                    resolved[f.field_key] = _count_creditors_distinct(db, case_id)
                else:
                    resolved[f.field_key] = None
                    warnings.append(f"{f.field_key}: aggregation kind desconocido: {kind}")
            except Exception as e:
                resolved[f.field_key] = None
                warnings.append(f"{f.field_key}: error agregando: {e}")

            if resolved.get(f.field_key) is None and f.required:
                if mapping.fallback == MappingFallback.NO_CONSTA.value:
                    missing_required.append(f.field_key)
                elif mapping.fallback == MappingFallback.MANUAL_REQUIRED.value:
                    missing_required.append(f.field_key)
            continue

        if mapping.source_kind == MappingSourceKind.SQL_QUERY.value:
            spec = mapping.source_spec_json or {}
            entity = (spec.get("entity") or "").strip()
            agg = (spec.get("aggregation") or "first_non_null").strip()
            limit = int(spec.get("limit") or 200)

            model = None
            if entity == "invoice":
                model = SituationInvoice
                base_q = db.query(SituationInvoice).filter(
                    SituationInvoice.case_id == case_id, SituationInvoice.is_current.is_(True)
                )
            elif entity == "loan":
                model = SituationCredit
                base_q = db.query(SituationCredit).filter(
                    SituationCredit.case_id == case_id, SituationCredit.is_current.is_(True)
                )
            elif entity == "asset":
                model = SituationAsset
                base_q = db.query(SituationAsset).filter(
                    SituationAsset.case_id == case_id, SituationAsset.is_current.is_(True)
                )
            elif entity == "public_debt":
                model = SituationPublicDebt
                base_q = db.query(SituationPublicDebt).filter(
                    SituationPublicDebt.case_id == case_id, SituationPublicDebt.is_current.is_(True)
                )
            elif entity == "court_claim":
                model = SituationCourtRecord
                base_q = db.query(SituationCourtRecord).filter(
                    SituationCourtRecord.case_id == case_id,
                    SituationCourtRecord.is_current.is_(True),
                )
            else:
                model = None
                base_q = None

            if not model or base_q is None:
                resolved[f.field_key] = None
                warnings.append(f"{f.field_key}: SQL_QUERY entity inválida: {entity}")
                if f.required and mapping.fallback in (
                    MappingFallback.NO_CONSTA.value,
                    MappingFallback.MANUAL_REQUIRED.value,
                ):
                    missing_required.append(f.field_key)
                continue

            # Por defecto: newest first
            try:
                base_q = base_q.order_by(getattr(model, "created_at").desc())
            except Exception:
                pass

            if agg == "list":
                fields_sel = list(spec.get("fields") or [])
                rows = base_q.limit(limit).all()
                out_rows: list[dict[str, Any]] = []
                for r in rows:
                    out_rows.append({k: getattr(r, k, None) for k in fields_sel})
                resolved[f.field_key] = out_rows
                continue

            if agg == "sum":
                col = (spec.get("column") or "").strip()
                total = 0.0
                ok_any = False
                for r in base_q.all():
                    v = getattr(r, col, None)
                    if v is None:
                        continue
                    try:
                        total += float(v)
                        ok_any = True
                    except Exception:
                        continue
                resolved[f.field_key] = total if ok_any else None
                if (
                    resolved.get(f.field_key) is None
                    and f.required
                    and mapping.fallback
                    in (
                        MappingFallback.NO_CONSTA.value,
                        MappingFallback.MANUAL_REQUIRED.value,
                    )
                ):
                    missing_required.append(f.field_key)
                continue

            # first_non_null (default)
            col = (spec.get("column") or "").strip()
            if not col:
                resolved[f.field_key] = None
                warnings.append(f"{f.field_key}: SQL_QUERY requiere column para aggregation={agg}")
                if f.required and mapping.fallback in (
                    MappingFallback.NO_CONSTA.value,
                    MappingFallback.MANUAL_REQUIRED.value,
                ):
                    missing_required.append(f.field_key)
                continue

            got = None
            for r in base_q.limit(limit).all():
                v = getattr(r, col, None)
                if v is None:
                    continue
                if isinstance(v, str) and not v.strip():
                    continue
                got = v
                break
            resolved[f.field_key] = got
            if (
                resolved.get(f.field_key) is None
                and f.required
                and mapping.fallback
                in (
                    MappingFallback.NO_CONSTA.value,
                    MappingFallback.MANUAL_REQUIRED.value,
                )
            ):
                missing_required.append(f.field_key)
            continue

        # source_kind desconocido
        resolved[f.field_key] = None
        if f.required:
            missing_required.append(f.field_key)
        warnings.append(f"{f.field_key}: source_kind desconocido: {mapping.source_kind}")

    return ResolveResult(
        template=tpl, resolved_fields=resolved, missing_required=missing_required, warnings=warnings
    )


def validate_resolved_fields(
    db: Session, *, case_id: str, template: Template, resolved_fields: dict[str, Any]
) -> dict[str, Any]:
    # Validación conservadora: required no nulo/empty y tipos básicos.
    fields = db.query(TemplateField).filter(TemplateField.template_id == template.template_id).all()
    field_by_key = {f.field_key: f for f in fields}

    errors: list[str] = []
    for k, f in field_by_key.items():
        if not f.required:
            continue
        v = resolved_fields.get(k)
        if v is None:
            errors.append(f"Falta campo requerido: {k}")
            continue
        # value_json manual suele ser dict; aceptamos {"value": ...} o {"text": ...}
        if isinstance(v, dict):
            inner = v.get("value", v.get("text", v.get("number")))
            if inner is None or (isinstance(inner, str) and not inner.strip()):
                errors.append(f"Campo requerido vacío: {k}")
        elif isinstance(v, str) and not v.strip():
            errors.append(f"Campo requerido vacío: {k}")

        # Reglas duras: NO_CONSTA en críticos => justification (y evidence si aplica)
        vcfg = f.validation_json or {}
        if vcfg.get("critical") and _is_no_consta_value(v):
            rule = (vcfg.get("no_consta") or {}) if isinstance(vcfg.get("no_consta"), dict) else {}
            min_len = int(rule.get("justification_min") or 20)
            evidence_required = bool(rule.get("evidence_required"))
            row = _get_manual_value_row(
                db, case_id=case_id, template_id=template.template_id, field_key=k
            )
            if not row:
                errors.append(
                    f"Campo crítico {k}: NO CONSTA requiere guardar valor manual con justificación"
                )
                continue
            just = (row.justification or "").strip()
            if len(just) < min_len:
                errors.append(
                    f"Campo crítico {k}: NO CONSTA requiere justificación (mín {min_len} caracteres)"
                )
            if evidence_required and not row.evidence_id:
                errors.append(
                    f"Campo crítico {k}: NO CONSTA requiere evidencia (evidence_id) además de justificación"
                )

    return {"ok": len(errors) == 0, "errors": errors}


def snapshot_submission(
    db: Session,
    *,
    case_id: str,
    submission_id: str,
    template: Template,
    resolved_fields: dict[str, Any],
) -> tuple[str, int]:
    """
    Crea un snapshot inmutable y devuelve (snapshot_id, created_items).

    Blindaje reproducibilidad:
    - Cada freeze crea un snapshot_id nuevo.
    - Los outputs generados se enlazan a snapshot_id (CaseGeneratedDocument.snapshot_id).
    """
    snapshot_id = str(uuid.uuid4())
    created = 0

    def _evidence_ids_for_record(
        *, record_type: str, record_id: Optional[str]
    ) -> Optional[list[str]]:
        if not record_id:
            return None
        rows = (
            db.query(CaseRecordEvidence.evidence_id)
            .filter(
                CaseRecordEvidence.case_id == case_id,
                CaseRecordEvidence.record_type == record_type,
                CaseRecordEvidence.record_id == record_id,
            )
            .order_by(CaseRecordEvidence.added_at.asc())
            .all()
        )
        out = [r[0] for r in rows if r and r[0]]
        return out or None

    # Snapshot 1: plantilla resuelta (campo-resuelto)
    snap_fields = {
        "template_code": template.code,
        "template_id": template.template_id,
        "template_version": template.version,
        "resolved_fields": resolved_fields,
    }
    db.add(
        CaseSubmissionItem(
            submission_id=submission_id,
            case_id=case_id,
            snapshot_id=snapshot_id,
            entity="template_resolve",
            record_type="form_field",
            logical_id=None,
            record_id=template.template_id,
            record_hash=stable_json_hash(snap_fields),
            snapshot_json=snap_fields,
            evidence_ids=None,
        )
    )
    created += 1

    # Snapshot 1.5: valores manuales (form_field_values) relevantes de esa plantilla
    fields = db.query(TemplateField).filter(TemplateField.template_id == template.template_id).all()
    field_keys = [f.field_key for f in fields]
    manual_values = (
        db.query(FormFieldValue)
        .filter(
            FormFieldValue.case_id == case_id, FormFieldValue.template_id == template.template_id
        )
        .all()
    )
    by_key = {v.field_key: v for v in manual_values}
    for k in field_keys:
        v = by_key.get(k)
        if not v:
            continue
        payload = {
            "template_code": template.code,
            "template_id": template.template_id,
            "field_key": v.field_key,
            "value_json": v.value_json,
            "evidence_id": v.evidence_id,
            "justification": v.justification,
            "updated_by": v.updated_by,
            "updated_at": v.updated_at.isoformat() if v.updated_at else None,
        }
        db.add(
            CaseSubmissionItem(
                submission_id=submission_id,
                case_id=case_id,
                snapshot_id=snapshot_id,
                entity="form_field_value",
                record_type="form_field",
                logical_id=None,
                record_id=v.value_id,
                record_hash=stable_json_hash(payload),
                snapshot_json=payload,
                evidence_ids=[v.evidence_id] if v.evidence_id else None,
            )
        )
        created += 1

    # Snapshot 2: entidades core vigentes (para reproducibilidad)
    def _snap_rows(entity: str, record_type: str, rows: list[Any], to_json) -> None:
        nonlocal created
        for r in rows:
            payload = to_json(r)
            db.add(
                CaseSubmissionItem(
                    submission_id=submission_id,
                    case_id=case_id,
                    snapshot_id=snapshot_id,
                    entity=entity,
                    record_type=record_type,
                    logical_id=getattr(r, "logical_id", None),
                    record_id=getattr(r, "record_id", None),
                    record_hash=stable_json_hash(payload),
                    snapshot_json=payload,
                    evidence_ids=_evidence_ids_for_record(
                        record_type=record_type, record_id=getattr(r, "record_id", None)
                    ),
                )
            )
            created += 1

    invoices = (
        db.query(SituationInvoice)
        .filter(SituationInvoice.case_id == case_id, SituationInvoice.is_current.is_(True))
        .order_by(SituationInvoice.created_at.desc())
        .all()
    )
    _snap_rows(
        "invoices",
        "invoice",
        invoices,
        lambda r: {
            "logical_id": r.logical_id,
            "record_id": r.record_id,
            "version": r.version,
            "supplier": r.supplier,
            "supplier_tax_id": r.supplier_tax_id,
            "supplier_address": r.supplier_address,
            "supplier_email": r.supplier_email,
            "buyer_name": r.buyer_name,
            "buyer_tax_id": r.buyer_tax_id,
            "buyer_address": r.buyer_address,
            "buyer_email": r.buyer_email,
            "invoice_number": r.invoice_number,
            "issue_date": r.issue_date,
            "due_date": r.due_date,
            "paid_date": r.paid_date,
            "currency": r.currency,
            "currency_fx_rate": r.currency_fx_rate,
            "base_amount": r.base_amount,
            "vat_amount": r.vat_amount,
            "withholding_amount": r.withholding_amount,
            "amount_total": r.amount_total,
            "status": r.status,
            "payment_terms": r.payment_terms,
            "payment_method": r.payment_method,
            "iban_masked": r.iban_masked,
            "invoice_type": r.invoice_type,
            "source_ref": r.source_ref,
            "is_disputed": r.is_disputed,
            "dispute_reason": r.dispute_reason,
            "notes": r.notes,
        },
    )

    credits = (
        db.query(SituationCredit)
        .filter(SituationCredit.case_id == case_id, SituationCredit.is_current.is_(True))
        .order_by(SituationCredit.created_at.desc())
        .all()
    )
    _snap_rows(
        "credits",
        "loan",
        credits,
        lambda r: {
            "logical_id": r.logical_id,
            "record_id": r.record_id,
            "version": r.version,
            "creditor": r.creditor,
            "creditor_tax_id": r.creditor_tax_id,
            "lender_address": r.lender_address,
            "lender_email": r.lender_email,
            "lender_phone": r.lender_phone,
            "contract_ref": r.contract_ref,
            "currency": r.currency,
            "amount_total": r.amount_total,
            "principal_initial": r.principal_initial,
            "outstanding_principal": r.outstanding_principal,
            "accrued_interest": r.accrued_interest,
            "interest_rate": r.interest_rate,
            "interest_type": r.interest_type,
            "spread": r.spread,
            "secured": r.secured,
            "guarantee_details": r.guarantee_details,
            "secured_type": r.secured_type,
            "collateral_description": r.collateral_description,
            "collateral_registry_ref": r.collateral_registry_ref,
            "guarantor_name": r.guarantor_name,
            "guarantor_tax_id": r.guarantor_tax_id,
            "maturity_date": r.maturity_date,
            "default_date": r.default_date,
            "last_payment_date": r.last_payment_date,
            "enforcement_stage": r.enforcement_stage,
            "procedure_ref": r.procedure_ref,
            "notes": r.notes,
        },
    )

    assets = (
        db.query(SituationAsset)
        .filter(SituationAsset.case_id == case_id, SituationAsset.is_current.is_(True))
        .order_by(SituationAsset.created_at.desc())
        .all()
    )
    _snap_rows(
        "assets",
        "asset",
        assets,
        lambda r: {
            "logical_id": r.logical_id,
            "record_id": r.record_id,
            "version": r.version,
            "asset_type": r.asset_type,
            "description": r.description,
            "location": r.location,
            "owner": r.owner,
            "ownership_share": r.ownership_share,
            "acquisition_date": r.acquisition_date,
            "acquisition_value": r.acquisition_value,
            "address_full": r.address_full,
            "city": r.city,
            "postal_code": r.postal_code,
            "province": r.province,
            "cadastral_ref": r.cadastral_ref,
            "registry_type": r.registry_type,
            "registry_ref": r.registry_ref,
            "finca_registral": r.finca_registral,
            "tomo": r.tomo,
            "libro": r.libro,
            "folio": r.folio,
            "currency": r.currency,
            "valuation_admin_concursal": r.valuation_admin_concursal,
            "valuation_external": r.valuation_external,
            "valuation_date": r.valuation_date,
            "liens": r.liens,
            "encumbrances_full": r.encumbrances_full,
            "mortgage_bank": r.mortgage_bank,
            "mortgage_outstanding": r.mortgage_outstanding,
            "disposal_status": r.disposal_status,
            "occupancy_status": r.occupancy_status,
            "notes": r.notes,
        },
    )

    public_debts = (
        db.query(SituationPublicDebt)
        .filter(SituationPublicDebt.case_id == case_id, SituationPublicDebt.is_current.is_(True))
        .order_by(SituationPublicDebt.created_at.desc())
        .all()
    )
    _snap_rows(
        "public_debts",
        "public_debt",
        public_debts,
        lambda r: {
            "logical_id": r.logical_id,
            "record_id": r.record_id,
            "version": r.version,
            "authority": r.authority,
            "taxpayer_name": r.taxpayer_name,
            "taxpayer_tax_id": r.taxpayer_tax_id,
            "concept": r.concept,
            "concept_code": r.concept_code,
            "period_start": r.period_start,
            "period_end": r.period_end,
            "period_key": r.period_key,
            "expediente_aplazamiento": r.expediente_aplazamiento,
            "aplazamiento_status": r.aplazamiento_status,
            "resolution_date": r.resolution_date,
            "currency": r.currency,
            "principal": r.principal,
            "surcharges": r.surcharges,
            "interest": r.interest,
            "penalties": r.penalties,
            "amount_total": r.amount_total,
            "deferred": r.deferred,
            "debt_status": r.debt_status,
            "enforcement_stage": r.enforcement_stage,
            "notes": r.notes,
        },
    )

    court = (
        db.query(SituationCourtRecord)
        .filter(SituationCourtRecord.case_id == case_id, SituationCourtRecord.is_current.is_(True))
        .order_by(SituationCourtRecord.created_at.desc())
        .all()
    )
    _snap_rows(
        "court_claims",
        "court_claim",
        court,
        lambda r: {
            "logical_id": r.logical_id,
            "record_id": r.record_id,
            "version": r.version,
            "court": r.court,
            "court_city": r.court_city,
            "court_section": r.court_section,
            "procedure_number": r.procedure_number,
            "autos_ref": r.autos_ref,
            "case_year": r.case_year,
            "case_role": r.case_role,
            "claimant": r.claimant,
            "party_counterparty_name": r.party_counterparty_name,
            "party_counterparty_tax_id": r.party_counterparty_tax_id,
            "party_counterparty_address": r.party_counterparty_address,
            "lawyer_name": r.lawyer_name,
            "procurator_name": r.procurator_name,
            "action_type": r.action_type,
            "action_date": r.action_date,
            "next_hearing_date": r.next_hearing_date,
            "currency": r.currency,
            "amount_claimed": r.amount_claimed,
            "amount_awarded": r.amount_awarded,
            "amount_paid": r.amount_paid,
            "status": r.status,
            "stage": r.stage,
            "milestones_json": r.milestones_json,
            "enforcement_flag": r.enforcement_flag,
            "seizures_notes": r.seizures_notes,
            "notes": r.notes,
        },
    )

    db.commit()
    return snapshot_id, created


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _resolved_value_to_string(v: Any) -> str:
    """
    Convierte valores resueltos (manual/mapping) a texto estable para DOCX.
    """
    if v is None:
        return "NO CONSTA"
    if isinstance(v, str):
        return v.strip() or "NO CONSTA"
    if isinstance(v, (int, float, bool)):
        return str(v)
    if isinstance(v, dict):
        inner = v.get("text", v.get("value", v.get("number")))
        if inner is None:
            return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return str(inner).strip() or "NO CONSTA"
    try:
        return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        return str(v)


def generate_docx_from_template_dump(
    *,
    db: Session,
    case: Case,
    template: Template,
    resolved_fields: dict[str, Any],
) -> bytes:
    """
    Generador DOCX genérico para cualquier plantilla:
    - Lista los TemplateField (label/field_key) y vuelca el valor resuelto.
    - Permite generar un output mínimo sin DOCX específico por plantilla.
    """
    try:
        from docx import Document  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"python-docx no disponible: {e}")

    fields = (
        db.query(TemplateField)
        .filter(TemplateField.template_id == template.template_id)
        .order_by(TemplateField.field_key.asc())
        .all()
    )

    doc = Document()
    doc.add_heading(template.name or template.code, level=1)
    doc.add_paragraph(f"Template: {template.code} (v{template.version})")
    doc.add_paragraph(f"Caso: {case.name} (case_id: {case.case_id})")
    doc.add_paragraph(f"Fecha generación: {datetime.utcnow().isoformat()}Z")

    doc.add_heading("Campos (volcado)", level=2)
    table = doc.add_table(rows=1, cols=4)
    hdr = table.rows[0].cells
    hdr[0].text = "field_key"
    hdr[1].text = "label"
    hdr[2].text = "required"
    hdr[3].text = "value"

    for f in fields:
        v = resolved_fields.get(f.field_key)
        s = _resolved_value_to_string(v)
        if len(s) > 8000:
            s = s[:8000] + "…(truncado)"
        row = table.add_row().cells
        row[0].text = f.field_key
        row[1].text = f.label
        row[2].text = "SI" if f.required else "NO"
        row[3].text = s

    import io

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def generate_docx_solicitud_concurso_pj(*, case: Case, resolved_fields: dict[str, Any]) -> bytes:
    """
    Genera un DOCX (MVP) con estructura equivalente al formulario PJ.
    NO rellena el PDF oficial; genera un pliego DOCX presentable desde plantilla.
    """
    try:
        from docx import Document  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"python-docx no disponible: {e}")

    def _get_text(key: str) -> str:
        v = resolved_fields.get(key)
        if v is None:
            return "NO CONSTA"
        if isinstance(v, dict):
            inner = v.get("text", v.get("value", v.get("number")))
            return str(inner) if inner is not None else "NO CONSTA"
        return str(v)

    doc = Document()
    doc.add_heading("SOLICITUD DE CONCURSO VOLUNTARIO (PERSONA JURÍDICA)", level=1)
    doc.add_paragraph(f"Caso: {case.name} (case_id: {case.case_id})")
    doc.add_paragraph(f"Fecha generación: {datetime.utcnow().date().isoformat()}")

    doc.add_heading("A) DATOS DEL DEUDOR", level=2)
    doc.add_paragraph(f"Denominación social: {_get_text('debtor.name')}")
    doc.add_paragraph(f"CIF: {_get_text('debtor.tax_id')}")
    doc.add_paragraph(f"Datos registrales: {_get_text('debtor.register_data')}")
    doc.add_paragraph(f"Objeto / actividad principal: {_get_text('debtor.object_activity')}")
    doc.add_paragraph(f"Domicilio social: {_get_text('debtor.address')}")

    doc.add_heading("C) DATOS DE LA INSOLVENCIA", level=2)
    doc.add_paragraph(f"Clase de insolvencia: {_get_text('insolvency.kind')}")
    doc.add_paragraph("Hechos (breve):")
    doc.add_paragraph(_get_text("insolvency.facts"))
    doc.add_paragraph(f"¿Ha cesado su actividad?: {_get_text('company.ceased_activity')}")

    doc.add_heading("Magnitudes", level=2)
    doc.add_paragraph(f"Nº trabajadores: {_get_text('workers.count')}")
    doc.add_paragraph(f"Valoración activo: {_get_text('totals.asset_value')}")
    doc.add_paragraph(f"Tesorería: {_get_text('totals.cash')}")
    doc.add_paragraph(f"Cuantía pasivo: {_get_text('totals.passive_amount')}")
    doc.add_paragraph(f"Nº acreedores: {_get_text('creditors.count')}")

    # Serializar a bytes
    import io

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def generate_submission_output_docx(
    db: Session,
    *,
    case_id: str,
    submission_id: str,
    template: Template,
    resolved_fields: dict[str, Any],
    snapshot_id: Optional[str] = None,
) -> CaseGeneratedDocument:
    case = _get_case(db, case_id)

    # Plantilla PJ: generador específico. Resto: generador genérico (volcado).
    if template.code == TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ:
        content = generate_docx_solicitud_concurso_pj(case=case, resolved_fields=resolved_fields)
    else:
        content = generate_docx_from_template_dump(
            db=db,
            case=case,
            template=template,
            resolved_fields=resolved_fields,
        )
    h = _sha256_bytes(content)

    # Guardar fichero en runtime/outputs (fuera de git, reproducible por hash)
    # Permite override para tests: PHOENIX_OUTPUT_DIR
    root = Path(os.getenv("PHOENIX_OUTPUT_DIR", str(Path("runtime") / "outputs")))
    base_dir = root / case_id / submission_id
    base_dir.mkdir(parents=True, exist_ok=True)
    # Nombre determinista por hash para reproducibilidad.
    filename = f"{template.code}_{h[:12]}.docx"
    out_path = base_dir / filename
    out_path.write_bytes(content)

    row = CaseGeneratedDocument(
        submission_id=submission_id,
        case_id=case_id,
        snapshot_id=snapshot_id,
        template_id=template.template_id,
        format=OutputFormat.DOCX.value,
        storage_path=str(out_path),
        content_hash=h,
        generator_version=GENERATOR_VERSION,
        metadata_json={"template_code": template.code, "snapshot_id": snapshot_id},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
