"""extend_situation_capa2_abogado_friendly_fields

Revision ID: 20260130_1930_situation_capa2_fields
Revises: 20260130_1810_situation_link_fields
Create Date: 2026-01-30 19:30:00

CAPA 2 — Cuadro de situación: ampliar modelo abogado-friendly.

Todos los campos nuevos son NULLABLE para no romper datos existentes y permitir
iteración incremental.
"""

from alembic import op
import sqlalchemy as sa


def _existing_cols(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        cols = insp.get_columns(table)
    except Exception:
        return set()
    return {c.get("name") for c in cols if c.get("name")}


def _add_if_missing(batch, *, table: str, col: sa.Column) -> None:
    if col.name in _existing_cols(table):
        return
    batch.add_column(col)


revision = "20260130_1930_situation_capa2_fields"
down_revision = "20260130_1810_situation_link_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("situation_invoices") as b:
        _add_if_missing(b, table="situation_invoices", col=sa.Column("supplier_address", sa.String(length=300), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("supplier_email", sa.String(length=120), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("buyer_name", sa.String(length=255), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("buyer_tax_id", sa.String(length=30), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("buyer_address", sa.String(length=300), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("buyer_email", sa.String(length=120), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("paid_date", sa.String(length=10), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("currency_fx_rate", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("base_amount", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("vat_amount", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("withholding_amount", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("payment_terms", sa.String(length=120), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("payment_method", sa.String(length=60), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("iban_masked", sa.String(length=34), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("invoice_type", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("source_ref", sa.String(length=200), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("is_disputed", sa.Boolean(), nullable=True))
        _add_if_missing(b, table="situation_invoices", col=sa.Column("dispute_reason", sa.Text(), nullable=True))

    with op.batch_alter_table("situation_credits") as b:
        _add_if_missing(b, table="situation_credits", col=sa.Column("lender_address", sa.String(length=300), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("lender_email", sa.String(length=120), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("lender_phone", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("principal_initial", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("accrued_interest", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("interest_rate", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("interest_type", sa.String(length=20), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("spread", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("secured_type", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("collateral_description", sa.Text(), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("collateral_registry_ref", sa.String(length=200), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("guarantor_name", sa.String(length=255), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("guarantor_tax_id", sa.String(length=30), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("default_date", sa.String(length=10), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("last_payment_date", sa.String(length=10), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("enforcement_stage", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_credits", col=sa.Column("procedure_ref", sa.String(length=120), nullable=True))

    with op.batch_alter_table("situation_assets") as b:
        _add_if_missing(b, table="situation_assets", col=sa.Column("owner", sa.String(length=255), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("ownership_share", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("acquisition_date", sa.String(length=10), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("acquisition_value", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("address_full", sa.String(length=300), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("city", sa.String(length=120), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("postal_code", sa.String(length=20), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("province", sa.String(length=120), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("cadastral_ref", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("registry_type", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("registry_ref", sa.String(length=200), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("finca_registral", sa.String(length=80), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("tomo", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("libro", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("folio", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("encumbrances_full", sa.Text(), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("mortgage_bank", sa.String(length=255), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("mortgage_outstanding", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("disposal_status", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_assets", col=sa.Column("occupancy_status", sa.String(length=40), nullable=True))

    with op.batch_alter_table("situation_public_debts") as b:
        _add_if_missing(b, table="situation_public_debts", col=sa.Column("taxpayer_name", sa.String(length=255), nullable=True))
        _add_if_missing(b, table="situation_public_debts", col=sa.Column("taxpayer_tax_id", sa.String(length=30), nullable=True))
        _add_if_missing(b, table="situation_public_debts", col=sa.Column("concept_code", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_public_debts", col=sa.Column("period_key", sa.String(length=20), nullable=True))
        _add_if_missing(b, table="situation_public_debts", col=sa.Column("aplazamiento_status", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_public_debts", col=sa.Column("resolution_date", sa.String(length=10), nullable=True))
        _add_if_missing(b, table="situation_public_debts", col=sa.Column("principal", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_public_debts", col=sa.Column("surcharges", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_public_debts", col=sa.Column("interest", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_public_debts", col=sa.Column("penalties", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_public_debts", col=sa.Column("debt_status", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_public_debts", col=sa.Column("enforcement_stage", sa.String(length=40), nullable=True))

    with op.batch_alter_table("situation_court_records") as b:
        _add_if_missing(b, table="situation_court_records", col=sa.Column("court_city", sa.String(length=120), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("court_section", sa.String(length=120), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("autos_ref", sa.String(length=120), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("case_year", sa.Integer(), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("case_role", sa.String(length=40), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("party_counterparty_name", sa.String(length=255), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("party_counterparty_tax_id", sa.String(length=30), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("party_counterparty_address", sa.String(length=300), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("lawyer_name", sa.String(length=255), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("procurator_name", sa.String(length=255), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("next_hearing_date", sa.String(length=10), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("amount_awarded", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("amount_paid", sa.Float(), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("milestones_json", sa.JSON(), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("enforcement_flag", sa.Boolean(), nullable=True))
        _add_if_missing(b, table="situation_court_records", col=sa.Column("seizures_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("situation_court_records") as b:
        b.drop_column("seizures_notes")
        b.drop_column("enforcement_flag")
        b.drop_column("milestones_json")
        b.drop_column("amount_paid")
        b.drop_column("amount_awarded")
        b.drop_column("next_hearing_date")
        b.drop_column("procurator_name")
        b.drop_column("lawyer_name")
        b.drop_column("party_counterparty_address")
        b.drop_column("party_counterparty_tax_id")
        b.drop_column("party_counterparty_name")
        b.drop_column("case_role")
        b.drop_column("case_year")
        b.drop_column("autos_ref")
        b.drop_column("court_section")
        b.drop_column("court_city")

    with op.batch_alter_table("situation_public_debts") as b:
        b.drop_column("enforcement_stage")
        b.drop_column("debt_status")
        b.drop_column("penalties")
        b.drop_column("interest")
        b.drop_column("surcharges")
        b.drop_column("principal")
        b.drop_column("resolution_date")
        b.drop_column("aplazamiento_status")
        b.drop_column("period_key")
        b.drop_column("concept_code")
        b.drop_column("taxpayer_tax_id")
        b.drop_column("taxpayer_name")

    with op.batch_alter_table("situation_assets") as b:
        b.drop_column("occupancy_status")
        b.drop_column("disposal_status")
        b.drop_column("mortgage_outstanding")
        b.drop_column("mortgage_bank")
        b.drop_column("encumbrances_full")
        b.drop_column("folio")
        b.drop_column("libro")
        b.drop_column("tomo")
        b.drop_column("finca_registral")
        b.drop_column("registry_ref")
        b.drop_column("registry_type")
        b.drop_column("cadastral_ref")
        b.drop_column("province")
        b.drop_column("postal_code")
        b.drop_column("city")
        b.drop_column("address_full")
        b.drop_column("acquisition_value")
        b.drop_column("acquisition_date")
        b.drop_column("ownership_share")
        b.drop_column("owner")

    with op.batch_alter_table("situation_credits") as b:
        b.drop_column("procedure_ref")
        b.drop_column("enforcement_stage")
        b.drop_column("last_payment_date")
        b.drop_column("default_date")
        b.drop_column("guarantor_tax_id")
        b.drop_column("guarantor_name")
        b.drop_column("collateral_registry_ref")
        b.drop_column("collateral_description")
        b.drop_column("secured_type")
        b.drop_column("spread")
        b.drop_column("interest_type")
        b.drop_column("interest_rate")
        b.drop_column("accrued_interest")
        b.drop_column("principal_initial")
        b.drop_column("lender_phone")
        b.drop_column("lender_email")
        b.drop_column("lender_address")

    with op.batch_alter_table("situation_invoices") as b:
        b.drop_column("dispute_reason")
        b.drop_column("is_disputed")
        b.drop_column("source_ref")
        b.drop_column("invoice_type")
        b.drop_column("iban_masked")
        b.drop_column("payment_method")
        b.drop_column("payment_terms")
        b.drop_column("withholding_amount")
        b.drop_column("vat_amount")
        b.drop_column("base_amount")
        b.drop_column("currency_fx_rate")
        b.drop_column("paid_date")
        b.drop_column("buyer_email")
        b.drop_column("buyer_address")
        b.drop_column("buyer_tax_id")
        b.drop_column("buyer_name")
        b.drop_column("supplier_email")
        b.drop_column("supplier_address")

