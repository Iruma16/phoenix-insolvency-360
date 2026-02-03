"""
API — Cuadro de situación (SQL) con evidencia obligatoria y auditoría append-only.

Reglas no negociables (MVP):
- Alta/edición requieren evidencia (≥1) y motivo (reason).
- Edición = nueva versión (append-only); el registro anterior deja de estar vigente.
"""

from __future__ import annotations

import io
import re
import uuid
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import AliasChoices, BaseModel, Field
from sqlalchemy import case as sa_case, func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.record_types import ENTITY_ALLOWED, record_type_from_entity
from app.models.case import Case
from app.models.case_central import AuditAction, CaseRecordAudit, CaseRecordEvidence
from app.models.document import Document
from app.models.situation import (
    SituationCourtRecord,
    SituationCredit,
    SituationInvoice,
    SituationAsset,
    SituationPublicDebt,
)


router = APIRouter(prefix="/cases/{case_id}/situation", tags=["situation"])


def _require_entity(entity: str) -> str:
    entity = (entity or "").strip().upper()
    if entity not in ENTITY_ALLOWED:
        raise HTTPException(status_code=400, detail=f"Entidad inválida: {entity}")
    return entity


# =========================================================
# Pydantic (requests / responses)
# =========================================================


class EvidenceInput(BaseModel):
    # Para DOCUMENTO: document_id obligatorio.
    # Para CLIENTE/CONTABILIDAD/CRITERIO_PROFESIONAL: document_id puede ser null.
    document_id: Optional[str] = Field(None, min_length=1)
    chunk_id: Optional[str] = None
    page: Optional[int] = Field(None, ge=1)
    note: str = Field(..., min_length=10, max_length=500)
    source_type: str = Field("DOCUMENTO", max_length=30)  # DOCUMENTO/CLIENTE/CONTABILIDAD/CRITERIO_PROFESIONAL
    certainty_level: str = Field("CONSTA", max_length=20)  # CONSTA/NO_CONSTA/ESTIMADO
    excerpt: Optional[str] = Field(None, max_length=1200)

    model_config = {"extra": "forbid"}


class _BaseUpsert(BaseModel):
    created_by: str = Field(..., min_length=2, max_length=100)
    reason: str = Field(..., min_length=10, max_length=500)
    evidence: list[EvidenceInput] = Field(..., min_length=1)

    model_config = {"extra": "forbid"}


class CreateInvoiceRequest(_BaseUpsert):
    supplier: str = Field(..., min_length=2, max_length=255, validation_alias=AliasChoices("supplier", "creditor_name"))
    supplier_tax_id: Optional[str] = Field(
        None, max_length=30, validation_alias=AliasChoices("supplier_tax_id", "creditor_tax_id")
    )
    supplier_address: Optional[str] = Field(None, max_length=300)
    supplier_email: Optional[str] = Field(None, max_length=120)

    buyer_name: Optional[str] = Field(None, max_length=255)
    buyer_tax_id: Optional[str] = Field(None, max_length=30)
    buyer_address: Optional[str] = Field(None, max_length=300)
    buyer_email: Optional[str] = Field(None, max_length=120)

    invoice_number: Optional[str] = Field(None, max_length=100)
    contract_ref: Optional[str] = Field(None, max_length=200)
    issue_date: Optional[str] = Field(None, max_length=10)
    due_date: Optional[str] = Field(None, max_length=10)
    paid_date: Optional[str] = Field(None, max_length=10)
    currency: str = Field("EUR", max_length=8)
    currency_fx_rate: Optional[float] = Field(None, ge=0.0)
    base_amount: Optional[float] = Field(None, ge=0.0)
    vat_amount: Optional[float] = Field(None, ge=0.0)
    withholding_amount: Optional[float] = Field(None, ge=0.0)
    amount_total: float = Field(0.0, ge=0.0)
    status: Optional[str] = Field(None, max_length=40)
    payment_terms: Optional[str] = Field(None, max_length=120)
    payment_method: Optional[str] = Field(None, max_length=60)
    iban_masked: Optional[str] = Field(None, max_length=34)
    invoice_type: Optional[str] = Field(None, max_length=40)
    source_ref: Optional[str] = Field(None, max_length=200)
    is_disputed: Optional[bool] = None
    dispute_reason: Optional[str] = None
    notes: Optional[str] = None


class UpdateInvoiceRequest(_BaseUpsert):
    logical_id: str = Field(..., min_length=1)
    expected_version: int = Field(..., ge=1)

    supplier: Optional[str] = Field(
        None, max_length=255, validation_alias=AliasChoices("supplier", "creditor_name")
    )
    supplier_tax_id: Optional[str] = Field(
        None, max_length=30, validation_alias=AliasChoices("supplier_tax_id", "creditor_tax_id")
    )
    supplier_address: Optional[str] = Field(None, max_length=300)
    supplier_email: Optional[str] = Field(None, max_length=120)

    buyer_name: Optional[str] = Field(None, max_length=255)
    buyer_tax_id: Optional[str] = Field(None, max_length=30)
    buyer_address: Optional[str] = Field(None, max_length=300)
    buyer_email: Optional[str] = Field(None, max_length=120)

    invoice_number: Optional[str] = Field(None, max_length=100)
    contract_ref: Optional[str] = Field(None, max_length=200)
    issue_date: Optional[str] = Field(None, max_length=10)
    due_date: Optional[str] = Field(None, max_length=10)
    paid_date: Optional[str] = Field(None, max_length=10)
    currency: Optional[str] = Field(None, max_length=8)
    currency_fx_rate: Optional[float] = Field(None, ge=0.0)
    base_amount: Optional[float] = Field(None, ge=0.0)
    vat_amount: Optional[float] = Field(None, ge=0.0)
    withholding_amount: Optional[float] = Field(None, ge=0.0)
    amount_total: Optional[float] = Field(None, ge=0.0)
    status: Optional[str] = Field(None, max_length=40)
    payment_terms: Optional[str] = Field(None, max_length=120)
    payment_method: Optional[str] = Field(None, max_length=60)
    iban_masked: Optional[str] = Field(None, max_length=34)
    invoice_type: Optional[str] = Field(None, max_length=40)
    source_ref: Optional[str] = Field(None, max_length=200)
    is_disputed: Optional[bool] = None
    dispute_reason: Optional[str] = None
    notes: Optional[str] = None


class CreateCreditRequest(_BaseUpsert):
    creditor: str = Field(..., min_length=2, max_length=255, validation_alias=AliasChoices("creditor", "lender_name"))
    creditor_tax_id: Optional[str] = Field(None, max_length=30)
    lender_address: Optional[str] = Field(None, max_length=300)
    lender_email: Optional[str] = Field(None, max_length=120)
    lender_phone: Optional[str] = Field(None, max_length=40)
    contract_ref: Optional[str] = Field(None, max_length=200)
    currency: str = Field("EUR", max_length=8)
    amount_total: float = Field(0.0, ge=0.0)
    principal_initial: Optional[float] = Field(None, ge=0.0)
    outstanding_principal: Optional[float] = Field(None, ge=0.0)
    accrued_interest: Optional[float] = Field(None, ge=0.0)
    interest_rate: Optional[float] = Field(None, ge=0.0, le=100.0)
    interest_type: Optional[str] = Field(None, max_length=20)
    spread: Optional[float] = Field(None, ge=0.0)
    secured: bool = False
    guarantee_details: Optional[str] = None
    secured_type: Optional[str] = Field(None, max_length=40)
    collateral_description: Optional[str] = None
    collateral_registry_ref: Optional[str] = Field(None, max_length=200)
    guarantor_name: Optional[str] = Field(None, max_length=255)
    guarantor_tax_id: Optional[str] = Field(None, max_length=30)
    maturity_date: Optional[str] = Field(None, max_length=10)
    default_date: Optional[str] = Field(None, max_length=10)
    last_payment_date: Optional[str] = Field(None, max_length=10)
    enforcement_stage: Optional[str] = Field(None, max_length=40)
    procedure_ref: Optional[str] = Field(None, max_length=120)
    notes: Optional[str] = None


class UpdateCreditRequest(_BaseUpsert):
    logical_id: str = Field(..., min_length=1)
    expected_version: int = Field(..., ge=1)

    creditor: Optional[str] = Field(
        None, max_length=255, validation_alias=AliasChoices("creditor", "lender_name")
    )
    creditor_tax_id: Optional[str] = Field(None, max_length=30)
    lender_address: Optional[str] = Field(None, max_length=300)
    lender_email: Optional[str] = Field(None, max_length=120)
    lender_phone: Optional[str] = Field(None, max_length=40)
    contract_ref: Optional[str] = Field(None, max_length=200)
    currency: Optional[str] = Field(None, max_length=8)
    amount_total: Optional[float] = Field(None, ge=0.0)
    principal_initial: Optional[float] = Field(None, ge=0.0)
    outstanding_principal: Optional[float] = Field(None, ge=0.0)
    accrued_interest: Optional[float] = Field(None, ge=0.0)
    interest_rate: Optional[float] = Field(None, ge=0.0, le=100.0)
    interest_type: Optional[str] = Field(None, max_length=20)
    spread: Optional[float] = Field(None, ge=0.0)
    secured: Optional[bool] = None
    guarantee_details: Optional[str] = None
    secured_type: Optional[str] = Field(None, max_length=40)
    collateral_description: Optional[str] = None
    collateral_registry_ref: Optional[str] = Field(None, max_length=200)
    guarantor_name: Optional[str] = Field(None, max_length=255)
    guarantor_tax_id: Optional[str] = Field(None, max_length=30)
    maturity_date: Optional[str] = Field(None, max_length=10)
    default_date: Optional[str] = Field(None, max_length=10)
    last_payment_date: Optional[str] = Field(None, max_length=10)
    enforcement_stage: Optional[str] = Field(None, max_length=40)
    procedure_ref: Optional[str] = Field(None, max_length=120)
    notes: Optional[str] = None


class CreateAssetRequest(_BaseUpsert):
    asset_type: str = Field(..., min_length=2, max_length=40)
    description: str = Field(..., min_length=2, max_length=500)
    location: Optional[str] = Field(None, max_length=255)
    owner: Optional[str] = Field(None, max_length=255)
    ownership_share: Optional[float] = Field(None, ge=0.0, le=1.0)
    acquisition_date: Optional[str] = Field(None, max_length=10)
    acquisition_value: Optional[float] = Field(None, ge=0.0)
    address_full: Optional[str] = Field(None, max_length=300)
    city: Optional[str] = Field(None, max_length=120)
    postal_code: Optional[str] = Field(None, max_length=20)
    province: Optional[str] = Field(None, max_length=120)
    cadastral_ref: Optional[str] = Field(None, max_length=40)
    registry_type: Optional[str] = Field(None, max_length=40)
    registry_ref: Optional[str] = Field(None, max_length=200)
    finca_registral: Optional[str] = Field(None, max_length=80)
    tomo: Optional[str] = Field(None, max_length=40)
    libro: Optional[str] = Field(None, max_length=40)
    folio: Optional[str] = Field(None, max_length=40)
    currency: str = Field("EUR", max_length=8)
    valuation_admin_concursal: Optional[float] = Field(None, ge=0.0)
    valuation_external: Optional[float] = Field(None, ge=0.0)
    valuation_date: Optional[str] = Field(None, max_length=10)
    liens: Optional[str] = None
    encumbrances_full: Optional[str] = None
    mortgage_bank: Optional[str] = Field(None, max_length=255)
    mortgage_outstanding: Optional[float] = Field(None, ge=0.0)
    disposal_status: Optional[str] = Field(None, max_length=40)
    occupancy_status: Optional[str] = Field(None, max_length=40)
    notes: Optional[str] = None


class UpdateAssetRequest(_BaseUpsert):
    logical_id: str = Field(..., min_length=1)
    expected_version: int = Field(..., ge=1)

    asset_type: Optional[str] = Field(None, max_length=40)
    description: Optional[str] = Field(None, max_length=500)
    location: Optional[str] = Field(None, max_length=255)
    owner: Optional[str] = Field(None, max_length=255)
    ownership_share: Optional[float] = Field(None, ge=0.0, le=1.0)
    acquisition_date: Optional[str] = Field(None, max_length=10)
    acquisition_value: Optional[float] = Field(None, ge=0.0)
    address_full: Optional[str] = Field(None, max_length=300)
    city: Optional[str] = Field(None, max_length=120)
    postal_code: Optional[str] = Field(None, max_length=20)
    province: Optional[str] = Field(None, max_length=120)
    cadastral_ref: Optional[str] = Field(None, max_length=40)
    registry_type: Optional[str] = Field(None, max_length=40)
    registry_ref: Optional[str] = Field(None, max_length=200)
    finca_registral: Optional[str] = Field(None, max_length=80)
    tomo: Optional[str] = Field(None, max_length=40)
    libro: Optional[str] = Field(None, max_length=40)
    folio: Optional[str] = Field(None, max_length=40)
    currency: Optional[str] = Field(None, max_length=8)
    valuation_admin_concursal: Optional[float] = Field(None, ge=0.0)
    valuation_external: Optional[float] = Field(None, ge=0.0)
    valuation_date: Optional[str] = Field(None, max_length=10)
    liens: Optional[str] = None
    encumbrances_full: Optional[str] = None
    mortgage_bank: Optional[str] = Field(None, max_length=255)
    mortgage_outstanding: Optional[float] = Field(None, ge=0.0)
    disposal_status: Optional[str] = Field(None, max_length=40)
    occupancy_status: Optional[str] = Field(None, max_length=40)
    notes: Optional[str] = None


class CreatePublicDebtRequest(_BaseUpsert):
    authority: str = Field(..., min_length=2, max_length=20)
    taxpayer_name: Optional[str] = Field(None, max_length=255)
    taxpayer_tax_id: Optional[str] = Field(None, max_length=30)
    concept: Optional[str] = Field(None, max_length=255)
    concept_code: Optional[str] = Field(None, max_length=40)
    period_start: Optional[str] = Field(None, max_length=10)
    period_end: Optional[str] = Field(None, max_length=10)
    period_key: Optional[str] = Field(None, max_length=20)
    expediente_aplazamiento: Optional[str] = Field(None, max_length=120)
    aplazamiento_status: Optional[str] = Field(None, max_length=40)
    resolution_date: Optional[str] = Field(None, max_length=10)
    currency: str = Field("EUR", max_length=8)
    principal: Optional[float] = Field(None, ge=0.0)
    surcharges: Optional[float] = Field(None, ge=0.0)
    interest: Optional[float] = Field(None, ge=0.0)
    penalties: Optional[float] = Field(None, ge=0.0)
    amount_total: float = Field(0.0, ge=0.0)
    debt_status: Optional[str] = Field(None, max_length=40)
    enforcement_stage: Optional[str] = Field(None, max_length=40)
    deferred: bool = False
    notes: Optional[str] = None


class UpdatePublicDebtRequest(_BaseUpsert):
    logical_id: str = Field(..., min_length=1)
    expected_version: int = Field(..., ge=1)

    authority: Optional[str] = Field(None, max_length=20)
    taxpayer_name: Optional[str] = Field(None, max_length=255)
    taxpayer_tax_id: Optional[str] = Field(None, max_length=30)
    concept: Optional[str] = Field(None, max_length=255)
    concept_code: Optional[str] = Field(None, max_length=40)
    period_start: Optional[str] = Field(None, max_length=10)
    period_end: Optional[str] = Field(None, max_length=10)
    period_key: Optional[str] = Field(None, max_length=20)
    expediente_aplazamiento: Optional[str] = Field(None, max_length=120)
    aplazamiento_status: Optional[str] = Field(None, max_length=40)
    resolution_date: Optional[str] = Field(None, max_length=10)
    currency: Optional[str] = Field(None, max_length=8)
    principal: Optional[float] = Field(None, ge=0.0)
    surcharges: Optional[float] = Field(None, ge=0.0)
    interest: Optional[float] = Field(None, ge=0.0)
    penalties: Optional[float] = Field(None, ge=0.0)
    amount_total: Optional[float] = Field(None, ge=0.0)
    debt_status: Optional[str] = Field(None, max_length=40)
    enforcement_stage: Optional[str] = Field(None, max_length=40)
    deferred: Optional[bool] = None
    notes: Optional[str] = None


class CreateCourtRecordRequest(_BaseUpsert):
    court: Optional[str] = Field(None, max_length=255)
    court_city: Optional[str] = Field(None, max_length=120)
    court_section: Optional[str] = Field(None, max_length=120)
    procedure_number: Optional[str] = Field(
        None, max_length=100, validation_alias=AliasChoices("procedure_number", "procedure_ref")
    )
    autos_ref: Optional[str] = Field(None, max_length=120)
    case_year: Optional[int] = Field(None, ge=1900, le=2200)
    case_role: Optional[str] = Field(None, max_length=40)
    claimant: Optional[str] = Field(None, max_length=255)
    party_counterparty_name: Optional[str] = Field(None, max_length=255)
    party_counterparty_tax_id: Optional[str] = Field(None, max_length=30)
    party_counterparty_address: Optional[str] = Field(None, max_length=300)
    lawyer_name: Optional[str] = Field(None, max_length=255)
    procurator_name: Optional[str] = Field(None, max_length=255)
    action_type: str = Field(..., min_length=2, max_length=80)
    action_date: Optional[str] = Field(None, max_length=10)
    next_hearing_date: Optional[str] = Field(None, max_length=10)
    currency: str = Field("EUR", max_length=8)
    amount_claimed: Optional[float] = Field(None, ge=0.0)
    status: Optional[str] = Field(None, max_length=80)
    stage: Optional[str] = Field(None, max_length=120)
    milestones_json: Optional[dict[str, Any]] = None
    enforcement_flag: Optional[bool] = None
    amount_awarded: Optional[float] = Field(None, ge=0.0)
    amount_paid: Optional[float] = Field(None, ge=0.0)
    seizures_notes: Optional[str] = None
    notes: Optional[str] = None


class UpdateCourtRecordRequest(_BaseUpsert):
    logical_id: str = Field(..., min_length=1)
    expected_version: int = Field(..., ge=1)

    court: Optional[str] = Field(None, max_length=255)
    court_city: Optional[str] = Field(None, max_length=120)
    court_section: Optional[str] = Field(None, max_length=120)
    procedure_number: Optional[str] = Field(
        None, max_length=100, validation_alias=AliasChoices("procedure_number", "procedure_ref")
    )
    autos_ref: Optional[str] = Field(None, max_length=120)
    case_year: Optional[int] = Field(None, ge=1900, le=2200)
    case_role: Optional[str] = Field(None, max_length=40)
    claimant: Optional[str] = Field(None, max_length=255)
    party_counterparty_name: Optional[str] = Field(None, max_length=255)
    party_counterparty_tax_id: Optional[str] = Field(None, max_length=30)
    party_counterparty_address: Optional[str] = Field(None, max_length=300)
    lawyer_name: Optional[str] = Field(None, max_length=255)
    procurator_name: Optional[str] = Field(None, max_length=255)
    action_type: Optional[str] = Field(None, max_length=80)
    action_date: Optional[str] = Field(None, max_length=10)
    next_hearing_date: Optional[str] = Field(None, max_length=10)
    currency: Optional[str] = Field(None, max_length=8)
    amount_claimed: Optional[float] = Field(None, ge=0.0)
    status: Optional[str] = Field(None, max_length=80)
    stage: Optional[str] = Field(None, max_length=120)
    milestones_json: Optional[dict[str, Any]] = None
    enforcement_flag: Optional[bool] = None
    amount_awarded: Optional[float] = Field(None, ge=0.0)
    amount_paid: Optional[float] = Field(None, ge=0.0)
    seizures_notes: Optional[str] = None
    notes: Optional[str] = None


class SituationRecordSummary(BaseModel):
    logical_id: str
    record_id: str
    version: int
    is_current: bool
    created_at: str
    created_by: str
    data: dict[str, Any]
    evidence_count: int = 0

    model_config = {"extra": "forbid"}


class SituationListResponse(BaseModel):
    items: list[SituationRecordSummary] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0

    model_config = {"extra": "forbid"}


class SituationSearchItem(BaseModel):
    """
    Resultado normalizado del buscador global del Cuadro de situación.
    """

    entity: str  # INVOICE|CREDIT|PUBLIC_DEBT|COURT
    record_id: str
    logical_id: str
    label: str
    data: dict[str, Any] = Field(default_factory=dict)
    evidence_ref: str = ""

    model_config = {"extra": "forbid"}


class SituationSearchGroup(BaseModel):
    items: list[SituationSearchItem] = Field(default_factory=list)
    total: int = 0

    model_config = {"extra": "forbid"}


class SituationSearchResponse(BaseModel):
    q: str
    page: int = 1
    page_size: int = 20
    groups: dict[str, SituationSearchGroup] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class SituationEvidenceItem(BaseModel):
    evidence_id: str
    record_id: str
    entity: str
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    page: Optional[int] = None
    note: str
    created_by: str
    created_at: str

    model_config = {"extra": "forbid"}


class SituationEvidenceListResponse(BaseModel):
    items: list[SituationEvidenceItem] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class AddEvidenceRequest(BaseModel):
    created_by: str = Field(..., min_length=2, max_length=100)
    reason: str = Field(..., min_length=10, max_length=500)
    evidence: list[EvidenceInput] = Field(..., min_length=1)

    model_config = {"extra": "forbid"}


class SituationAuditEntry(BaseModel):
    audit_id: str
    entity: str
    logical_id: str
    record_id: str
    action: str
    actor: str
    reason: str
    before: Optional[dict[str, Any]] = None
    after: Optional[dict[str, Any]] = None
    created_at: str

    model_config = {"extra": "forbid"}


class SituationAuditListResponse(BaseModel):
    items: list[SituationAuditEntry] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class LinkTargetItem(BaseModel):
    label: str = Field(..., min_length=1, max_length=500)
    record_id: str = Field(..., min_length=1, max_length=36)

    model_config = {"extra": "forbid"}


class LinkTargetsResponse(BaseModel):
    items: list[LinkTargetItem] = Field(default_factory=list)
    total: int = Field(0, ge=0)
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

    model_config = {"extra": "forbid"}


class SituationKpiCurrencyRow(BaseModel):
    currency: str = Field(..., min_length=1, max_length=8)
    invoices_open: float = Field(0.0, ge=0.0)
    credits_total: float = Field(0.0, ge=0.0)
    public_debt_total: float = Field(0.0, ge=0.0)
    total_pasivo: float = Field(0.0, ge=0.0)

    model_config = {"extra": "forbid"}


class SituationKpisResponse(BaseModel):
    total_pasivo: float = Field(0.0, ge=0.0)
    total_deuda_publica: float = Field(0.0, ge=0.0)
    num_acreedores: int = Field(0, ge=0)
    num_facturas: int = Field(0, ge=0)
    num_creditos: int = Field(0, ge=0)
    num_bienes: int = Field(0, ge=0)
    num_actuaciones: int = Field(0, ge=0)
    by_currency: list[SituationKpiCurrencyRow] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


# =========================================================
# Helpers
# =========================================================


def _require_case(db: Session, case_id: str) -> Case:
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caso no encontrado")
    return case


def _validate_evidence(db: Session, case_id: str, evidence: list[EvidenceInput]) -> None:
    if not evidence:
        raise HTTPException(status_code=400, detail="Evidencia obligatoria (mínimo 1)")

    allowed_source = {"DOCUMENTO", "CLIENTE", "CONTABILIDAD", "CRITERIO_PROFESIONAL"}
    allowed_certainty = {"CONSTA", "NO_CONSTA", "ESTIMADO"}

    # Regla dura: si source_type=DOCUMENTO -> document_id requerido
    for ev in evidence:
        st = (ev.source_type or "").strip().upper()
        cl = (ev.certainty_level or "").strip().upper()
        if st not in allowed_source:
            raise HTTPException(status_code=422, detail=f"source_type inválido: {ev.source_type}")
        if cl not in allowed_certainty:
            raise HTTPException(status_code=422, detail=f"certainty_level inválido: {ev.certainty_level}")

        # Regla dura: NO_CONSTA requiere justificación más fuerte (evitar "NO_CONSTA" vacío).
        if cl == "NO_CONSTA" and len((ev.note or "").strip()) < 20:
            raise HTTPException(
                status_code=422,
                detail="Evidencia inválida: certainty_level=NO_CONSTA requiere note >= 20 caracteres",
            )

        if st == "DOCUMENTO":
            if not (ev.document_id or "").strip():
                raise HTTPException(
                    status_code=422,
                    detail="Evidencia inválida: source_type=DOCUMENTO requiere document_id",
                )
        else:
            # Regla dura: si source_type != DOCUMENTO -> document_id/chunk_id/page deben ser null
            if (ev.document_id or "").strip() or (ev.chunk_id or "").strip() or (ev.page is not None):
                raise HTTPException(
                    status_code=422,
                    detail="Evidencia inválida: source_type != DOCUMENTO requiere document_id/chunk_id/page null",
                )

    # Validar que los documents existen y pertenecen al caso (si se proporcionan)
    doc_ids = list({(e.document_id or "").strip() for e in evidence if (e.document_id or "").strip()})
    existing = (
        db.query(Document.document_id)
        .filter(Document.case_id == case_id, Document.document_id.in_(doc_ids), Document.deleted_at.is_(None))
        .all()
    )
    found = {d[0] for d in existing}
    missing = [d for d in doc_ids if d not in found]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Evidencia inválida: document_id no existe en el caso o está excluido: {missing[:5]}",
        )


def _insert_evidence(
    *,
    db: Session,
    case_id: str,
    entity: str,
    record_id: str,
    created_by: str,
    evidence: list[EvidenceInput],
) -> None:
    record_type = record_type_from_entity(entity)
    for ev in evidence:
        st = (ev.source_type or "DOCUMENTO").strip().upper()
        cl = (ev.certainty_level or "CONSTA").strip().upper()
        doc_id = (ev.document_id or "").strip() or None
        if st != "DOCUMENTO":
            doc_id = None

        # CAPA 3 — Evidencia canónica
        db.add(
            CaseRecordEvidence(
                case_id=case_id,
                record_type=record_type,
                record_id=record_id,
                source_type=st,
                certainty_level=cl,
                justification=ev.note,
                document_id=doc_id,
                chunk_id=ev.chunk_id if st == "DOCUMENTO" else None,
                page=ev.page if st == "DOCUMENTO" else None,
                excerpt=ev.excerpt if st == "DOCUMENTO" else None,
                added_by=created_by,
            )
        )


def _audit(
    *,
    db: Session,
    case_id: str,
    entity: str,
    logical_id: str,
    record_id: str,
    action: str,
    actor: str,
    reason: str,
    before: Optional[dict],
    after: Optional[dict],
) -> None:
    record_type = record_type_from_entity(entity)
    db.add(
        CaseRecordAudit(
            case_id=case_id,
            record_type=record_type,
            logical_id=logical_id or None,
            record_id=record_id or None,
            action=action,
            actor=actor,
            justification=reason,
            before_json=before,
            after_json=after,
        )
    )


def _new_logical_id() -> str:
    return str(uuid.uuid4())


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_iso_date(value: Optional[str], *, field: str) -> Optional[date]:
    if value is None:
        return None
    v = (value or "").strip()
    if not v:
        return None
    if not _ISO_DATE_RE.match(v):
        raise HTTPException(status_code=422, detail=f"{field} debe tener formato YYYY-MM-DD")
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=422, detail=f"{field} no es una fecha válida: {v}")


def _require_date_order(
    a: Optional[str], *, a_field: str, b: Optional[str], b_field: str, allow_equal: bool = True
) -> None:
    da = _parse_iso_date(a, field=a_field)
    dbb = _parse_iso_date(b, field=b_field)
    if da is None or dbb is None:
        return
    if allow_equal:
        if da > dbb:
            raise HTTPException(status_code=422, detail=f"Incoherencia: {a_field} > {b_field}")
    else:
        if da >= dbb:
            raise HTTPException(status_code=422, detail=f"Incoherencia: {a_field} >= {b_field}")


def _validate_invoice_consistency(*, payload: dict[str, Any]) -> None:
    _require_date_order(payload.get("issue_date"), a_field="issue_date", b=payload.get("due_date"), b_field="due_date")
    issue = payload.get("issue_date")
    paid = payload.get("paid_date")
    if paid:
        _require_date_order(issue, a_field="issue_date", b=paid, b_field="paid_date")

    status_txt = (payload.get("status") or "").strip().lower()
    if status_txt.startswith("pagad") and not (payload.get("paid_date") or "").strip():
        raise HTTPException(status_code=422, detail="paid_date es obligatorio cuando status=pagada")

    base = payload.get("base_amount")
    vat = payload.get("vat_amount")
    wh = payload.get("withholding_amount")
    if base is not None or vat is not None or wh is not None:
        expected = float(base or 0.0) + float(vat or 0.0) - float(wh or 0.0)
        total = float(payload.get("amount_total") or 0.0)
        if abs(expected - total) > 0.01:
            raise HTTPException(
                status_code=422,
                detail=f"Incoherencia importes: amount_total={total:.2f} pero base+vat-withholding={expected:.2f}",
            )


def _validate_public_debt_consistency(*, payload: dict[str, Any]) -> None:
    _require_date_order(
        payload.get("period_start"), a_field="period_start", b=payload.get("period_end"), b_field="period_end"
    )
    principal = payload.get("principal")
    sur = payload.get("surcharges")
    it = payload.get("interest")
    pen = payload.get("penalties")
    if principal is not None or sur is not None or it is not None or pen is not None:
        expected = float(principal or 0.0) + float(sur or 0.0) + float(it or 0.0) + float(pen or 0.0)
        total = float(payload.get("amount_total") or 0.0)
        if abs(expected - total) > 0.01:
            raise HTTPException(
                status_code=422,
                detail=f"Incoherencia importes: amount_total={total:.2f} pero principal+surcharges+interest+penalties={expected:.2f}",
            )


def _validate_credit_consistency(*, payload: dict[str, Any]) -> None:
    # Fechas coherentes (si existen)
    _require_date_order(payload.get("default_date"), a_field="default_date", b=payload.get("maturity_date"), b_field="maturity_date")
    _require_date_order(
        payload.get("last_payment_date"),
        a_field="last_payment_date",
        b=payload.get("maturity_date"),
        b_field="maturity_date",
    )

    # Coherencias básicas de importes (si existen)
    principal_initial = payload.get("principal_initial")
    outstanding = payload.get("outstanding_principal")
    if principal_initial is not None and outstanding is not None and float(outstanding) - float(principal_initial) > 0.01:
        raise HTTPException(
            status_code=422,
            detail="Incoherencia: outstanding_principal no puede ser mayor que principal_initial",
        )

    rate = payload.get("interest_rate")
    if rate is not None and (float(rate) < 0.0 or float(rate) > 100.0):
        raise HTTPException(status_code=422, detail="interest_rate debe estar entre 0 y 100")


def _check_duplicate_invoice(
    db: Session,
    *,
    case_id: str,
    supplier_tax_id: Optional[str],
    invoice_number: Optional[str],
    issue_date: Optional[str],
    exclude_logical_id: Optional[str] = None,
) -> None:
    stid = (supplier_tax_id or "").strip()
    inv = (invoice_number or "").strip()
    iss = (issue_date or "").strip()
    if not (stid and inv and iss):
        return
    q = (
        db.query(SituationInvoice.record_id, SituationInvoice.logical_id)
        .filter(
            SituationInvoice.case_id == case_id,
            SituationInvoice.is_current.is_(True),
            func.lower(SituationInvoice.supplier_tax_id) == func.lower(stid),
            func.lower(SituationInvoice.invoice_number) == func.lower(inv),
            SituationInvoice.issue_date == iss,
        )
    )
    if exclude_logical_id:
        q = q.filter(SituationInvoice.logical_id != exclude_logical_id)
    hit = q.first()
    if hit:
        raise HTTPException(status_code=409, detail="DUPLICATE_INVOICE: ya existe una factura vigente con esa clave")


def _check_duplicate_credit(
    db: Session,
    *,
    case_id: str,
    creditor_tax_id: Optional[str],
    contract_ref: Optional[str],
    exclude_logical_id: Optional[str] = None,
) -> None:
    ctid = (creditor_tax_id or "").strip()
    cref = (contract_ref or "").strip()
    if not (ctid and cref):
        return
    q = (
        db.query(SituationCredit.record_id, SituationCredit.logical_id)
        .filter(
            SituationCredit.case_id == case_id,
            SituationCredit.is_current.is_(True),
            func.lower(SituationCredit.creditor_tax_id) == func.lower(ctid),
            func.lower(SituationCredit.contract_ref) == func.lower(cref),
        )
    )
    if exclude_logical_id:
        q = q.filter(SituationCredit.logical_id != exclude_logical_id)
    hit = q.first()
    if hit:
        raise HTTPException(status_code=409, detail="DUPLICATE_CREDIT: ya existe un crédito vigente con esa clave")


@router.get(
    "/link-targets",
    response_model=LinkTargetsResponse,
    summary="Buscar destinos para enlazar evidencia (global, server-side)",
)
def list_link_targets(
    case_id: str,
    record_type: str = Query(..., description="invoice|loan|asset|public_debt|court_claim|form_field"),
    q: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> LinkTargetsResponse:
    """
    Endpoint único para la UI: devuelve destinos (label + record_id) paginados y filtrables.
    """
    _require_case(db, case_id)

    rt = (record_type or "").strip().lower()
    allowed = {"invoice", "loan", "asset", "public_debt", "court_claim", "form_field"}
    if rt not in allowed:
        raise HTTPException(status_code=422, detail=f"record_type inválido: {record_type}")

    qn = (q or "").strip()
    q_lower = qn.lower()
    q_like = f"%{qn}%"
    q_prefix = f"{q_lower}%"
    q_contains = f"%{q_lower}%"

    # ---------------------------------------------------------
    # Helpers: ranking por campo (prefijo > contiene) + recencia.
    # ---------------------------------------------------------
    def _lower_coalesce(col_expr):
        return func.lower(func.coalesce(col_expr, ""))

    def _order_by_score(*, score_expr, created_col):
        if not qn:
            return (created_col.desc(),)
        return (
            score_expr.asc(),
            created_col.desc(),
        )

    items: list[LinkTargetItem] = []

    if rt == "invoice":
        base = db.query(SituationInvoice).filter(
            SituationInvoice.case_id == case_id,
            SituationInvoice.is_current.is_(True),
        )
        if qn:
            base = base.filter(
                or_(
                    SituationInvoice.invoice_number.ilike(q_like),
                    SituationInvoice.supplier.ilike(q_like),
                    SituationInvoice.supplier_tax_id.ilike(q_like),
                    SituationInvoice.supplier_email.ilike(q_like),
                    SituationInvoice.contract_ref.ilike(q_like),
                    SituationInvoice.buyer_name.ilike(q_like),
                    SituationInvoice.buyer_tax_id.ilike(q_like),
                    SituationInvoice.buyer_email.ilike(q_like),
                    SituationInvoice.due_date.ilike(q_like),
                )
            )
        score = sa_case(
            (_lower_coalesce(SituationInvoice.invoice_number).like(q_prefix), 0),
            (_lower_coalesce(SituationInvoice.supplier_tax_id).like(q_prefix), 1),
            (_lower_coalesce(SituationInvoice.buyer_tax_id).like(q_prefix), 2),
            (_lower_coalesce(SituationInvoice.contract_ref).like(q_prefix), 2),
            (_lower_coalesce(SituationInvoice.supplier).like(q_prefix), 3),
            (_lower_coalesce(SituationInvoice.buyer_name).like(q_prefix), 4),
            (_lower_coalesce(SituationInvoice.invoice_number).like(q_contains), 10),
            (_lower_coalesce(SituationInvoice.supplier_tax_id).like(q_contains), 11),
            (_lower_coalesce(SituationInvoice.buyer_tax_id).like(q_contains), 12),
            (_lower_coalesce(SituationInvoice.contract_ref).like(q_contains), 12),
            (_lower_coalesce(SituationInvoice.supplier).like(q_contains), 13),
            (_lower_coalesce(SituationInvoice.buyer_name).like(q_contains), 14),
            else_=99,
        )
        total = int(base.count())
        rows = (
            base.order_by(*_order_by_score(score_expr=score, created_col=SituationInvoice.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        for r in rows:
            supplier = r.supplier
            inv_no = r.invoice_number or "sin nº"
            amount = f"{r.amount_total:.2f}"
            due = r.due_date or "s/f"
            cref = r.contract_ref or ""
            cref = f" | {cref}" if cref else ""
            buyer = r.buyer_tax_id or ""
            buyer = f" | NIF cliente {buyer}" if buyer else ""
            label = f"{supplier}{cref}{buyer} | {inv_no} | {amount}€ | vto {due}"
            items.append(LinkTargetItem(label=label[:500], record_id=r.record_id))
        return LinkTargetsResponse(items=items, total=total, page=page, page_size=page_size)

    if rt == "loan":
        base = db.query(SituationCredit).filter(
            SituationCredit.case_id == case_id,
            SituationCredit.is_current.is_(True),
        )
        if qn:
            base = base.filter(
                or_(
                    SituationCredit.creditor.ilike(q_like),
                    SituationCredit.creditor_tax_id.ilike(q_like),
                    SituationCredit.lender_email.ilike(q_like),
                    SituationCredit.lender_phone.ilike(q_like),
                    SituationCredit.contract_ref.ilike(q_like),
                    SituationCredit.procedure_ref.ilike(q_like),
                    SituationCredit.guarantor_name.ilike(q_like),
                    SituationCredit.guarantor_tax_id.ilike(q_like),
                    SituationCredit.maturity_date.ilike(q_like),
                )
            )
        score = sa_case(
            (_lower_coalesce(SituationCredit.contract_ref).like(q_prefix), 0),
            (_lower_coalesce(SituationCredit.creditor_tax_id).like(q_prefix), 1),
            (_lower_coalesce(SituationCredit.creditor).like(q_prefix), 2),
            (_lower_coalesce(SituationCredit.procedure_ref).like(q_prefix), 3),
            (_lower_coalesce(SituationCredit.maturity_date).like(q_prefix), 3),
            (_lower_coalesce(SituationCredit.contract_ref).like(q_contains), 10),
            (_lower_coalesce(SituationCredit.creditor_tax_id).like(q_contains), 11),
            (_lower_coalesce(SituationCredit.creditor).like(q_contains), 12),
            (_lower_coalesce(SituationCredit.procedure_ref).like(q_contains), 13),
            (_lower_coalesce(SituationCredit.maturity_date).like(q_contains), 13),
            else_=99,
        )
        total = int(base.count())
        rows = (
            base.order_by(*_order_by_score(score_expr=score, created_col=SituationCredit.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        for r in rows:
            name = r.creditor
            cref = r.contract_ref or "sin ref"
            amt = r.outstanding_principal if r.outstanding_principal is not None else r.amount_total
            amount = f"{amt:.2f}"
            vto = r.maturity_date or "s/f"
            label = f"{name} | {cref} | saldo {amount}€ | vto {vto}"
            items.append(LinkTargetItem(label=label[:500], record_id=r.record_id))
        return LinkTargetsResponse(items=items, total=total, page=page, page_size=page_size)

    if rt == "asset":
        base = db.query(SituationAsset).filter(
            SituationAsset.case_id == case_id,
            SituationAsset.is_current.is_(True),
        )
        if qn:
            base = base.filter(
                or_(
                    SituationAsset.asset_type.ilike(q_like),
                    SituationAsset.description.ilike(q_like),
                    SituationAsset.location.ilike(q_like),
                    SituationAsset.owner.ilike(q_like),
                    SituationAsset.cadastral_ref.ilike(q_like),
                    SituationAsset.registry_ref.ilike(q_like),
                    SituationAsset.finca_registral.ilike(q_like),
                    SituationAsset.address_full.ilike(q_like),
                )
            )
        score = sa_case(
            (_lower_coalesce(SituationAsset.description).like(q_prefix), 0),
            (_lower_coalesce(SituationAsset.location).like(q_prefix), 1),
            (_lower_coalesce(SituationAsset.cadastral_ref).like(q_prefix), 2),
            (_lower_coalesce(SituationAsset.registry_ref).like(q_prefix), 3),
            (_lower_coalesce(SituationAsset.finca_registral).like(q_prefix), 4),
            (_lower_coalesce(SituationAsset.owner).like(q_prefix), 5),
            (_lower_coalesce(SituationAsset.asset_type).like(q_prefix), 6),
            (_lower_coalesce(SituationAsset.description).like(q_contains), 10),
            (_lower_coalesce(SituationAsset.location).like(q_contains), 11),
            (_lower_coalesce(SituationAsset.cadastral_ref).like(q_contains), 12),
            (_lower_coalesce(SituationAsset.registry_ref).like(q_contains), 13),
            (_lower_coalesce(SituationAsset.finca_registral).like(q_contains), 14),
            (_lower_coalesce(SituationAsset.owner).like(q_contains), 15),
            (_lower_coalesce(SituationAsset.asset_type).like(q_contains), 16),
            else_=99,
        )
        total = int(base.count())
        rows = (
            base.order_by(*_order_by_score(score_expr=score, created_col=SituationAsset.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        for r in rows:
            val = r.valuation_admin_concursal
            if val is None:
                val = r.valuation_external
            val_txt = f"{val:.2f}" if val is not None else "s/v"
            loc = f" | {r.location}" if r.location else ""
            reg = r.cadastral_ref or r.registry_ref or r.finca_registral or ""
            reg = f" | ref {reg}" if reg else ""
            label = f"{r.asset_type} | {r.description}{loc}{reg} | valor {val_txt}€"
            items.append(LinkTargetItem(label=label[:500], record_id=r.record_id))
        return LinkTargetsResponse(items=items, total=total, page=page, page_size=page_size)

    if rt == "public_debt":
        base = db.query(SituationPublicDebt).filter(
            SituationPublicDebt.case_id == case_id,
            SituationPublicDebt.is_current.is_(True),
        )
        if qn:
            base = base.filter(
                or_(
                    SituationPublicDebt.authority.ilike(q_like),
                    SituationPublicDebt.taxpayer_tax_id.ilike(q_like),
                    SituationPublicDebt.taxpayer_name.ilike(q_like),
                    SituationPublicDebt.concept.ilike(q_like),
                    SituationPublicDebt.concept_code.ilike(q_like),
                    SituationPublicDebt.expediente_aplazamiento.ilike(q_like),
                    SituationPublicDebt.period_key.ilike(q_like),
                    SituationPublicDebt.period_start.ilike(q_like),
                    SituationPublicDebt.period_end.ilike(q_like),
                )
            )
        score = sa_case(
            (_lower_coalesce(SituationPublicDebt.expediente_aplazamiento).like(q_prefix), 0),
            (_lower_coalesce(SituationPublicDebt.taxpayer_tax_id).like(q_prefix), 1),
            (_lower_coalesce(SituationPublicDebt.authority).like(q_prefix), 1),
            (_lower_coalesce(SituationPublicDebt.concept_code).like(q_prefix), 2),
            (_lower_coalesce(SituationPublicDebt.concept).like(q_prefix), 3),
            (_lower_coalesce(SituationPublicDebt.period_key).like(q_prefix), 4),
            (_lower_coalesce(SituationPublicDebt.period_start).like(q_prefix), 3),
            (_lower_coalesce(SituationPublicDebt.period_end).like(q_prefix), 4),
            (_lower_coalesce(SituationPublicDebt.expediente_aplazamiento).like(q_contains), 10),
            (_lower_coalesce(SituationPublicDebt.taxpayer_tax_id).like(q_contains), 11),
            (_lower_coalesce(SituationPublicDebt.authority).like(q_contains), 11),
            (_lower_coalesce(SituationPublicDebt.concept_code).like(q_contains), 12),
            (_lower_coalesce(SituationPublicDebt.concept).like(q_contains), 13),
            (_lower_coalesce(SituationPublicDebt.period_key).like(q_contains), 14),
            (_lower_coalesce(SituationPublicDebt.period_start).like(q_contains), 13),
            (_lower_coalesce(SituationPublicDebt.period_end).like(q_contains), 14),
            else_=99,
        )
        total = int(base.count())
        rows = (
            base.order_by(*_order_by_score(score_expr=score, created_col=SituationPublicDebt.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        for r in rows:
            concept = r.concept or "s/concepto"
            amount = f"{r.amount_total:.2f}"
            period = ""
            if r.period_start or r.period_end:
                period = f"{r.period_start or ''}–{r.period_end or ''}".strip("–")
            period = period or "s/f"
            exp = r.expediente_aplazamiento or ""
            exp = f" | exp {exp}" if exp else ""
            nif = r.taxpayer_tax_id or ""
            nif = f" | NIF {nif}" if nif else ""
            label = f"{r.authority}{exp}{nif} | {concept} | {amount}€ | periodo {period}"
            items.append(LinkTargetItem(label=label[:500], record_id=r.record_id))
        return LinkTargetsResponse(items=items, total=total, page=page, page_size=page_size)

    if rt == "court_claim":
        base = db.query(SituationCourtRecord).filter(
            SituationCourtRecord.case_id == case_id,
            SituationCourtRecord.is_current.is_(True),
        )
        if qn:
            base = base.filter(
                or_(
                    SituationCourtRecord.court.ilike(q_like),
                    SituationCourtRecord.court_city.ilike(q_like),
                    SituationCourtRecord.procedure_number.ilike(q_like),
                    SituationCourtRecord.autos_ref.ilike(q_like),
                    func.cast(SituationCourtRecord.case_year, String).ilike(q_like),
                    SituationCourtRecord.claimant.ilike(q_like),
                    SituationCourtRecord.party_counterparty_name.ilike(q_like),
                    SituationCourtRecord.party_counterparty_tax_id.ilike(q_like),
                    SituationCourtRecord.action_type.ilike(q_like),
                    SituationCourtRecord.status.ilike(q_like),
                    SituationCourtRecord.stage.ilike(q_like),
                )
            )
        score = sa_case(
            (_lower_coalesce(SituationCourtRecord.procedure_number).like(q_prefix), 0),
            (_lower_coalesce(SituationCourtRecord.autos_ref).like(q_prefix), 1),
            (_lower_coalesce(SituationCourtRecord.claimant).like(q_prefix), 1),
            (_lower_coalesce(SituationCourtRecord.party_counterparty_tax_id).like(q_prefix), 2),
            (_lower_coalesce(SituationCourtRecord.court).like(q_prefix), 2),
            (_lower_coalesce(SituationCourtRecord.stage).like(q_prefix), 3),
            (_lower_coalesce(SituationCourtRecord.status).like(q_prefix), 4),
            (_lower_coalesce(SituationCourtRecord.action_type).like(q_prefix), 5),
            (_lower_coalesce(SituationCourtRecord.procedure_number).like(q_contains), 10),
            (_lower_coalesce(SituationCourtRecord.autos_ref).like(q_contains), 11),
            (_lower_coalesce(SituationCourtRecord.claimant).like(q_contains), 11),
            (_lower_coalesce(SituationCourtRecord.party_counterparty_tax_id).like(q_contains), 12),
            (_lower_coalesce(SituationCourtRecord.court).like(q_contains), 12),
            (_lower_coalesce(SituationCourtRecord.stage).like(q_contains), 13),
            (_lower_coalesce(SituationCourtRecord.status).like(q_contains), 14),
            (_lower_coalesce(SituationCourtRecord.action_type).like(q_contains), 15),
            else_=99,
        )
        total = int(base.count())
        rows = (
            base.order_by(*_order_by_score(score_expr=score, created_col=SituationCourtRecord.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        for r in rows:
            court = r.court or "Juzgado"
            proc = r.procedure_number or "s/ref"
            amount = f"{r.amount_claimed:.2f}" if r.amount_claimed is not None else "s/imp"
            claimant = f" | {r.claimant}" if r.claimant else ""
            autos = f" | autos {r.autos_ref}" if r.autos_ref else ""
            stage = r.stage or r.status or r.action_type
            label = f"{court} | {proc}{autos}{claimant} | {amount}€ | {stage}"
            items.append(LinkTargetItem(label=label[:500], record_id=r.record_id))
        return LinkTargetsResponse(items=items, total=total, page=page, page_size=page_size)

    # rt == "form_field": se resuelve contra TemplateField (no depende de FormFieldValue).
    # La UI consume también /templates/fields, pero aquí damos compatibilidad completa "todo en uno".
    from app.models.case_central import Template, TemplateField  # import local para evitar ciclos

    base = (
        db.query(TemplateField, Template.code)
        .join(Template, Template.template_id == TemplateField.template_id)
        .filter(Template.is_active.is_(True))
    )
    if qn:
        base = base.filter(
            or_(
                Template.code.ilike(q_like),
                TemplateField.field_key.ilike(q_like),
                TemplateField.label.ilike(q_like),
            )
        )
    total = int(base.count())
    score = sa_case(
        (_lower_coalesce(TemplateField.field_key).like(q_prefix), 0),
        (_lower_coalesce(Template.code).like(q_prefix), 1),
        (_lower_coalesce(TemplateField.label).like(q_prefix), 2),
        (_lower_coalesce(TemplateField.field_key).like(q_contains), 10),
        (_lower_coalesce(Template.code).like(q_contains), 11),
        (_lower_coalesce(TemplateField.label).like(q_contains), 12),
        else_=99,
    )
    rows = (
        base.order_by(score.asc(), Template.code.asc(), TemplateField.field_key.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    for f, template_code in rows:
        label = f"{template_code} | {f.field_key} | {f.label}"
        items.append(LinkTargetItem(label=label[:500], record_id=f.field_id))
    return LinkTargetsResponse(items=items, total=total, page=page, page_size=page_size)


def _count_evidence(db: Session, *, case_id: str, entity: str, record_id: str) -> int:
    record_type = record_type_from_entity(entity)
    return int(
        db.query(CaseRecordEvidence.evidence_id)
        .filter(
            CaseRecordEvidence.case_id == case_id,
            CaseRecordEvidence.record_type == record_type,
            CaseRecordEvidence.record_id == record_id,
        )
        .count()
    )


def _get_evidence_items(db: Session, *, case_id: str, entity: str, record_id: str) -> list[SituationEvidenceItem]:
    record_type = record_type_from_entity(entity)
    rows_new = (
        db.query(CaseRecordEvidence)
        .filter(
            CaseRecordEvidence.case_id == case_id,
            CaseRecordEvidence.record_type == record_type,
            CaseRecordEvidence.record_id == record_id,
        )
        .order_by(CaseRecordEvidence.added_at.desc())
        .all()
    )
    items: list[SituationEvidenceItem] = []
    for r in rows_new:
        items.append(
            SituationEvidenceItem(
                evidence_id=r.evidence_id,
                record_id=r.record_id or "",
                entity=entity,
                document_id=r.document_id,
                chunk_id=r.chunk_id,
                page=r.page,
                note=r.justification,
                created_by=r.added_by,
                created_at=r.added_at.isoformat() if r.added_at else "",
            )
        )
    return items


@router.get(
    "/{entity}/{record_id}/evidence",
    response_model=SituationEvidenceListResponse,
    summary="Listar evidencia por registro (versión concreta)",
)
def list_record_evidence(
    case_id: str,
    entity: str,
    record_id: str,
    db: Session = Depends(get_db),
) -> SituationEvidenceListResponse:
    _require_case(db, case_id)
    entity = _require_entity(entity)

    # Validar que el record pertenece al caso (tabla core del Cuadro de situación).
    model_map = {
        "INVOICE": SituationInvoice,
        "CREDIT": SituationCredit,
        "ASSET": SituationAsset,
        "PUBLIC_DEBT": SituationPublicDebt,
        "COURT": SituationCourtRecord,
    }
    model = model_map[entity]
    rec = db.query(model).filter(model.case_id == case_id, model.record_id == record_id).first()
    if not rec:
        return SituationEvidenceListResponse(items=[])

    items = _get_evidence_items(db, case_id=case_id, entity=entity, record_id=record_id)
    return SituationEvidenceListResponse(items=items)


@router.post(
    "/{entity}/{record_id}/evidence",
    response_model=SituationEvidenceListResponse,
    summary="Añadir evidencia (append-only) a un registro existente",
)
def add_record_evidence(
    case_id: str,
    entity: str,
    record_id: str,
    req: AddEvidenceRequest,
    db: Session = Depends(get_db),
) -> SituationEvidenceListResponse:
    _require_case(db, case_id)
    entity = _require_entity(entity)
    _validate_evidence(db, case_id, req.evidence)

    # Verificar que el record pertenece al caso (por entidad).
    # Para no duplicar lógica por tabla, buscamos el record_id en la tabla correspondiente.
    # Si no existe, 404.
    model_map = {
        "INVOICE": SituationInvoice,
        "CREDIT": SituationCredit,
        "ASSET": SituationAsset,
        "PUBLIC_DEBT": SituationPublicDebt,
        "COURT": SituationCourtRecord,
    }
    model = model_map[entity]
    rec = db.query(model).filter(model.case_id == case_id, model.record_id == record_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Registro no encontrado (record_id)")

    _insert_evidence(
        db=db,
        case_id=case_id,
        entity=entity,
        record_id=record_id,
        created_by=req.created_by,
        evidence=req.evidence,
    )
    # Auditoría: ADD_EVIDENCE (no crea nueva versión).
    _audit(
        db=db,
        case_id=case_id,
        entity=entity,
        logical_id=getattr(rec, "logical_id", ""),
        record_id=record_id,
        action="ADD_EVIDENCE",
        actor=req.created_by,
        reason=req.reason,
        before=None,
        after={"added_evidence_count": len(req.evidence)},
    )
    db.commit()

    items = _get_evidence_items(db, case_id=case_id, entity=entity, record_id=record_id)
    return SituationEvidenceListResponse(items=items)


@router.get(
    "/{entity}/{logical_id}/audit",
    response_model=SituationAuditListResponse,
    summary="Ver auditoría por registro lógico (todas las versiones)",
)
def list_audit_for_logical(
    case_id: str,
    entity: str,
    logical_id: str,
    db: Session = Depends(get_db),
) -> SituationAuditListResponse:
    _require_case(db, case_id)
    entity = _require_entity(entity)
    record_type = record_type_from_entity(entity)
    rows = (
        db.query(CaseRecordAudit)
        .filter(
            CaseRecordAudit.case_id == case_id,
            CaseRecordAudit.record_type == record_type,
            CaseRecordAudit.logical_id == logical_id,
        )
        .order_by(CaseRecordAudit.created_at.desc())
        .all()
    )
    items: list[SituationAuditEntry] = []
    for r in rows:
        items.append(
            SituationAuditEntry(
                audit_id=r.audit_id,
                entity=entity,
                logical_id=r.logical_id or "",
                record_id=r.record_id or "",
                action=r.action,
                actor=r.actor,
                reason=r.justification,
                before=r.before_json,
                after=r.after_json,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
        )
    return SituationAuditListResponse(items=items)


def _export_rows_to_xlsx(rows: list[dict[str, Any]], sheet_name: str, filename: str) -> StreamingResponse:
    try:
        import pandas as pd  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pandas no disponible para export: {e}")

    buf = io.BytesIO()
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


def _export_multi_sheet_xlsx(
    *,
    sheets: dict[str, list[dict[str, Any]]],
    filename: str,
) -> StreamingResponse:
    try:
        import pandas as pd  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pandas no disponible para export: {e}")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, rows in sheets.items():
            df = pd.DataFrame(rows)
            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


def _build_evidence_ref_map(
    db: Session, *, case_id: str, entity: str, record_ids: list[str]
) -> dict[str, str]:
    if not record_ids:
        return {}
    record_type = record_type_from_entity(entity)
    rows = (
        db.query(
            CaseRecordEvidence.record_id,
            CaseRecordEvidence.document_id,
            CaseRecordEvidence.page,
        )
        .filter(
            CaseRecordEvidence.case_id == case_id,
            CaseRecordEvidence.record_type == record_type,
            CaseRecordEvidence.record_id.in_(record_ids),
            CaseRecordEvidence.document_id.isnot(None),
        )
        .order_by(CaseRecordEvidence.added_at.desc())
        .all()
    )
    out: dict[str, list[str]] = {}
    for rec_id, doc_id, page in rows:
        short = (doc_id or "")[:8]
        ref = f"{short}…"
        if page:
            ref += f" p.{page}"
        out.setdefault(rec_id, [])
        if ref not in out[rec_id]:
            out[rec_id].append(ref)
    return {k: "; ".join(v[:10]) for k, v in out.items()}


@router.get(
    "/search",
    response_model=SituationSearchResponse,
    summary="Buscador global (Cuadro de situación): facturas/créditos/deuda pública/juzgado",
)
def search_situation(
    case_id: str,
    *,
    q: str = Query("", description="Texto libre (proveedor, nº factura, acreedor, procedimiento…)", max_length=200),
    record_types: list[str] = Query(
        default=[],
        description="Filtro opcional: invoice|credit|public_debt|court (si vacío, busca en todos)",
        max_length=30,
    ),
    include_history: bool = Query(False, description="Si true, incluye versiones no vigentes"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SituationSearchResponse:
    _require_case(db, case_id)
    qn = (q or "").strip()
    if not qn:
        return SituationSearchResponse(q="", page=page, page_size=page_size, groups={})

    allowed = {"invoice", "credit", "public_debt", "court"}
    wanted = [x.strip().lower() for x in (record_types or []) if x and x.strip()]
    for w in wanted:
        if w not in allowed:
            raise HTTPException(status_code=422, detail=f"record_types inválido: {w}")
    if not wanted:
        wanted = sorted(allowed)

    q_like = f"%{qn}%"

    groups: dict[str, SituationSearchGroup] = {}

    # INVOICE
    if "invoice" in wanted:
        base = db.query(SituationInvoice).filter(SituationInvoice.case_id == case_id)
        if not include_history:
            base = base.filter(SituationInvoice.is_current.is_(True))
        base = base.filter(
            or_(
                SituationInvoice.supplier.ilike(q_like),
                SituationInvoice.invoice_number.ilike(q_like),
                SituationInvoice.contract_ref.ilike(q_like),
                SituationInvoice.supplier_tax_id.ilike(q_like),
                SituationInvoice.status.ilike(q_like),
                SituationInvoice.notes.ilike(q_like),
            )
        )
        total = int(base.count())
        rows = (
            base.order_by(SituationInvoice.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        ev_ref = _build_evidence_ref_map(db, case_id=case_id, entity="INVOICE", record_ids=[r.record_id for r in rows])
        items = []
        for r in rows:
            inv_no = r.invoice_number or "sin nº"
            label = f"{r.supplier} | {inv_no} | {r.amount_total:.2f} {r.currency} | {r.status or '—'}"
            items.append(
                SituationSearchItem(
                    entity="INVOICE",
                    record_id=r.record_id,
                    logical_id=r.logical_id,
                    label=label[:500],
                    evidence_ref=ev_ref.get(r.record_id, ""),
                    data={
                        "supplier": r.supplier,
                        "invoice_number": r.invoice_number,
                        "issue_date": r.issue_date,
                        "due_date": r.due_date,
                        "paid_date": r.paid_date,
                        "amount_total": r.amount_total,
                        "currency": r.currency,
                        "status": r.status,
                    },
                )
            )
        groups["invoice"] = SituationSearchGroup(items=items, total=total)

    # CREDIT
    if "credit" in wanted:
        base = db.query(SituationCredit).filter(SituationCredit.case_id == case_id)
        if not include_history:
            base = base.filter(SituationCredit.is_current.is_(True))
        base = base.filter(
            or_(
                SituationCredit.creditor.ilike(q_like),
                SituationCredit.contract_ref.ilike(q_like),
                SituationCredit.creditor_tax_id.ilike(q_like),
                SituationCredit.procedure_ref.ilike(q_like),
                SituationCredit.notes.ilike(q_like),
            )
        )
        total = int(base.count())
        rows = (
            base.order_by(SituationCredit.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        ev_ref = _build_evidence_ref_map(db, case_id=case_id, entity="CREDIT", record_ids=[r.record_id for r in rows])
        items = []
        for r in rows:
            cref = r.contract_ref or "s/ref"
            label = f"{r.creditor} | {cref} | {r.amount_total:.2f} {r.currency}"
            items.append(
                SituationSearchItem(
                    entity="CREDIT",
                    record_id=r.record_id,
                    logical_id=r.logical_id,
                    label=label[:500],
                    evidence_ref=ev_ref.get(r.record_id, ""),
                    data={
                        "creditor": r.creditor,
                        "contract_ref": r.contract_ref,
                        "amount_total": r.amount_total,
                        "currency": r.currency,
                        "maturity_date": r.maturity_date,
                        "default_date": r.default_date,
                        "secured": bool(r.secured),
                    },
                )
            )
        groups["credit"] = SituationSearchGroup(items=items, total=total)

    # PUBLIC_DEBT
    if "public_debt" in wanted:
        base = db.query(SituationPublicDebt).filter(SituationPublicDebt.case_id == case_id)
        if not include_history:
            base = base.filter(SituationPublicDebt.is_current.is_(True))
        base = base.filter(
            or_(
                SituationPublicDebt.authority.ilike(q_like),
                SituationPublicDebt.concept.ilike(q_like),
                SituationPublicDebt.concept_code.ilike(q_like),
                SituationPublicDebt.taxpayer_name.ilike(q_like),
                SituationPublicDebt.taxpayer_tax_id.ilike(q_like),
                SituationPublicDebt.period_key.ilike(q_like),
                SituationPublicDebt.period_start.ilike(q_like),
                SituationPublicDebt.period_end.ilike(q_like),
                SituationPublicDebt.expediente_aplazamiento.ilike(q_like),
                SituationPublicDebt.debt_status.ilike(q_like),
                SituationPublicDebt.enforcement_stage.ilike(q_like),
                SituationPublicDebt.notes.ilike(q_like),
            )
        )
        total = int(base.count())
        rows = (
            base.order_by(SituationPublicDebt.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        ev_ref = _build_evidence_ref_map(db, case_id=case_id, entity="PUBLIC_DEBT", record_ids=[r.record_id for r in rows])
        items = []
        for r in rows:
            label = f"{r.authority} | {r.concept or 's/concepto'} | {r.amount_total:.2f} {r.currency} | {r.debt_status or r.enforcement_stage or '—'}"
            items.append(
                SituationSearchItem(
                    entity="PUBLIC_DEBT",
                    record_id=r.record_id,
                    logical_id=r.logical_id,
                    label=label[:500],
                    evidence_ref=ev_ref.get(r.record_id, ""),
                    data={
                        "authority": r.authority,
                        "concept": r.concept,
                        "concept_code": r.concept_code,
                        "taxpayer_name": r.taxpayer_name,
                        "taxpayer_tax_id": r.taxpayer_tax_id,
                        "period_key": r.period_key,
                        "period_start": r.period_start,
                        "period_end": r.period_end,
                        "expediente_aplazamiento": r.expediente_aplazamiento,
                        "amount_total": r.amount_total,
                        "currency": r.currency,
                        "debt_status": r.debt_status,
                        "enforcement_stage": r.enforcement_stage,
                        # Back-compat para UI vieja (cols: reference/status)
                        "reference": r.expediente_aplazamiento,
                        "status": r.debt_status,
                    },
                )
            )
        groups["public_debt"] = SituationSearchGroup(items=items, total=total)

    # COURT
    if "court" in wanted:
        base = db.query(SituationCourtRecord).filter(SituationCourtRecord.case_id == case_id)
        if not include_history:
            base = base.filter(SituationCourtRecord.is_current.is_(True))
        base = base.filter(
            or_(
                SituationCourtRecord.court.ilike(q_like),
                SituationCourtRecord.procedure_number.ilike(q_like),
                SituationCourtRecord.autos_ref.ilike(q_like),
                SituationCourtRecord.claimant.ilike(q_like),
                SituationCourtRecord.party_counterparty_name.ilike(q_like),
                SituationCourtRecord.party_counterparty_tax_id.ilike(q_like),
                SituationCourtRecord.status.ilike(q_like),
                SituationCourtRecord.stage.ilike(q_like),
                SituationCourtRecord.notes.ilike(q_like),
            )
        )
        total = int(base.count())
        rows = (
            base.order_by(SituationCourtRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        ev_ref = _build_evidence_ref_map(db, case_id=case_id, entity="COURT", record_ids=[r.record_id for r in rows])
        items = []
        for r in rows:
            proc = r.procedure_number or "s/ref"
            court = r.court or "Juzgado"
            amt = f"{float(r.amount_claimed or 0.0):.2f} {r.currency or 'EUR'}" if r.amount_claimed else "s/imp"
            label = f"{court} | {proc} | {amt} | {r.stage or r.status or '—'}"
            items.append(
                SituationSearchItem(
                    entity="COURT",
                    record_id=r.record_id,
                    logical_id=r.logical_id,
                    label=label[:500],
                    evidence_ref=ev_ref.get(r.record_id, ""),
                    data={
                        "court": r.court,
                        "procedure_number": r.procedure_number,
                        "autos_ref": r.autos_ref,
                        "claimant": r.claimant,
                        "party_counterparty_name": r.party_counterparty_name,
                        "amount_claimed": r.amount_claimed,
                        "currency": r.currency,
                        "status": r.status,
                        "stage": r.stage,
                    },
                )
            )
        groups["court"] = SituationSearchGroup(items=items, total=total)

    return SituationSearchResponse(q=qn, page=page, page_size=page_size, groups=groups)


@router.get("/export.xlsx", summary="Exportar Cuadro de situación (Excel, 5 pestañas)")
def export_situation_excel(case_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    _require_case(db, case_id)

    # Solo vigentes (operativo).
    inv = (
        db.query(SituationInvoice)
        .filter(SituationInvoice.case_id == case_id, SituationInvoice.is_current.is_(True))
        .order_by(SituationInvoice.created_at.desc())
        .all()
    )
    cred = (
        db.query(SituationCredit)
        .filter(SituationCredit.case_id == case_id, SituationCredit.is_current.is_(True))
        .order_by(SituationCredit.created_at.desc())
        .all()
    )
    assets = (
        db.query(SituationAsset)
        .filter(SituationAsset.case_id == case_id, SituationAsset.is_current.is_(True))
        .order_by(SituationAsset.created_at.desc())
        .all()
    )
    pub = (
        db.query(SituationPublicDebt)
        .filter(SituationPublicDebt.case_id == case_id, SituationPublicDebt.is_current.is_(True))
        .order_by(SituationPublicDebt.created_at.desc())
        .all()
    )
    court = (
        db.query(SituationCourtRecord)
        .filter(SituationCourtRecord.case_id == case_id, SituationCourtRecord.is_current.is_(True))
        .order_by(SituationCourtRecord.created_at.desc())
        .all()
    )

    inv_ev = _build_evidence_ref_map(db, case_id=case_id, entity="INVOICE", record_ids=[r.record_id for r in inv])
    cred_ev = _build_evidence_ref_map(db, case_id=case_id, entity="CREDIT", record_ids=[r.record_id for r in cred])
    asset_ev = _build_evidence_ref_map(db, case_id=case_id, entity="ASSET", record_ids=[r.record_id for r in assets])
    pub_ev = _build_evidence_ref_map(db, case_id=case_id, entity="PUBLIC_DEBT", record_ids=[r.record_id for r in pub])
    court_ev = _build_evidence_ref_map(db, case_id=case_id, entity="COURT", record_ids=[r.record_id for r in court])

    sheets: dict[str, list[dict[str, Any]]] = {}
    sheets["Facturas"] = [
        {
            "logical_id": r.logical_id,
            "record_id": r.record_id,
            "version": r.version,
            "created_at": r.created_at.isoformat(),
            "created_by": r.created_by,
            "supplier": r.supplier,
            "invoice_number": r.invoice_number,
            "issue_date": r.issue_date,
            "due_date": r.due_date,
            "currency": r.currency,
            "amount_total": r.amount_total,
            "status": r.status,
            "notes": r.notes,
            "evidence": inv_ev.get(r.record_id, ""),
        }
        for r in inv
    ]
    sheets["Créditos"] = [
        {
            "logical_id": r.logical_id,
            "record_id": r.record_id,
            "version": r.version,
            "created_at": r.created_at.isoformat(),
            "created_by": r.created_by,
            "creditor": r.creditor,
            "contract_ref": r.contract_ref,
            "currency": r.currency,
            "amount_total": r.amount_total,
            "secured": r.secured,
            "guarantee_details": r.guarantee_details,
            "maturity_date": r.maturity_date,
            "notes": r.notes,
            "evidence": cred_ev.get(r.record_id, ""),
        }
        for r in cred
    ]
    sheets["Bienes"] = [
        {
            "logical_id": r.logical_id,
            "record_id": r.record_id,
            "version": r.version,
            "created_at": r.created_at.isoformat(),
            "created_by": r.created_by,
            "asset_type": r.asset_type,
            "description": r.description,
            "currency": r.currency,
            "valuation_admin_concursal": r.valuation_admin_concursal,
            "valuation_external": r.valuation_external,
            "valuation_date": r.valuation_date,
            "liens": r.liens,
            "notes": r.notes,
            "evidence": asset_ev.get(r.record_id, ""),
        }
        for r in assets
    ]
    sheets["Deuda pública"] = [
        {
            "logical_id": r.logical_id,
            "record_id": r.record_id,
            "version": r.version,
            "created_at": r.created_at.isoformat(),
            "created_by": r.created_by,
            "authority": r.authority,
            "concept": r.concept,
            "period_start": r.period_start,
            "period_end": r.period_end,
            "currency": r.currency,
            "amount_total": r.amount_total,
            "deferred": r.deferred,
            "notes": r.notes,
            "evidence": pub_ev.get(r.record_id, ""),
        }
        for r in pub
    ]
    sheets["Juzgado"] = [
        {
            "logical_id": r.logical_id,
            "record_id": r.record_id,
            "version": r.version,
            "created_at": r.created_at.isoformat(),
            "created_by": r.created_by,
            "court": r.court,
            "procedure_number": r.procedure_number,
            "action_type": r.action_type,
            "action_date": r.action_date,
            "currency": r.currency,
            "amount_claimed": r.amount_claimed,
            "status": r.status,
            "notes": r.notes,
            "evidence": court_ev.get(r.record_id, ""),
        }
        for r in court
    ]

    return _export_multi_sheet_xlsx(sheets=sheets, filename=f"situation_{case_id}.xlsx")


@router.get(
    "/kpis",
    response_model=SituationKpisResponse,
    summary="KPIs agregados del Cuadro de situación (vigentes)",
)
def get_situation_kpis(case_id: str, db: Session = Depends(get_db)) -> SituationKpisResponse:
    """
    KPIs rápidos (server-side):
    - total_pasivo = créditos (amount_total) + deuda pública (amount_total) + facturas no pagadas (amount_total)
    - total_deuda_publica = suma deuda pública (amount_total)
    - num_acreedores = distinct de SituationCredit (creditor_tax_id si existe; si no, creditor)
    """
    _require_case(db, case_id)

    inv_open_rows = (
        db.query(
            SituationInvoice.currency,
            func.coalesce(func.sum(SituationInvoice.amount_total), 0.0),
        )
        .filter(
            SituationInvoice.case_id == case_id,
            SituationInvoice.is_current.is_(True),
            or_(
                SituationInvoice.status.is_(None),
                func.lower(SituationInvoice.status).notlike("pagad%"),
            ),
        )
        .group_by(SituationInvoice.currency)
        .all()
    )

    cred_rows = (
        db.query(
            SituationCredit.currency,
            func.coalesce(func.sum(SituationCredit.amount_total), 0.0),
        )
        .filter(SituationCredit.case_id == case_id, SituationCredit.is_current.is_(True))
        .group_by(SituationCredit.currency)
        .all()
    )

    pub_rows = (
        db.query(
            SituationPublicDebt.currency,
            func.coalesce(func.sum(SituationPublicDebt.amount_total), 0.0),
        )
        .filter(SituationPublicDebt.case_id == case_id, SituationPublicDebt.is_current.is_(True))
        .group_by(SituationPublicDebt.currency)
        .all()
    )

    # Totales y conteos
    num_facturas = int(
        db.query(SituationInvoice.record_id)
        .filter(SituationInvoice.case_id == case_id, SituationInvoice.is_current.is_(True))
        .count()
    )
    num_creditos = int(
        db.query(SituationCredit.record_id)
        .filter(SituationCredit.case_id == case_id, SituationCredit.is_current.is_(True))
        .count()
    )
    num_bienes = int(
        db.query(SituationAsset.record_id)
        .filter(SituationAsset.case_id == case_id, SituationAsset.is_current.is_(True))
        .count()
    )
    num_actuaciones = int(
        db.query(SituationCourtRecord.record_id)
        .filter(SituationCourtRecord.case_id == case_id, SituationCourtRecord.is_current.is_(True))
        .count()
    )

    num_acreedores = int(
        db.query(
            func.count(
                func.distinct(
                    func.lower(func.coalesce(SituationCredit.creditor_tax_id, SituationCredit.creditor))
                )
            )
        )
        .filter(SituationCredit.case_id == case_id, SituationCredit.is_current.is_(True))
        .scalar()
        or 0
    )

    inv_open_map = {c: float(v or 0.0) for c, v in inv_open_rows}
    cred_map = {c: float(v or 0.0) for c, v in cred_rows}
    pub_map = {c: float(v or 0.0) for c, v in pub_rows}

    currencies = sorted(set(inv_open_map.keys()) | set(cred_map.keys()) | set(pub_map.keys()))
    by_currency: list[SituationKpiCurrencyRow] = []
    for cur in currencies:
        inv_open = float(inv_open_map.get(cur, 0.0))
        cred_total = float(cred_map.get(cur, 0.0))
        pub_total = float(pub_map.get(cur, 0.0))
        by_currency.append(
            SituationKpiCurrencyRow(
                currency=cur,
                invoices_open=inv_open,
                credits_total=cred_total,
                public_debt_total=pub_total,
                total_pasivo=float(inv_open + cred_total + pub_total),
            )
        )

    total_deuda_publica = float(sum(pub_map.values()))
    total_pasivo = float(sum((inv_open_map.get(c, 0.0) + cred_map.get(c, 0.0) + pub_map.get(c, 0.0)) for c in currencies))

    return SituationKpisResponse(
        total_pasivo=total_pasivo,
        total_deuda_publica=total_deuda_publica,
        num_acreedores=num_acreedores,
        num_facturas=num_facturas,
        num_creditos=num_creditos,
        num_bienes=num_bienes,
        num_actuaciones=num_actuaciones,
        by_currency=by_currency,
    )


# =========================================================
# Endpoints — Invoices
# =========================================================


@router.get("/invoices", response_model=SituationListResponse, summary="Listar facturas (vigentes)")
def list_invoices(
    case_id: str,
    *,
    include_history: bool = Query(False, description="Si true, incluye versiones no vigentes"),
    supplier: Optional[str] = Query(None, min_length=2, max_length=255),
    status_txt: Optional[str] = Query(None, alias="status", max_length=40),
    invoice_number: Optional[str] = Query(None, max_length=100),
    due_from: Optional[str] = Query(None, max_length=10, description="YYYY-MM-DD"),
    due_to: Optional[str] = Query(None, max_length=10, description="YYYY-MM-DD"),
    min_amount: Optional[float] = Query(None, ge=0.0),
    max_amount: Optional[float] = Query(None, ge=0.0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SituationListResponse:
    _require_case(db, case_id)
    q = db.query(SituationInvoice).filter(SituationInvoice.case_id == case_id)
    if not include_history:
        q = q.filter(SituationInvoice.is_current.is_(True))
    if supplier:
        q = q.filter(SituationInvoice.supplier.ilike(f"%{supplier}%"))
    if status_txt:
        q = q.filter(SituationInvoice.status.ilike(f"%{status_txt}%"))
    if invoice_number:
        q = q.filter(SituationInvoice.invoice_number.ilike(f"%{invoice_number}%"))
    if due_from:
        q = q.filter(SituationInvoice.due_date.isnot(None), SituationInvoice.due_date >= due_from)
    if due_to:
        q = q.filter(SituationInvoice.due_date.isnot(None), SituationInvoice.due_date <= due_to)
    if min_amount is not None:
        q = q.filter(SituationInvoice.amount_total >= float(min_amount))
    if max_amount is not None:
        q = q.filter(SituationInvoice.amount_total <= float(max_amount))

    total = q.count()
    rows = (
        q.order_by(SituationInvoice.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items: list[SituationRecordSummary] = []
    for r in rows:
        items.append(
            SituationRecordSummary(
                logical_id=r.logical_id,
                record_id=r.record_id,
                version=r.version,
                is_current=r.is_current,
                created_at=r.created_at.isoformat(),
                created_by=r.created_by,
                data={
                    "supplier": r.supplier,
                    "supplier_tax_id": r.supplier_tax_id,
                    "supplier_address": r.supplier_address,
                    "supplier_email": r.supplier_email,
                    "buyer_name": r.buyer_name,
                    "buyer_tax_id": r.buyer_tax_id,
                    "buyer_address": r.buyer_address,
                    "buyer_email": r.buyer_email,
                    "invoice_number": r.invoice_number,
                    "contract_ref": r.contract_ref,
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
                evidence_count=_count_evidence(db, case_id=case_id, entity="INVOICE", record_id=r.record_id),
            )
        )
    return SituationListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/invoices/export.xlsx", summary="Exportar facturas (Excel)")
def export_invoices_excel(case_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    _require_case(db, case_id)
    rows = (
        db.query(SituationInvoice)
        .filter(SituationInvoice.case_id == case_id, SituationInvoice.is_current.is_(True))
        .order_by(SituationInvoice.created_at.desc())
        .all()
    )
    data_rows: list[dict[str, Any]] = []
    for r in rows:
        data_rows.append(
            {
                "logical_id": r.logical_id,
                "record_id": r.record_id,
                "version": r.version,
                "created_at": r.created_at.isoformat(),
                "created_by": r.created_by,
                "supplier": r.supplier,
                "supplier_tax_id": r.supplier_tax_id,
                "supplier_address": r.supplier_address,
                "supplier_email": r.supplier_email,
                "buyer_name": r.buyer_name,
                "buyer_tax_id": r.buyer_tax_id,
                "buyer_address": r.buyer_address,
                "buyer_email": r.buyer_email,
                "invoice_number": r.invoice_number,
                "contract_ref": r.contract_ref,
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
                "evidence_count": _count_evidence(db, case_id=case_id, entity="INVOICE", record_id=r.record_id),
            }
        )
    return _export_rows_to_xlsx(
        data_rows,
        sheet_name="Facturas",
        filename=f"situation_invoices_{case_id}.xlsx",
    )


@router.post("/invoices", response_model=SituationRecordSummary, summary="Crear factura")
def create_invoice(case_id: str, req: CreateInvoiceRequest, db: Session = Depends(get_db)) -> SituationRecordSummary:
    _require_case(db, case_id)
    _validate_evidence(db, case_id, req.evidence)

    payload_for_validation = {
        "issue_date": req.issue_date,
        "due_date": req.due_date,
        "paid_date": req.paid_date,
        "status": req.status,
        "base_amount": req.base_amount,
        "vat_amount": req.vat_amount,
        "withholding_amount": req.withholding_amount,
        "amount_total": req.amount_total,
    }
    _validate_invoice_consistency(payload=payload_for_validation)
    _check_duplicate_invoice(
        db,
        case_id=case_id,
        supplier_tax_id=req.supplier_tax_id,
        invoice_number=req.invoice_number,
        issue_date=req.issue_date,
    )

    logical_id = _new_logical_id()
    record = SituationInvoice(
        logical_id=logical_id,
        case_id=case_id,
        version=1,
        is_current=True,
        created_by=req.created_by,
        supplier=req.supplier,
        supplier_tax_id=req.supplier_tax_id,
        supplier_address=req.supplier_address,
        supplier_email=req.supplier_email,
        buyer_name=req.buyer_name,
        buyer_tax_id=req.buyer_tax_id,
        buyer_address=req.buyer_address,
        buyer_email=req.buyer_email,
        invoice_number=req.invoice_number,
        contract_ref=req.contract_ref,
        issue_date=req.issue_date,
        due_date=req.due_date,
        paid_date=req.paid_date,
        currency=req.currency,
        currency_fx_rate=req.currency_fx_rate,
        base_amount=req.base_amount,
        vat_amount=req.vat_amount,
        withholding_amount=req.withholding_amount,
        amount_total=req.amount_total,
        status=req.status,
        payment_terms=req.payment_terms,
        payment_method=req.payment_method,
        iban_masked=req.iban_masked,
        invoice_type=req.invoice_type,
        source_ref=req.source_ref,
        is_disputed=req.is_disputed,
        dispute_reason=req.dispute_reason,
        notes=req.notes,
    )
    db.add(record)
    db.flush()

    _insert_evidence(
        db=db,
        case_id=case_id,
        entity="INVOICE",
        record_id=record.record_id,
        created_by=req.created_by,
        evidence=req.evidence,
    )
    _audit(
        db=db,
        case_id=case_id,
        entity="INVOICE",
        logical_id=logical_id,
        record_id=record.record_id,
        action="CREATE",
        actor=req.created_by,
        reason=req.reason,
        before=None,
        after={
            "supplier": record.supplier,
            "supplier_tax_id": record.supplier_tax_id,
            "supplier_address": record.supplier_address,
            "supplier_email": record.supplier_email,
            "buyer_name": record.buyer_name,
            "buyer_tax_id": record.buyer_tax_id,
            "buyer_address": record.buyer_address,
            "buyer_email": record.buyer_email,
            "invoice_number": record.invoice_number,
            "contract_ref": record.contract_ref,
            "issue_date": record.issue_date,
            "due_date": record.due_date,
            "paid_date": record.paid_date,
            "currency": record.currency,
            "currency_fx_rate": record.currency_fx_rate,
            "base_amount": record.base_amount,
            "vat_amount": record.vat_amount,
            "withholding_amount": record.withholding_amount,
            "amount_total": record.amount_total,
            "status": record.status,
            "payment_terms": record.payment_terms,
            "payment_method": record.payment_method,
            "iban_masked": record.iban_masked,
            "invoice_type": record.invoice_type,
            "source_ref": record.source_ref,
            "is_disputed": record.is_disputed,
            "dispute_reason": record.dispute_reason,
            "notes": record.notes,
        },
    )

    db.commit()
    db.refresh(record)

    return SituationRecordSummary(
        logical_id=record.logical_id,
        record_id=record.record_id,
        version=record.version,
        is_current=record.is_current,
        created_at=record.created_at.isoformat(),
        created_by=record.created_by,
        data={
            "supplier": record.supplier,
            "supplier_tax_id": record.supplier_tax_id,
            "supplier_address": record.supplier_address,
            "supplier_email": record.supplier_email,
            "buyer_name": record.buyer_name,
            "buyer_tax_id": record.buyer_tax_id,
            "buyer_address": record.buyer_address,
            "buyer_email": record.buyer_email,
            "invoice_number": record.invoice_number,
            "contract_ref": record.contract_ref,
            "issue_date": record.issue_date,
            "due_date": record.due_date,
            "paid_date": record.paid_date,
            "currency": record.currency,
            "currency_fx_rate": record.currency_fx_rate,
            "base_amount": record.base_amount,
            "vat_amount": record.vat_amount,
            "withholding_amount": record.withholding_amount,
            "amount_total": record.amount_total,
            "status": record.status,
            "payment_terms": record.payment_terms,
            "payment_method": record.payment_method,
            "iban_masked": record.iban_masked,
            "invoice_type": record.invoice_type,
            "source_ref": record.source_ref,
            "is_disputed": record.is_disputed,
            "dispute_reason": record.dispute_reason,
            "notes": record.notes,
        },
        evidence_count=_count_evidence(db, case_id=case_id, entity="INVOICE", record_id=record.record_id),
    )


@router.post("/invoices/update", response_model=SituationRecordSummary, summary="Actualizar factura (nueva versión)")
def update_invoice(case_id: str, req: UpdateInvoiceRequest, db: Session = Depends(get_db)) -> SituationRecordSummary:
    _require_case(db, case_id)
    _validate_evidence(db, case_id, req.evidence)

    current = (
        db.query(SituationInvoice)
        .filter(
            SituationInvoice.case_id == case_id,
            SituationInvoice.logical_id == req.logical_id,
            SituationInvoice.is_current.is_(True),
        )
        .first()
    )
    if not current:
        raise HTTPException(status_code=404, detail="Factura no encontrada (logical_id)")
    if current.version != req.expected_version:
        raise HTTPException(
            status_code=409,
            detail=f"CONCURRENT_MODIFICATION: expected_version={req.expected_version}, actual={current.version}",
        )

    before = {
        "supplier": current.supplier,
        "supplier_tax_id": current.supplier_tax_id,
        "supplier_address": current.supplier_address,
        "supplier_email": current.supplier_email,
        "buyer_name": current.buyer_name,
        "buyer_tax_id": current.buyer_tax_id,
        "buyer_address": current.buyer_address,
        "buyer_email": current.buyer_email,
        "invoice_number": current.invoice_number,
        "contract_ref": current.contract_ref,
        "issue_date": current.issue_date,
        "due_date": current.due_date,
        "paid_date": current.paid_date,
        "currency": current.currency,
        "currency_fx_rate": current.currency_fx_rate,
        "base_amount": current.base_amount,
        "vat_amount": current.vat_amount,
        "withholding_amount": current.withholding_amount,
        "amount_total": current.amount_total,
        "status": current.status,
        "payment_terms": current.payment_terms,
        "payment_method": current.payment_method,
        "iban_masked": current.iban_masked,
        "invoice_type": current.invoice_type,
        "source_ref": current.source_ref,
        "is_disputed": current.is_disputed,
        "dispute_reason": current.dispute_reason,
        "notes": current.notes,
    }

    # Cerrar vigente anterior
    current.is_current = False
    db.flush()

    # Nueva versión
    record = SituationInvoice(
        logical_id=current.logical_id,
        case_id=case_id,
        version=current.version + 1,
        is_current=True,
        supersedes_record_id=current.record_id,
        created_by=req.created_by,
        supplier=req.supplier if req.supplier is not None else current.supplier,
        supplier_tax_id=req.supplier_tax_id if req.supplier_tax_id is not None else current.supplier_tax_id,
        supplier_address=req.supplier_address if req.supplier_address is not None else current.supplier_address,
        supplier_email=req.supplier_email if req.supplier_email is not None else current.supplier_email,
        buyer_name=req.buyer_name if req.buyer_name is not None else current.buyer_name,
        buyer_tax_id=req.buyer_tax_id if req.buyer_tax_id is not None else current.buyer_tax_id,
        buyer_address=req.buyer_address if req.buyer_address is not None else current.buyer_address,
        buyer_email=req.buyer_email if req.buyer_email is not None else current.buyer_email,
        invoice_number=req.invoice_number if req.invoice_number is not None else current.invoice_number,
        contract_ref=req.contract_ref if req.contract_ref is not None else current.contract_ref,
        issue_date=req.issue_date if req.issue_date is not None else current.issue_date,
        due_date=req.due_date if req.due_date is not None else current.due_date,
        paid_date=req.paid_date if req.paid_date is not None else current.paid_date,
        currency=req.currency if req.currency is not None else current.currency,
        currency_fx_rate=req.currency_fx_rate if req.currency_fx_rate is not None else current.currency_fx_rate,
        base_amount=req.base_amount if req.base_amount is not None else current.base_amount,
        vat_amount=req.vat_amount if req.vat_amount is not None else current.vat_amount,
        withholding_amount=req.withholding_amount if req.withholding_amount is not None else current.withholding_amount,
        amount_total=req.amount_total if req.amount_total is not None else current.amount_total,
        status=req.status if req.status is not None else current.status,
        payment_terms=req.payment_terms if req.payment_terms is not None else current.payment_terms,
        payment_method=req.payment_method if req.payment_method is not None else current.payment_method,
        iban_masked=req.iban_masked if req.iban_masked is not None else current.iban_masked,
        invoice_type=req.invoice_type if req.invoice_type is not None else current.invoice_type,
        source_ref=req.source_ref if req.source_ref is not None else current.source_ref,
        is_disputed=req.is_disputed if req.is_disputed is not None else current.is_disputed,
        dispute_reason=req.dispute_reason if req.dispute_reason is not None else current.dispute_reason,
        notes=req.notes if req.notes is not None else current.notes,
    )
    db.add(record)
    db.flush()

    _insert_evidence(
        db=db,
        case_id=case_id,
        entity="INVOICE",
        record_id=record.record_id,
        created_by=req.created_by,
        evidence=req.evidence,
    )

    after = {
        "supplier": record.supplier,
        "supplier_tax_id": record.supplier_tax_id,
        "supplier_address": record.supplier_address,
        "supplier_email": record.supplier_email,
        "buyer_name": record.buyer_name,
        "buyer_tax_id": record.buyer_tax_id,
        "buyer_address": record.buyer_address,
        "buyer_email": record.buyer_email,
        "invoice_number": record.invoice_number,
        "contract_ref": record.contract_ref,
        "issue_date": record.issue_date,
        "due_date": record.due_date,
        "paid_date": record.paid_date,
        "currency": record.currency,
        "currency_fx_rate": record.currency_fx_rate,
        "base_amount": record.base_amount,
        "vat_amount": record.vat_amount,
        "withholding_amount": record.withholding_amount,
        "amount_total": record.amount_total,
        "status": record.status,
        "payment_terms": record.payment_terms,
        "payment_method": record.payment_method,
        "iban_masked": record.iban_masked,
        "invoice_type": record.invoice_type,
        "source_ref": record.source_ref,
        "is_disputed": record.is_disputed,
        "dispute_reason": record.dispute_reason,
        "notes": record.notes,
    }
    _validate_invoice_consistency(payload=after)
    _check_duplicate_invoice(
        db,
        case_id=case_id,
        supplier_tax_id=record.supplier_tax_id,
        invoice_number=record.invoice_number,
        issue_date=record.issue_date,
        exclude_logical_id=record.logical_id,
    )
    _audit(
        db=db,
        case_id=case_id,
        entity="INVOICE",
        logical_id=record.logical_id,
        record_id=record.record_id,
        action="UPDATE",
        actor=req.created_by,
        reason=req.reason,
        before=before,
        after=after,
    )

    db.commit()
    db.refresh(record)

    return SituationRecordSummary(
        logical_id=record.logical_id,
        record_id=record.record_id,
        version=record.version,
        is_current=record.is_current,
        created_at=record.created_at.isoformat(),
        created_by=record.created_by,
        data=after,
        evidence_count=_count_evidence(db, case_id=case_id, entity="INVOICE", record_id=record.record_id),
    )


# =========================================================
# Endpoints — Credits
# =========================================================


@router.get("/credits", response_model=SituationListResponse, summary="Listar créditos (vigentes)")
def list_credits(
    case_id: str,
    *,
    include_history: bool = Query(False),
    creditor: Optional[str] = Query(None, min_length=2, max_length=255),
    secured: Optional[bool] = Query(None),
    min_amount: Optional[float] = Query(None, ge=0.0),
    max_amount: Optional[float] = Query(None, ge=0.0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SituationListResponse:
    _require_case(db, case_id)
    q = db.query(SituationCredit).filter(SituationCredit.case_id == case_id)
    if not include_history:
        q = q.filter(SituationCredit.is_current.is_(True))
    if creditor:
        q = q.filter(SituationCredit.creditor.ilike(f"%{creditor}%"))
    if secured is not None:
        q = q.filter(SituationCredit.secured.is_(bool(secured)))
    if min_amount is not None:
        q = q.filter(SituationCredit.amount_total >= float(min_amount))
    if max_amount is not None:
        q = q.filter(SituationCredit.amount_total <= float(max_amount))

    total = q.count()
    rows = (
        q.order_by(SituationCredit.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items: list[SituationRecordSummary] = []
    for r in rows:
        items.append(
            SituationRecordSummary(
                logical_id=r.logical_id,
                record_id=r.record_id,
                version=r.version,
                is_current=r.is_current,
                created_at=r.created_at.isoformat(),
                created_by=r.created_by,
                data={
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
                evidence_count=_count_evidence(db, case_id=case_id, entity="CREDIT", record_id=r.record_id),
            )
        )
    return SituationListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/credits/export.xlsx", summary="Exportar créditos (Excel)")
def export_credits_excel(case_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    _require_case(db, case_id)
    rows = (
        db.query(SituationCredit)
        .filter(SituationCredit.case_id == case_id, SituationCredit.is_current.is_(True))
        .order_by(SituationCredit.created_at.desc())
        .all()
    )
    data_rows: list[dict[str, Any]] = []
    for r in rows:
        data_rows.append(
            {
                "logical_id": r.logical_id,
                "record_id": r.record_id,
                "version": r.version,
                "created_at": r.created_at.isoformat(),
                "created_by": r.created_by,
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
                "evidence_count": _count_evidence(db, case_id=case_id, entity="CREDIT", record_id=r.record_id),
            }
        )
    return _export_rows_to_xlsx(
        data_rows,
        sheet_name="Creditos",
        filename=f"situation_credits_{case_id}.xlsx",
    )


@router.post("/credits", response_model=SituationRecordSummary, summary="Crear crédito")
def create_credit(case_id: str, req: CreateCreditRequest, db: Session = Depends(get_db)) -> SituationRecordSummary:
    _require_case(db, case_id)
    _validate_evidence(db, case_id, req.evidence)

    # Validación de fechas (formato) y duplicados
    _parse_iso_date(req.maturity_date, field="maturity_date")
    _parse_iso_date(req.default_date, field="default_date")
    _parse_iso_date(req.last_payment_date, field="last_payment_date")
    _validate_credit_consistency(
        payload={
            "principal_initial": req.principal_initial,
            "outstanding_principal": req.outstanding_principal,
            "interest_rate": req.interest_rate,
            "default_date": req.default_date,
            "last_payment_date": req.last_payment_date,
            "maturity_date": req.maturity_date,
        }
    )
    _check_duplicate_credit(
        db,
        case_id=case_id,
        creditor_tax_id=req.creditor_tax_id,
        contract_ref=req.contract_ref,
    )

    logical_id = _new_logical_id()
    record = SituationCredit(
        logical_id=logical_id,
        case_id=case_id,
        version=1,
        is_current=True,
        created_by=req.created_by,
        creditor=req.creditor,
        creditor_tax_id=req.creditor_tax_id,
        lender_address=req.lender_address,
        lender_email=req.lender_email,
        lender_phone=req.lender_phone,
        contract_ref=req.contract_ref,
        currency=req.currency,
        amount_total=req.amount_total,
        principal_initial=req.principal_initial,
        outstanding_principal=req.outstanding_principal,
        accrued_interest=req.accrued_interest,
        interest_rate=req.interest_rate,
        interest_type=req.interest_type,
        spread=req.spread,
        secured=req.secured,
        guarantee_details=req.guarantee_details,
        secured_type=req.secured_type,
        collateral_description=req.collateral_description,
        collateral_registry_ref=req.collateral_registry_ref,
        guarantor_name=req.guarantor_name,
        guarantor_tax_id=req.guarantor_tax_id,
        maturity_date=req.maturity_date,
        default_date=req.default_date,
        last_payment_date=req.last_payment_date,
        enforcement_stage=req.enforcement_stage,
        procedure_ref=req.procedure_ref,
        notes=req.notes,
    )
    db.add(record)
    db.flush()

    _insert_evidence(
        db=db,
        case_id=case_id,
        entity="CREDIT",
        record_id=record.record_id,
        created_by=req.created_by,
        evidence=req.evidence,
    )
    after = {
        "creditor": record.creditor,
        "creditor_tax_id": record.creditor_tax_id,
        "lender_address": record.lender_address,
        "lender_email": record.lender_email,
        "lender_phone": record.lender_phone,
        "contract_ref": record.contract_ref,
        "currency": record.currency,
        "amount_total": record.amount_total,
        "principal_initial": record.principal_initial,
        "outstanding_principal": record.outstanding_principal,
        "accrued_interest": record.accrued_interest,
        "interest_rate": record.interest_rate,
        "interest_type": record.interest_type,
        "spread": record.spread,
        "secured": record.secured,
        "guarantee_details": record.guarantee_details,
        "secured_type": record.secured_type,
        "collateral_description": record.collateral_description,
        "collateral_registry_ref": record.collateral_registry_ref,
        "guarantor_name": record.guarantor_name,
        "guarantor_tax_id": record.guarantor_tax_id,
        "maturity_date": record.maturity_date,
        "default_date": record.default_date,
        "last_payment_date": record.last_payment_date,
        "enforcement_stage": record.enforcement_stage,
        "procedure_ref": record.procedure_ref,
        "notes": record.notes,
    }
    _validate_credit_consistency(payload=after)
    _audit(
        db=db,
        case_id=case_id,
        entity="CREDIT",
        logical_id=logical_id,
        record_id=record.record_id,
        action="CREATE",
        actor=req.created_by,
        reason=req.reason,
        before=None,
        after=after,
    )

    db.commit()
    db.refresh(record)
    return SituationRecordSummary(
        logical_id=record.logical_id,
        record_id=record.record_id,
        version=record.version,
        is_current=record.is_current,
        created_at=record.created_at.isoformat(),
        created_by=record.created_by,
        data=after,
        evidence_count=_count_evidence(db, case_id=case_id, entity="CREDIT", record_id=record.record_id),
    )


@router.post("/credits/update", response_model=SituationRecordSummary, summary="Actualizar crédito (nueva versión)")
def update_credit(case_id: str, req: UpdateCreditRequest, db: Session = Depends(get_db)) -> SituationRecordSummary:
    _require_case(db, case_id)
    _validate_evidence(db, case_id, req.evidence)

    current = (
        db.query(SituationCredit)
        .filter(
            SituationCredit.case_id == case_id,
            SituationCredit.logical_id == req.logical_id,
            SituationCredit.is_current.is_(True),
        )
        .first()
    )
    if not current:
        raise HTTPException(status_code=404, detail="Crédito no encontrado (logical_id)")
    if current.version != req.expected_version:
        raise HTTPException(
            status_code=409,
            detail=f"CONCURRENT_MODIFICATION: expected_version={req.expected_version}, actual={current.version}",
        )

    before = {
        "creditor": current.creditor,
        "creditor_tax_id": current.creditor_tax_id,
        "lender_address": current.lender_address,
        "lender_email": current.lender_email,
        "lender_phone": current.lender_phone,
        "contract_ref": current.contract_ref,
        "currency": current.currency,
        "amount_total": current.amount_total,
        "principal_initial": current.principal_initial,
        "outstanding_principal": current.outstanding_principal,
        "accrued_interest": current.accrued_interest,
        "interest_rate": current.interest_rate,
        "interest_type": current.interest_type,
        "spread": current.spread,
        "secured": current.secured,
        "guarantee_details": current.guarantee_details,
        "secured_type": current.secured_type,
        "collateral_description": current.collateral_description,
        "collateral_registry_ref": current.collateral_registry_ref,
        "guarantor_name": current.guarantor_name,
        "guarantor_tax_id": current.guarantor_tax_id,
        "maturity_date": current.maturity_date,
        "default_date": current.default_date,
        "last_payment_date": current.last_payment_date,
        "enforcement_stage": current.enforcement_stage,
        "procedure_ref": current.procedure_ref,
        "notes": current.notes,
    }

    current.is_current = False
    db.flush()

    record = SituationCredit(
        logical_id=current.logical_id,
        case_id=case_id,
        version=current.version + 1,
        is_current=True,
        supersedes_record_id=current.record_id,
        created_by=req.created_by,
        creditor=req.creditor if req.creditor is not None else current.creditor,
        creditor_tax_id=req.creditor_tax_id if req.creditor_tax_id is not None else current.creditor_tax_id,
        lender_address=req.lender_address if req.lender_address is not None else current.lender_address,
        lender_email=req.lender_email if req.lender_email is not None else current.lender_email,
        lender_phone=req.lender_phone if req.lender_phone is not None else current.lender_phone,
        contract_ref=req.contract_ref if req.contract_ref is not None else current.contract_ref,
        currency=req.currency if req.currency is not None else current.currency,
        amount_total=req.amount_total if req.amount_total is not None else current.amount_total,
        principal_initial=req.principal_initial
        if req.principal_initial is not None
        else current.principal_initial,
        outstanding_principal=req.outstanding_principal
        if req.outstanding_principal is not None
        else current.outstanding_principal,
        accrued_interest=req.accrued_interest if req.accrued_interest is not None else current.accrued_interest,
        interest_rate=req.interest_rate if req.interest_rate is not None else current.interest_rate,
        interest_type=req.interest_type if req.interest_type is not None else current.interest_type,
        spread=req.spread if req.spread is not None else current.spread,
        secured=req.secured if req.secured is not None else current.secured,
        guarantee_details=req.guarantee_details
        if req.guarantee_details is not None
        else current.guarantee_details,
        secured_type=req.secured_type if req.secured_type is not None else current.secured_type,
        collateral_description=req.collateral_description
        if req.collateral_description is not None
        else current.collateral_description,
        collateral_registry_ref=req.collateral_registry_ref
        if req.collateral_registry_ref is not None
        else current.collateral_registry_ref,
        guarantor_name=req.guarantor_name if req.guarantor_name is not None else current.guarantor_name,
        guarantor_tax_id=req.guarantor_tax_id if req.guarantor_tax_id is not None else current.guarantor_tax_id,
        maturity_date=req.maturity_date if req.maturity_date is not None else current.maturity_date,
        default_date=req.default_date if req.default_date is not None else current.default_date,
        last_payment_date=req.last_payment_date if req.last_payment_date is not None else current.last_payment_date,
        enforcement_stage=req.enforcement_stage if req.enforcement_stage is not None else current.enforcement_stage,
        procedure_ref=req.procedure_ref if req.procedure_ref is not None else current.procedure_ref,
        notes=req.notes if req.notes is not None else current.notes,
    )
    db.add(record)
    db.flush()

    _insert_evidence(
        db=db,
        case_id=case_id,
        entity="CREDIT",
        record_id=record.record_id,
        created_by=req.created_by,
        evidence=req.evidence,
    )

    after = {
        "creditor": record.creditor,
        "creditor_tax_id": record.creditor_tax_id,
        "lender_address": record.lender_address,
        "lender_email": record.lender_email,
        "lender_phone": record.lender_phone,
        "contract_ref": record.contract_ref,
        "currency": record.currency,
        "amount_total": record.amount_total,
        "principal_initial": record.principal_initial,
        "outstanding_principal": record.outstanding_principal,
        "accrued_interest": record.accrued_interest,
        "interest_rate": record.interest_rate,
        "interest_type": record.interest_type,
        "spread": record.spread,
        "secured": record.secured,
        "guarantee_details": record.guarantee_details,
        "secured_type": record.secured_type,
        "collateral_description": record.collateral_description,
        "collateral_registry_ref": record.collateral_registry_ref,
        "guarantor_name": record.guarantor_name,
        "guarantor_tax_id": record.guarantor_tax_id,
        "maturity_date": record.maturity_date,
        "default_date": record.default_date,
        "last_payment_date": record.last_payment_date,
        "enforcement_stage": record.enforcement_stage,
        "procedure_ref": record.procedure_ref,
        "notes": record.notes,
    }
    _parse_iso_date(record.maturity_date, field="maturity_date")
    _parse_iso_date(record.default_date, field="default_date")
    _parse_iso_date(record.last_payment_date, field="last_payment_date")
    _validate_credit_consistency(payload=after)
    _check_duplicate_credit(
        db,
        case_id=case_id,
        creditor_tax_id=record.creditor_tax_id,
        contract_ref=record.contract_ref,
        exclude_logical_id=record.logical_id,
    )
    _audit(
        db=db,
        case_id=case_id,
        entity="CREDIT",
        logical_id=record.logical_id,
        record_id=record.record_id,
        action="UPDATE",
        actor=req.created_by,
        reason=req.reason,
        before=before,
        after=after,
    )

    db.commit()
    db.refresh(record)
    return SituationRecordSummary(
        logical_id=record.logical_id,
        record_id=record.record_id,
        version=record.version,
        is_current=record.is_current,
        created_at=record.created_at.isoformat(),
        created_by=record.created_by,
        data=after,
        evidence_count=_count_evidence(db, case_id=case_id, entity="CREDIT", record_id=record.record_id),
    )


# =========================================================
# Endpoints — Assets
# =========================================================


@router.get("/assets", response_model=SituationListResponse, summary="Listar bienes (vigentes)")
def list_assets(
    case_id: str,
    *,
    include_history: bool = Query(False, description="Si true, incluye versiones no vigentes"),
    asset_type: Optional[str] = Query(None, max_length=40),
    description: Optional[str] = Query(None, min_length=2, max_length=500),
    min_val_ac: Optional[float] = Query(None, ge=0.0),
    max_val_ac: Optional[float] = Query(None, ge=0.0),
    min_val_ext: Optional[float] = Query(None, ge=0.0),
    max_val_ext: Optional[float] = Query(None, ge=0.0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SituationListResponse:
    _require_case(db, case_id)
    q = db.query(SituationAsset).filter(SituationAsset.case_id == case_id)
    if not include_history:
        q = q.filter(SituationAsset.is_current.is_(True))
    if asset_type:
        q = q.filter(SituationAsset.asset_type == asset_type)
    if description:
        q = q.filter(SituationAsset.description.ilike(f"%{description}%"))
    if min_val_ac is not None:
        q = q.filter(
            SituationAsset.valuation_admin_concursal.isnot(None),
            SituationAsset.valuation_admin_concursal >= float(min_val_ac),
        )
    if max_val_ac is not None:
        q = q.filter(
            SituationAsset.valuation_admin_concursal.isnot(None),
            SituationAsset.valuation_admin_concursal <= float(max_val_ac),
        )
    if min_val_ext is not None:
        q = q.filter(
            SituationAsset.valuation_external.isnot(None),
            SituationAsset.valuation_external >= float(min_val_ext),
        )
    if max_val_ext is not None:
        q = q.filter(
            SituationAsset.valuation_external.isnot(None),
            SituationAsset.valuation_external <= float(max_val_ext),
        )

    total = q.count()
    rows = (
        q.order_by(SituationAsset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items: list[SituationRecordSummary] = []
    for r in rows:
        items.append(
            SituationRecordSummary(
                logical_id=r.logical_id,
                record_id=r.record_id,
                version=r.version,
                is_current=r.is_current,
                created_at=r.created_at.isoformat(),
                created_by=r.created_by,
                data={
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
                evidence_count=_count_evidence(db, case_id=case_id, entity="ASSET", record_id=r.record_id),
            )
        )
    return SituationListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/assets/export.xlsx", summary="Exportar bienes (Excel)")
def export_assets_excel(case_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    _require_case(db, case_id)
    rows = (
        db.query(SituationAsset)
        .filter(SituationAsset.case_id == case_id, SituationAsset.is_current.is_(True))
        .order_by(SituationAsset.created_at.desc())
        .all()
    )
    data_rows: list[dict[str, Any]] = []
    for r in rows:
        data_rows.append(
            {
                "logical_id": r.logical_id,
                "record_id": r.record_id,
                "version": r.version,
                "created_at": r.created_at.isoformat(),
                "created_by": r.created_by,
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
                "evidence_count": _count_evidence(db, case_id=case_id, entity="ASSET", record_id=r.record_id),
            }
        )
    return _export_rows_to_xlsx(
        data_rows,
        sheet_name="Bienes",
        filename=f"situation_assets_{case_id}.xlsx",
    )


@router.post("/assets", response_model=SituationRecordSummary, summary="Crear bien")
def create_asset(case_id: str, req: CreateAssetRequest, db: Session = Depends(get_db)) -> SituationRecordSummary:
    _require_case(db, case_id)
    _validate_evidence(db, case_id, req.evidence)

    _parse_iso_date(req.acquisition_date, field="acquisition_date")
    _parse_iso_date(req.valuation_date, field="valuation_date")

    logical_id = _new_logical_id()
    record = SituationAsset(
        logical_id=logical_id,
        case_id=case_id,
        version=1,
        is_current=True,
        created_by=req.created_by,
        asset_type=req.asset_type,
        description=req.description,
        location=req.location,
        owner=req.owner,
        ownership_share=req.ownership_share,
        acquisition_date=req.acquisition_date,
        acquisition_value=req.acquisition_value,
        address_full=req.address_full,
        city=req.city,
        postal_code=req.postal_code,
        province=req.province,
        cadastral_ref=req.cadastral_ref,
        registry_type=req.registry_type,
        registry_ref=req.registry_ref,
        finca_registral=req.finca_registral,
        tomo=req.tomo,
        libro=req.libro,
        folio=req.folio,
        currency=req.currency,
        valuation_admin_concursal=req.valuation_admin_concursal,
        valuation_external=req.valuation_external,
        valuation_date=req.valuation_date,
        liens=req.liens,
        encumbrances_full=req.encumbrances_full,
        mortgage_bank=req.mortgage_bank,
        mortgage_outstanding=req.mortgage_outstanding,
        disposal_status=req.disposal_status,
        occupancy_status=req.occupancy_status,
        notes=req.notes,
    )
    db.add(record)
    db.flush()
    _insert_evidence(
        db=db,
        case_id=case_id,
        entity="ASSET",
        record_id=record.record_id,
        created_by=req.created_by,
        evidence=req.evidence,
    )

    after = {
        "asset_type": record.asset_type,
        "description": record.description,
        "location": record.location,
        "owner": record.owner,
        "ownership_share": record.ownership_share,
        "acquisition_date": record.acquisition_date,
        "acquisition_value": record.acquisition_value,
        "address_full": record.address_full,
        "city": record.city,
        "postal_code": record.postal_code,
        "province": record.province,
        "cadastral_ref": record.cadastral_ref,
        "registry_type": record.registry_type,
        "registry_ref": record.registry_ref,
        "finca_registral": record.finca_registral,
        "tomo": record.tomo,
        "libro": record.libro,
        "folio": record.folio,
        "currency": record.currency,
        "valuation_admin_concursal": record.valuation_admin_concursal,
        "valuation_external": record.valuation_external,
        "valuation_date": record.valuation_date,
        "liens": record.liens,
        "encumbrances_full": record.encumbrances_full,
        "mortgage_bank": record.mortgage_bank,
        "mortgage_outstanding": record.mortgage_outstanding,
        "disposal_status": record.disposal_status,
        "occupancy_status": record.occupancy_status,
        "notes": record.notes,
    }
    _audit(
        db=db,
        case_id=case_id,
        entity="ASSET",
        logical_id=logical_id,
        record_id=record.record_id,
        action="CREATE",
        actor=req.created_by,
        reason=req.reason,
        before=None,
        after=after,
    )

    db.commit()
    db.refresh(record)
    return SituationRecordSummary(
        logical_id=record.logical_id,
        record_id=record.record_id,
        version=record.version,
        is_current=record.is_current,
        created_at=record.created_at.isoformat(),
        created_by=record.created_by,
        data=after,
        evidence_count=_count_evidence(db, case_id=case_id, entity="ASSET", record_id=record.record_id),
    )


@router.post("/assets/update", response_model=SituationRecordSummary, summary="Actualizar bien (nueva versión)")
def update_asset(case_id: str, req: UpdateAssetRequest, db: Session = Depends(get_db)) -> SituationRecordSummary:
    _require_case(db, case_id)
    _validate_evidence(db, case_id, req.evidence)

    current = (
        db.query(SituationAsset)
        .filter(
            SituationAsset.case_id == case_id,
            SituationAsset.logical_id == req.logical_id,
            SituationAsset.is_current.is_(True),
        )
        .first()
    )
    if not current:
        raise HTTPException(status_code=404, detail="Bien no encontrado (logical_id)")
    if current.version != req.expected_version:
        raise HTTPException(
            status_code=409,
            detail=f"CONCURRENT_MODIFICATION: expected_version={req.expected_version}, actual={current.version}",
        )

    before = {
        "asset_type": current.asset_type,
        "description": current.description,
        "location": current.location,
        "owner": current.owner,
        "ownership_share": current.ownership_share,
        "acquisition_date": current.acquisition_date,
        "acquisition_value": current.acquisition_value,
        "address_full": current.address_full,
        "city": current.city,
        "postal_code": current.postal_code,
        "province": current.province,
        "cadastral_ref": current.cadastral_ref,
        "registry_type": current.registry_type,
        "registry_ref": current.registry_ref,
        "finca_registral": current.finca_registral,
        "tomo": current.tomo,
        "libro": current.libro,
        "folio": current.folio,
        "currency": current.currency,
        "valuation_admin_concursal": current.valuation_admin_concursal,
        "valuation_external": current.valuation_external,
        "valuation_date": current.valuation_date,
        "liens": current.liens,
        "encumbrances_full": current.encumbrances_full,
        "mortgage_bank": current.mortgage_bank,
        "mortgage_outstanding": current.mortgage_outstanding,
        "disposal_status": current.disposal_status,
        "occupancy_status": current.occupancy_status,
        "notes": current.notes,
    }

    current.is_current = False
    db.flush()

    record = SituationAsset(
        logical_id=current.logical_id,
        case_id=case_id,
        version=current.version + 1,
        is_current=True,
        supersedes_record_id=current.record_id,
        created_by=req.created_by,
        asset_type=req.asset_type if req.asset_type is not None else current.asset_type,
        description=req.description if req.description is not None else current.description,
        location=req.location if req.location is not None else current.location,
        owner=req.owner if req.owner is not None else current.owner,
        ownership_share=req.ownership_share if req.ownership_share is not None else current.ownership_share,
        acquisition_date=req.acquisition_date if req.acquisition_date is not None else current.acquisition_date,
        acquisition_value=req.acquisition_value if req.acquisition_value is not None else current.acquisition_value,
        address_full=req.address_full if req.address_full is not None else current.address_full,
        city=req.city if req.city is not None else current.city,
        postal_code=req.postal_code if req.postal_code is not None else current.postal_code,
        province=req.province if req.province is not None else current.province,
        cadastral_ref=req.cadastral_ref if req.cadastral_ref is not None else current.cadastral_ref,
        registry_type=req.registry_type if req.registry_type is not None else current.registry_type,
        registry_ref=req.registry_ref if req.registry_ref is not None else current.registry_ref,
        finca_registral=req.finca_registral if req.finca_registral is not None else current.finca_registral,
        tomo=req.tomo if req.tomo is not None else current.tomo,
        libro=req.libro if req.libro is not None else current.libro,
        folio=req.folio if req.folio is not None else current.folio,
        currency=req.currency if req.currency is not None else current.currency,
        valuation_admin_concursal=req.valuation_admin_concursal
        if req.valuation_admin_concursal is not None
        else current.valuation_admin_concursal,
        valuation_external=req.valuation_external
        if req.valuation_external is not None
        else current.valuation_external,
        valuation_date=req.valuation_date if req.valuation_date is not None else current.valuation_date,
        liens=req.liens if req.liens is not None else current.liens,
        encumbrances_full=req.encumbrances_full
        if req.encumbrances_full is not None
        else current.encumbrances_full,
        mortgage_bank=req.mortgage_bank if req.mortgage_bank is not None else current.mortgage_bank,
        mortgage_outstanding=req.mortgage_outstanding
        if req.mortgage_outstanding is not None
        else current.mortgage_outstanding,
        disposal_status=req.disposal_status if req.disposal_status is not None else current.disposal_status,
        occupancy_status=req.occupancy_status if req.occupancy_status is not None else current.occupancy_status,
        notes=req.notes if req.notes is not None else current.notes,
    )
    db.add(record)
    db.flush()

    _insert_evidence(
        db=db,
        case_id=case_id,
        entity="ASSET",
        record_id=record.record_id,
        created_by=req.created_by,
        evidence=req.evidence,
    )

    after = {
        "asset_type": record.asset_type,
        "description": record.description,
        "location": record.location,
        "owner": record.owner,
        "ownership_share": record.ownership_share,
        "acquisition_date": record.acquisition_date,
        "acquisition_value": record.acquisition_value,
        "address_full": record.address_full,
        "city": record.city,
        "postal_code": record.postal_code,
        "province": record.province,
        "cadastral_ref": record.cadastral_ref,
        "registry_type": record.registry_type,
        "registry_ref": record.registry_ref,
        "finca_registral": record.finca_registral,
        "tomo": record.tomo,
        "libro": record.libro,
        "folio": record.folio,
        "currency": record.currency,
        "valuation_admin_concursal": record.valuation_admin_concursal,
        "valuation_external": record.valuation_external,
        "valuation_date": record.valuation_date,
        "liens": record.liens,
        "encumbrances_full": record.encumbrances_full,
        "mortgage_bank": record.mortgage_bank,
        "mortgage_outstanding": record.mortgage_outstanding,
        "disposal_status": record.disposal_status,
        "occupancy_status": record.occupancy_status,
        "notes": record.notes,
    }
    _parse_iso_date(record.acquisition_date, field="acquisition_date")
    _parse_iso_date(record.valuation_date, field="valuation_date")
    _audit(
        db=db,
        case_id=case_id,
        entity="ASSET",
        logical_id=record.logical_id,
        record_id=record.record_id,
        action="UPDATE",
        actor=req.created_by,
        reason=req.reason,
        before=before,
        after=after,
    )

    db.commit()
    db.refresh(record)
    return SituationRecordSummary(
        logical_id=record.logical_id,
        record_id=record.record_id,
        version=record.version,
        is_current=record.is_current,
        created_at=record.created_at.isoformat(),
        created_by=record.created_by,
        data=after,
        evidence_count=_count_evidence(db, case_id=case_id, entity="ASSET", record_id=record.record_id),
    )


# =========================================================
# Endpoints — Public debts (AEAT/TGSS)
# =========================================================


@router.get("/public-debts", response_model=SituationListResponse, summary="Listar deudas públicas (vigentes)")
def list_public_debts(
    case_id: str,
    *,
    include_history: bool = Query(False),
    authority: Optional[str] = Query(None, max_length=20),
    deferred: Optional[bool] = Query(None),
    min_amount: Optional[float] = Query(None, ge=0.0),
    max_amount: Optional[float] = Query(None, ge=0.0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SituationListResponse:
    _require_case(db, case_id)
    q = db.query(SituationPublicDebt).filter(SituationPublicDebt.case_id == case_id)
    if not include_history:
        q = q.filter(SituationPublicDebt.is_current.is_(True))
    if authority:
        q = q.filter(SituationPublicDebt.authority == authority)
    if deferred is not None:
        q = q.filter(SituationPublicDebt.deferred.is_(bool(deferred)))
    if min_amount is not None:
        q = q.filter(SituationPublicDebt.amount_total >= float(min_amount))
    if max_amount is not None:
        q = q.filter(SituationPublicDebt.amount_total <= float(max_amount))

    total = q.count()
    rows = (
        q.order_by(SituationPublicDebt.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items: list[SituationRecordSummary] = []
    for r in rows:
        items.append(
            SituationRecordSummary(
                logical_id=r.logical_id,
                record_id=r.record_id,
                version=r.version,
                is_current=r.is_current,
                created_at=r.created_at.isoformat(),
                created_by=r.created_by,
                data={
                    "authority": r.authority,
                    "taxpayer_name": r.taxpayer_name,
                    "taxpayer_tax_id": r.taxpayer_tax_id,
                    "concept": r.concept,
                    "concept_code": r.concept_code,
                    "period_start": r.period_start,
                    "period_end": r.period_end,
                    "expediente_aplazamiento": r.expediente_aplazamiento,
                    "period_key": r.period_key,
                    "aplazamiento_status": r.aplazamiento_status,
                    "resolution_date": r.resolution_date,
                    "currency": r.currency,
                    "principal": r.principal,
                    "surcharges": r.surcharges,
                    "interest": r.interest,
                    "penalties": r.penalties,
                    "amount_total": r.amount_total,
                    "debt_status": r.debt_status,
                    "enforcement_stage": r.enforcement_stage,
                    "deferred": r.deferred,
                    "notes": r.notes,
                },
                evidence_count=_count_evidence(db, case_id=case_id, entity="PUBLIC_DEBT", record_id=r.record_id),
            )
        )
    return SituationListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/public-debts/export.xlsx", summary="Exportar deudas públicas (Excel)")
def export_public_debts_excel(case_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    _require_case(db, case_id)
    rows = (
        db.query(SituationPublicDebt)
        .filter(SituationPublicDebt.case_id == case_id, SituationPublicDebt.is_current.is_(True))
        .order_by(SituationPublicDebt.created_at.desc())
        .all()
    )
    data_rows: list[dict[str, Any]] = []
    for r in rows:
        data_rows.append(
            {
                "logical_id": r.logical_id,
                "record_id": r.record_id,
                "version": r.version,
                "created_at": r.created_at.isoformat(),
                "created_by": r.created_by,
                "authority": r.authority,
                "taxpayer_name": r.taxpayer_name,
                "taxpayer_tax_id": r.taxpayer_tax_id,
                "concept": r.concept,
                "concept_code": r.concept_code,
                "period_start": r.period_start,
                "period_end": r.period_end,
                "expediente_aplazamiento": r.expediente_aplazamiento,
                "period_key": r.period_key,
                "aplazamiento_status": r.aplazamiento_status,
                "resolution_date": r.resolution_date,
                "currency": r.currency,
                "principal": r.principal,
                "surcharges": r.surcharges,
                "interest": r.interest,
                "penalties": r.penalties,
                "amount_total": r.amount_total,
                "debt_status": r.debt_status,
                "enforcement_stage": r.enforcement_stage,
                "deferred": r.deferred,
                "notes": r.notes,
                "evidence_count": _count_evidence(db, case_id=case_id, entity="PUBLIC_DEBT", record_id=r.record_id),
            }
        )
    return _export_rows_to_xlsx(
        data_rows,
        sheet_name="DeudaPublica",
        filename=f"situation_public_debts_{case_id}.xlsx",
    )


@router.post("/public-debts", response_model=SituationRecordSummary, summary="Crear deuda pública")
def create_public_debt(
    case_id: str, req: CreatePublicDebtRequest, db: Session = Depends(get_db)
) -> SituationRecordSummary:
    _require_case(db, case_id)
    _validate_evidence(db, case_id, req.evidence)

    payload_for_validation = {
        "period_start": req.period_start,
        "period_end": req.period_end,
        "principal": req.principal,
        "surcharges": req.surcharges,
        "interest": req.interest,
        "penalties": req.penalties,
        "amount_total": req.amount_total,
    }
    _validate_public_debt_consistency(payload=payload_for_validation)
    _parse_iso_date(req.resolution_date, field="resolution_date")

    logical_id = _new_logical_id()
    record = SituationPublicDebt(
        logical_id=logical_id,
        case_id=case_id,
        version=1,
        is_current=True,
        created_by=req.created_by,
        authority=req.authority,
        taxpayer_name=req.taxpayer_name,
        taxpayer_tax_id=req.taxpayer_tax_id,
        concept=req.concept,
        concept_code=req.concept_code,
        period_start=req.period_start,
        period_end=req.period_end,
        period_key=req.period_key,
        expediente_aplazamiento=req.expediente_aplazamiento,
        aplazamiento_status=req.aplazamiento_status,
        resolution_date=req.resolution_date,
        currency=req.currency,
        principal=req.principal,
        surcharges=req.surcharges,
        interest=req.interest,
        penalties=req.penalties,
        amount_total=req.amount_total,
        debt_status=req.debt_status,
        enforcement_stage=req.enforcement_stage,
        deferred=req.deferred,
        notes=req.notes,
    )
    db.add(record)
    db.flush()
    _insert_evidence(
        db=db,
        case_id=case_id,
        entity="PUBLIC_DEBT",
        record_id=record.record_id,
        created_by=req.created_by,
        evidence=req.evidence,
    )
    after = {
        "authority": record.authority,
        "taxpayer_name": record.taxpayer_name,
        "taxpayer_tax_id": record.taxpayer_tax_id,
        "concept": record.concept,
        "concept_code": record.concept_code,
        "period_start": record.period_start,
        "period_end": record.period_end,
        "period_key": record.period_key,
        "expediente_aplazamiento": record.expediente_aplazamiento,
        "aplazamiento_status": record.aplazamiento_status,
        "resolution_date": record.resolution_date,
        "currency": record.currency,
        "principal": record.principal,
        "surcharges": record.surcharges,
        "interest": record.interest,
        "penalties": record.penalties,
        "amount_total": record.amount_total,
        "debt_status": record.debt_status,
        "enforcement_stage": record.enforcement_stage,
        "deferred": record.deferred,
        "notes": record.notes,
    }
    _audit(
        db=db,
        case_id=case_id,
        entity="PUBLIC_DEBT",
        logical_id=logical_id,
        record_id=record.record_id,
        action="CREATE",
        actor=req.created_by,
        reason=req.reason,
        before=None,
        after=after,
    )
    db.commit()
    db.refresh(record)
    return SituationRecordSummary(
        logical_id=record.logical_id,
        record_id=record.record_id,
        version=record.version,
        is_current=record.is_current,
        created_at=record.created_at.isoformat(),
        created_by=record.created_by,
        data=after,
        evidence_count=_count_evidence(db, case_id=case_id, entity="PUBLIC_DEBT", record_id=record.record_id),
    )


@router.post("/public-debts/update", response_model=SituationRecordSummary, summary="Actualizar deuda pública (nueva versión)")
def update_public_debt(
    case_id: str, req: UpdatePublicDebtRequest, db: Session = Depends(get_db)
) -> SituationRecordSummary:
    _require_case(db, case_id)
    _validate_evidence(db, case_id, req.evidence)

    current = (
        db.query(SituationPublicDebt)
        .filter(
            SituationPublicDebt.case_id == case_id,
            SituationPublicDebt.logical_id == req.logical_id,
            SituationPublicDebt.is_current.is_(True),
        )
        .first()
    )
    if not current:
        raise HTTPException(status_code=404, detail="Deuda pública no encontrada (logical_id)")
    if current.version != req.expected_version:
        raise HTTPException(
            status_code=409,
            detail=f"CONCURRENT_MODIFICATION: expected_version={req.expected_version}, actual={current.version}",
        )

    before = {
        "authority": current.authority,
        "taxpayer_name": current.taxpayer_name,
        "taxpayer_tax_id": current.taxpayer_tax_id,
        "concept": current.concept,
        "concept_code": current.concept_code,
        "period_start": current.period_start,
        "period_end": current.period_end,
        "period_key": current.period_key,
        "expediente_aplazamiento": current.expediente_aplazamiento,
        "aplazamiento_status": current.aplazamiento_status,
        "resolution_date": current.resolution_date,
        "currency": current.currency,
        "principal": current.principal,
        "surcharges": current.surcharges,
        "interest": current.interest,
        "penalties": current.penalties,
        "amount_total": current.amount_total,
        "debt_status": current.debt_status,
        "enforcement_stage": current.enforcement_stage,
        "deferred": current.deferred,
        "notes": current.notes,
    }

    current.is_current = False
    db.flush()

    record = SituationPublicDebt(
        logical_id=current.logical_id,
        case_id=case_id,
        version=current.version + 1,
        is_current=True,
        supersedes_record_id=current.record_id,
        created_by=req.created_by,
        authority=req.authority if req.authority is not None else current.authority,
        taxpayer_name=req.taxpayer_name if req.taxpayer_name is not None else current.taxpayer_name,
        taxpayer_tax_id=req.taxpayer_tax_id if req.taxpayer_tax_id is not None else current.taxpayer_tax_id,
        concept=req.concept if req.concept is not None else current.concept,
        concept_code=req.concept_code if req.concept_code is not None else current.concept_code,
        period_start=req.period_start if req.period_start is not None else current.period_start,
        period_end=req.period_end if req.period_end is not None else current.period_end,
        period_key=req.period_key if req.period_key is not None else current.period_key,
        expediente_aplazamiento=req.expediente_aplazamiento
        if req.expediente_aplazamiento is not None
        else current.expediente_aplazamiento,
        aplazamiento_status=req.aplazamiento_status
        if req.aplazamiento_status is not None
        else current.aplazamiento_status,
        resolution_date=req.resolution_date if req.resolution_date is not None else current.resolution_date,
        currency=req.currency if req.currency is not None else current.currency,
        principal=req.principal if req.principal is not None else current.principal,
        surcharges=req.surcharges if req.surcharges is not None else current.surcharges,
        interest=req.interest if req.interest is not None else current.interest,
        penalties=req.penalties if req.penalties is not None else current.penalties,
        amount_total=req.amount_total if req.amount_total is not None else current.amount_total,
        debt_status=req.debt_status if req.debt_status is not None else current.debt_status,
        enforcement_stage=req.enforcement_stage if req.enforcement_stage is not None else current.enforcement_stage,
        deferred=req.deferred if req.deferred is not None else current.deferred,
        notes=req.notes if req.notes is not None else current.notes,
    )
    db.add(record)
    db.flush()
    _insert_evidence(
        db=db,
        case_id=case_id,
        entity="PUBLIC_DEBT",
        record_id=record.record_id,
        created_by=req.created_by,
        evidence=req.evidence,
    )

    after = {
        "authority": record.authority,
        "taxpayer_name": record.taxpayer_name,
        "taxpayer_tax_id": record.taxpayer_tax_id,
        "concept": record.concept,
        "concept_code": record.concept_code,
        "period_start": record.period_start,
        "period_end": record.period_end,
        "period_key": record.period_key,
        "expediente_aplazamiento": record.expediente_aplazamiento,
        "aplazamiento_status": record.aplazamiento_status,
        "resolution_date": record.resolution_date,
        "currency": record.currency,
        "principal": record.principal,
        "surcharges": record.surcharges,
        "interest": record.interest,
        "penalties": record.penalties,
        "amount_total": record.amount_total,
        "debt_status": record.debt_status,
        "enforcement_stage": record.enforcement_stage,
        "deferred": record.deferred,
        "notes": record.notes,
    }
    _validate_public_debt_consistency(payload=after)
    _parse_iso_date(record.resolution_date, field="resolution_date")
    _audit(
        db=db,
        case_id=case_id,
        entity="PUBLIC_DEBT",
        logical_id=record.logical_id,
        record_id=record.record_id,
        action="UPDATE",
        actor=req.created_by,
        reason=req.reason,
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(record)
    return SituationRecordSummary(
        logical_id=record.logical_id,
        record_id=record.record_id,
        version=record.version,
        is_current=record.is_current,
        created_at=record.created_at.isoformat(),
        created_by=record.created_by,
        data=after,
        evidence_count=_count_evidence(db, case_id=case_id, entity="PUBLIC_DEBT", record_id=record.record_id),
    )


# =========================================================
# Endpoints — Court records
# =========================================================


@router.get("/court-records", response_model=SituationListResponse, summary="Listar actuaciones/juzgado (vigentes)")
def list_court_records(
    case_id: str,
    *,
    include_history: bool = Query(False),
    action_type: Optional[str] = Query(None, max_length=80),
    procedure_number: Optional[str] = Query(None, max_length=100),
    status_txt: Optional[str] = Query(None, alias="status", max_length=80),
    min_amount: Optional[float] = Query(None, ge=0.0),
    max_amount: Optional[float] = Query(None, ge=0.0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SituationListResponse:
    _require_case(db, case_id)
    q = db.query(SituationCourtRecord).filter(SituationCourtRecord.case_id == case_id)
    if not include_history:
        q = q.filter(SituationCourtRecord.is_current.is_(True))
    if action_type:
        q = q.filter(SituationCourtRecord.action_type == action_type)
    if procedure_number:
        q = q.filter(SituationCourtRecord.procedure_number.ilike(f"%{procedure_number}%"))
    if status_txt:
        q = q.filter(SituationCourtRecord.status.ilike(f"%{status_txt}%"))
    if min_amount is not None:
        q = q.filter(
            SituationCourtRecord.amount_claimed.isnot(None),
            SituationCourtRecord.amount_claimed >= float(min_amount),
        )
    if max_amount is not None:
        q = q.filter(
            SituationCourtRecord.amount_claimed.isnot(None),
            SituationCourtRecord.amount_claimed <= float(max_amount),
        )

    total = q.count()
    rows = (
        q.order_by(SituationCourtRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items: list[SituationRecordSummary] = []
    for r in rows:
        items.append(
            SituationRecordSummary(
                logical_id=r.logical_id,
                record_id=r.record_id,
                version=r.version,
                is_current=r.is_current,
                created_at=r.created_at.isoformat(),
                created_by=r.created_by,
                data={
                    "court": r.court,
                    "court_city": r.court_city,
                    "court_section": r.court_section,
                    "procedure_number": r.procedure_number,
                    "claimant": r.claimant,
                    "autos_ref": r.autos_ref,
                    "case_year": r.case_year,
                    "case_role": r.case_role,
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
                evidence_count=_count_evidence(db, case_id=case_id, entity="COURT", record_id=r.record_id),
            )
        )
    return SituationListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/court-records/export.xlsx", summary="Exportar actuaciones/juzgado (Excel)")
def export_court_records_excel(case_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    _require_case(db, case_id)
    rows = (
        db.query(SituationCourtRecord)
        .filter(SituationCourtRecord.case_id == case_id, SituationCourtRecord.is_current.is_(True))
        .order_by(SituationCourtRecord.created_at.desc())
        .all()
    )
    data_rows: list[dict[str, Any]] = []
    for r in rows:
        data_rows.append(
            {
                "logical_id": r.logical_id,
                "record_id": r.record_id,
                "version": r.version,
                "created_at": r.created_at.isoformat(),
                "created_by": r.created_by,
                "court": r.court,
                "court_city": r.court_city,
                "court_section": r.court_section,
                "procedure_number": r.procedure_number,
                "claimant": r.claimant,
                "autos_ref": r.autos_ref,
                "case_year": r.case_year,
                "case_role": r.case_role,
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
                "evidence_count": _count_evidence(db, case_id=case_id, entity="COURT", record_id=r.record_id),
            }
        )
    return _export_rows_to_xlsx(
        data_rows,
        sheet_name="Juzgado",
        filename=f"situation_court_records_{case_id}.xlsx",
    )

@router.post("/court-records", response_model=SituationRecordSummary, summary="Crear actuación/juzgado")
def create_court_record(
    case_id: str, req: CreateCourtRecordRequest, db: Session = Depends(get_db)
) -> SituationRecordSummary:
    _require_case(db, case_id)
    _validate_evidence(db, case_id, req.evidence)

    _parse_iso_date(req.action_date, field="action_date")
    _parse_iso_date(req.next_hearing_date, field="next_hearing_date")

    logical_id = _new_logical_id()
    record = SituationCourtRecord(
        logical_id=logical_id,
        case_id=case_id,
        version=1,
        is_current=True,
        created_by=req.created_by,
        court=req.court,
        court_city=req.court_city,
        court_section=req.court_section,
        procedure_number=req.procedure_number,
        autos_ref=req.autos_ref,
        case_year=req.case_year,
        case_role=req.case_role,
        claimant=req.claimant,
        party_counterparty_name=req.party_counterparty_name,
        party_counterparty_tax_id=req.party_counterparty_tax_id,
        party_counterparty_address=req.party_counterparty_address,
        lawyer_name=req.lawyer_name,
        procurator_name=req.procurator_name,
        action_type=req.action_type,
        action_date=req.action_date,
        next_hearing_date=req.next_hearing_date,
        currency=req.currency,
        amount_claimed=req.amount_claimed,
        amount_awarded=req.amount_awarded,
        amount_paid=req.amount_paid,
        status=req.status,
        stage=req.stage,
        milestones_json=req.milestones_json,
        enforcement_flag=req.enforcement_flag,
        seizures_notes=req.seizures_notes,
        notes=req.notes,
    )
    db.add(record)
    db.flush()
    _insert_evidence(
        db=db,
        case_id=case_id,
        entity="COURT",
        record_id=record.record_id,
        created_by=req.created_by,
        evidence=req.evidence,
    )
    after = {
        "court": record.court,
        "court_city": record.court_city,
        "court_section": record.court_section,
        "procedure_number": record.procedure_number,
        "autos_ref": record.autos_ref,
        "case_year": record.case_year,
        "case_role": record.case_role,
        "claimant": record.claimant,
        "party_counterparty_name": record.party_counterparty_name,
        "party_counterparty_tax_id": record.party_counterparty_tax_id,
        "party_counterparty_address": record.party_counterparty_address,
        "lawyer_name": record.lawyer_name,
        "procurator_name": record.procurator_name,
        "action_type": record.action_type,
        "action_date": record.action_date,
        "next_hearing_date": record.next_hearing_date,
        "currency": record.currency,
        "amount_claimed": record.amount_claimed,
        "amount_awarded": record.amount_awarded,
        "amount_paid": record.amount_paid,
        "status": record.status,
        "stage": record.stage,
        "milestones_json": record.milestones_json,
        "enforcement_flag": record.enforcement_flag,
        "seizures_notes": record.seizures_notes,
        "notes": record.notes,
    }
    _audit(
        db=db,
        case_id=case_id,
        entity="COURT",
        logical_id=logical_id,
        record_id=record.record_id,
        action="CREATE",
        actor=req.created_by,
        reason=req.reason,
        before=None,
        after=after,
    )
    db.commit()
    db.refresh(record)
    return SituationRecordSummary(
        logical_id=record.logical_id,
        record_id=record.record_id,
        version=record.version,
        is_current=record.is_current,
        created_at=record.created_at.isoformat(),
        created_by=record.created_by,
        data=after,
        evidence_count=_count_evidence(db, case_id=case_id, entity="COURT", record_id=record.record_id),
    )


@router.post("/court-records/update", response_model=SituationRecordSummary, summary="Actualizar actuación/juzgado (nueva versión)")
def update_court_record(
    case_id: str, req: UpdateCourtRecordRequest, db: Session = Depends(get_db)
) -> SituationRecordSummary:
    _require_case(db, case_id)
    _validate_evidence(db, case_id, req.evidence)

    current = (
        db.query(SituationCourtRecord)
        .filter(
            SituationCourtRecord.case_id == case_id,
            SituationCourtRecord.logical_id == req.logical_id,
            SituationCourtRecord.is_current.is_(True),
        )
        .first()
    )
    if not current:
        raise HTTPException(status_code=404, detail="Actuación no encontrada (logical_id)")
    if current.version != req.expected_version:
        raise HTTPException(
            status_code=409,
            detail=f"CONCURRENT_MODIFICATION: expected_version={req.expected_version}, actual={current.version}",
        )

    before = {
        "court": current.court,
        "court_city": current.court_city,
        "court_section": current.court_section,
        "procedure_number": current.procedure_number,
        "autos_ref": current.autos_ref,
        "case_year": current.case_year,
        "case_role": current.case_role,
        "claimant": current.claimant,
        "party_counterparty_name": current.party_counterparty_name,
        "party_counterparty_tax_id": current.party_counterparty_tax_id,
        "party_counterparty_address": current.party_counterparty_address,
        "lawyer_name": current.lawyer_name,
        "procurator_name": current.procurator_name,
        "action_type": current.action_type,
        "action_date": current.action_date,
        "next_hearing_date": current.next_hearing_date,
        "currency": current.currency,
        "amount_claimed": current.amount_claimed,
        "amount_awarded": current.amount_awarded,
        "amount_paid": current.amount_paid,
        "status": current.status,
        "stage": current.stage,
        "milestones_json": current.milestones_json,
        "enforcement_flag": current.enforcement_flag,
        "seizures_notes": current.seizures_notes,
        "notes": current.notes,
    }

    current.is_current = False
    db.flush()

    record = SituationCourtRecord(
        logical_id=current.logical_id,
        case_id=case_id,
        version=current.version + 1,
        is_current=True,
        supersedes_record_id=current.record_id,
        created_by=req.created_by,
        court=req.court if req.court is not None else current.court,
        court_city=req.court_city if req.court_city is not None else current.court_city,
        court_section=req.court_section if req.court_section is not None else current.court_section,
        procedure_number=req.procedure_number
        if req.procedure_number is not None
        else current.procedure_number,
        autos_ref=req.autos_ref if req.autos_ref is not None else current.autos_ref,
        case_year=req.case_year if req.case_year is not None else current.case_year,
        case_role=req.case_role if req.case_role is not None else current.case_role,
        claimant=req.claimant if req.claimant is not None else current.claimant,
        party_counterparty_name=req.party_counterparty_name
        if req.party_counterparty_name is not None
        else current.party_counterparty_name,
        party_counterparty_tax_id=req.party_counterparty_tax_id
        if req.party_counterparty_tax_id is not None
        else current.party_counterparty_tax_id,
        party_counterparty_address=req.party_counterparty_address
        if req.party_counterparty_address is not None
        else current.party_counterparty_address,
        lawyer_name=req.lawyer_name if req.lawyer_name is not None else current.lawyer_name,
        procurator_name=req.procurator_name if req.procurator_name is not None else current.procurator_name,
        action_type=req.action_type if req.action_type is not None else current.action_type,
        action_date=req.action_date if req.action_date is not None else current.action_date,
        next_hearing_date=req.next_hearing_date
        if req.next_hearing_date is not None
        else current.next_hearing_date,
        currency=req.currency if req.currency is not None else current.currency,
        amount_claimed=req.amount_claimed
        if req.amount_claimed is not None
        else current.amount_claimed,
        amount_awarded=req.amount_awarded if req.amount_awarded is not None else current.amount_awarded,
        amount_paid=req.amount_paid if req.amount_paid is not None else current.amount_paid,
        status=req.status if req.status is not None else current.status,
        stage=req.stage if req.stage is not None else current.stage,
        milestones_json=req.milestones_json if req.milestones_json is not None else current.milestones_json,
        enforcement_flag=req.enforcement_flag
        if req.enforcement_flag is not None
        else current.enforcement_flag,
        seizures_notes=req.seizures_notes if req.seizures_notes is not None else current.seizures_notes,
        notes=req.notes if req.notes is not None else current.notes,
    )
    db.add(record)
    db.flush()
    _insert_evidence(
        db=db,
        case_id=case_id,
        entity="COURT",
        record_id=record.record_id,
        created_by=req.created_by,
        evidence=req.evidence,
    )

    after = {
        "court": record.court,
        "court_city": record.court_city,
        "court_section": record.court_section,
        "procedure_number": record.procedure_number,
        "autos_ref": record.autos_ref,
        "case_year": record.case_year,
        "case_role": record.case_role,
        "claimant": record.claimant,
        "party_counterparty_name": record.party_counterparty_name,
        "party_counterparty_tax_id": record.party_counterparty_tax_id,
        "party_counterparty_address": record.party_counterparty_address,
        "lawyer_name": record.lawyer_name,
        "procurator_name": record.procurator_name,
        "action_type": record.action_type,
        "action_date": record.action_date,
        "next_hearing_date": record.next_hearing_date,
        "currency": record.currency,
        "amount_claimed": record.amount_claimed,
        "amount_awarded": record.amount_awarded,
        "amount_paid": record.amount_paid,
        "status": record.status,
        "stage": record.stage,
        "milestones_json": record.milestones_json,
        "enforcement_flag": record.enforcement_flag,
        "seizures_notes": record.seizures_notes,
        "notes": record.notes,
    }
    _parse_iso_date(record.action_date, field="action_date")
    _parse_iso_date(record.next_hearing_date, field="next_hearing_date")
    _audit(
        db=db,
        case_id=case_id,
        entity="COURT",
        logical_id=record.logical_id,
        record_id=record.record_id,
        action="UPDATE",
        actor=req.created_by,
        reason=req.reason,
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(record)
    return SituationRecordSummary(
        logical_id=record.logical_id,
        record_id=record.record_id,
        version=record.version,
        is_current=record.is_current,
        created_at=record.created_at.isoformat(),
        created_by=record.created_by,
        data=after,
        evidence_count=_count_evidence(db, case_id=case_id, entity="COURT", record_id=record.record_id),
    )

