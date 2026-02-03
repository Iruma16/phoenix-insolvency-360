from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# =========================================================
# CUADRO DE SITUACIÓN (SQL) — Versionado “vigente” + append-only
# =========================================================


class SituationEvidence(Base):
    """
    Evidencia obligatoria para altas/ediciones del Cuadro de situación.
    Append-only: no se edita, no se borra (salvo mantenimiento DBA).
    """

    __tablename__ = "situation_evidence"

    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Polimórfico: a qué entidad/version pertenece esta evidencia
    entity: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    record_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.document_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    note: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SituationAuditLog(Base):
    """
    Auditoría append-only: quién cambió qué, cuándo y por qué.
    """

    __tablename__ = "situation_audit_log"

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    entity: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    logical_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    record_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    action: Mapped[str] = mapped_column(String(20), nullable=False)  # CREATE/UPDATE
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)

    before: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SituationInvoice(Base):
    __tablename__ = "situation_invoices"

    # Versioning “vigente”
    record_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    logical_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    supersedes_record_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Datos “abogado-friendly”
    supplier: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_tax_id: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    supplier_address: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    supplier_email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    buyer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    buyer_tax_id: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    buyer_address: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    buyer_email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    invoice_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contract_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    issue_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    due_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    paid_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD

    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    currency_fx_rate: Mapped[Optional[float]] = mapped_column(nullable=True)

    base_amount: Mapped[Optional[float]] = mapped_column(nullable=True)
    vat_amount: Mapped[Optional[float]] = mapped_column(nullable=True)
    withholding_amount: Mapped[Optional[float]] = mapped_column(nullable=True)
    amount_total: Mapped[float] = mapped_column(nullable=False, default=0.0)

    status: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )  # pendiente/pagada/impagada
    payment_terms: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    iban_masked: Mapped[Optional[str]] = mapped_column(String(34), nullable=True)

    invoice_type: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )  # ordinaria/rectificativa/...
    source_ref: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )  # pedido/albarán/...

    is_disputed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    dispute_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SituationCredit(Base):
    __tablename__ = "situation_credits"

    record_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    logical_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    supersedes_record_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    creditor: Mapped[str] = mapped_column(String(255), nullable=False)  # lender_name
    creditor_tax_id: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )  # lender_tax_id
    lender_address: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    lender_email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    lender_phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    contract_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    amount_total: Mapped[float] = mapped_column(nullable=False, default=0.0)

    principal_initial: Mapped[Optional[float]] = mapped_column(nullable=True)
    outstanding_principal: Mapped[Optional[float]] = mapped_column(nullable=True)
    accrued_interest: Mapped[Optional[float]] = mapped_column(nullable=True)
    interest_rate: Mapped[Optional[float]] = mapped_column(
        nullable=True
    )  # porcentaje anual (0..100)
    interest_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # fijo/variable
    spread: Mapped[Optional[float]] = mapped_column(nullable=True)

    secured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    guarantee_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    secured_type: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )  # hipoteca/prenda/aval/...
    collateral_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    collateral_registry_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    guarantor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    guarantor_tax_id: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    maturity_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    default_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    last_payment_date: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )  # YYYY-MM-DD

    enforcement_stage: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )  # amistosa/ejecutiva/...
    procedure_ref: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )  # si judicializado
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SituationAsset(Base):
    __tablename__ = "situation_assets"

    record_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    logical_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    supersedes_record_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    asset_type: Mapped[str] = mapped_column(
        String(40), nullable=False
    )  # INMUEBLE/VEHICULO/MAQUINARIA
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ownership_share: Mapped[Optional[float]] = mapped_column(nullable=True)  # 0..1
    acquisition_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    acquisition_value: Mapped[Optional[float]] = mapped_column(nullable=True)

    address_full: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    province: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    cadastral_ref: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    registry_type: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )  # prop/mercantil/...
    registry_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    finca_registral: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    tomo: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    libro: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    folio: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    valuation_admin_concursal: Mapped[Optional[float]] = mapped_column(nullable=True)
    valuation_external: Mapped[Optional[float]] = mapped_column(nullable=True)
    valuation_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    liens: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    encumbrances_full: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mortgage_bank: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mortgage_outstanding: Mapped[Optional[float]] = mapped_column(nullable=True)

    disposal_status: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )  # vendible/ocupado/litigioso
    occupancy_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SituationPublicDebt(Base):
    __tablename__ = "situation_public_debts"

    record_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    logical_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    supersedes_record_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    authority: Mapped[str] = mapped_column(String(20), nullable=False)  # AEAT/TGSS/OTRO
    taxpayer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    taxpayer_tax_id: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    concept: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    concept_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    period_start: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    period_end: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    period_key: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # p.ej. 2025Q4

    expediente_aplazamiento: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    aplazamiento_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    resolution_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD

    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    principal: Mapped[Optional[float]] = mapped_column(nullable=True)
    surcharges: Mapped[Optional[float]] = mapped_column(nullable=True)
    interest: Mapped[Optional[float]] = mapped_column(nullable=True)
    penalties: Mapped[Optional[float]] = mapped_column(nullable=True)
    amount_total: Mapped[float] = mapped_column(nullable=False, default=0.0)

    debt_status: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )  # voluntaria/ejecutiva/aplazada
    enforcement_stage: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    deferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SituationCourtRecord(Base):
    __tablename__ = "situation_court_records"

    record_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    logical_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    supersedes_record_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    court: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    court_city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    court_section: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    procedure_number: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # procedure_ref
    autos_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    case_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    case_role: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )  # demandante/demandado

    claimant: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    party_counterparty_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    party_counterparty_tax_id: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    party_counterparty_address: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    lawyer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    procurator_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    action_type: Mapped[str] = mapped_column(
        String(80), nullable=False
    )  # demanda/monitorio/ejecucion/...
    action_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    next_hearing_date: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )  # YYYY-MM-DD

    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="EUR")
    amount_claimed: Mapped[Optional[float]] = mapped_column(nullable=True)
    amount_awarded: Mapped[Optional[float]] = mapped_column(nullable=True)
    amount_paid: Mapped[Optional[float]] = mapped_column(nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    stage: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    milestones_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    enforcement_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    seizures_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
