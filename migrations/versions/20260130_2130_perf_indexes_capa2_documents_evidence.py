"""perf_indexes_capa2_documents_evidence

Revision ID: 20260130_2130_perf_indexes
Revises: 20260130_2030_submission_snapshot_id
Create Date: 2026-01-30 21:30:00

CAPA 6 — Performance:
- Índices compuestos (case_id + is_current + filtros frecuentes) para situation_*
- Índices operativos para documents (case_id + deleted_at + created_at, doc_type, etc.)
- Índice lookup para case_record_evidence (case_id + record_type + record_id)
"""

from alembic import op
import sqlalchemy as sa


revision = "20260130_2130_perf_indexes"
down_revision = "20260130_2030_submission_snapshot_id"
branch_labels = None
depends_on = None


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _create_index_if_possible(name: str, table: str, cols: list[str]) -> None:
    if _is_sqlite():
        cols_sql = ", ".join(cols)
        op.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols_sql})"))
    else:
        op.create_index(name, table, cols)


def _drop_index_if_exists(name: str, table: str) -> None:
    if _is_sqlite():
        op.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))
    else:
        op.drop_index(name, table_name=table)


def upgrade() -> None:
    # =========================================================
    # CAPA 2 — situation_* (case_id + is_current + filtros)
    # =========================================================
    _create_index_if_possible("ix_sit_inv_case_cur_supplier", "situation_invoices", ["case_id", "is_current", "supplier"])
    _create_index_if_possible(
        "ix_sit_inv_case_cur_supplier_tax",
        "situation_invoices",
        ["case_id", "is_current", "supplier_tax_id"],
    )
    _create_index_if_possible(
        "ix_sit_inv_case_cur_buyer_tax",
        "situation_invoices",
        ["case_id", "is_current", "buyer_tax_id"],
    )
    _create_index_if_possible("ix_sit_inv_case_cur_issue", "situation_invoices", ["case_id", "is_current", "issue_date"])
    _create_index_if_possible("ix_sit_inv_case_cur_due", "situation_invoices", ["case_id", "is_current", "due_date"])
    _create_index_if_possible(
        "ix_sit_inv_case_cur_amount",
        "situation_invoices",
        ["case_id", "is_current", "amount_total"],
    )
    _create_index_if_possible("ix_sit_inv_case_cur_status", "situation_invoices", ["case_id", "is_current", "status"])

    _create_index_if_possible("ix_sit_cred_case_cur_creditor", "situation_credits", ["case_id", "is_current", "creditor"])
    _create_index_if_possible(
        "ix_sit_cred_case_cur_creditor_tax",
        "situation_credits",
        ["case_id", "is_current", "creditor_tax_id"],
    )
    _create_index_if_possible(
        "ix_sit_cred_case_cur_contract",
        "situation_credits",
        ["case_id", "is_current", "contract_ref"],
    )
    _create_index_if_possible(
        "ix_sit_cred_case_cur_maturity",
        "situation_credits",
        ["case_id", "is_current", "maturity_date"],
    )
    _create_index_if_possible(
        "ix_sit_cred_case_cur_default",
        "situation_credits",
        ["case_id", "is_current", "default_date"],
    )
    _create_index_if_possible(
        "ix_sit_cred_case_cur_amount",
        "situation_credits",
        ["case_id", "is_current", "amount_total"],
    )

    _create_index_if_possible("ix_sit_asset_case_cur_type", "situation_assets", ["case_id", "is_current", "asset_type"])
    _create_index_if_possible("ix_sit_asset_case_cur_city", "situation_assets", ["case_id", "is_current", "city"])
    _create_index_if_possible("ix_sit_asset_case_cur_province", "situation_assets", ["case_id", "is_current", "province"])
    _create_index_if_possible(
        "ix_sit_asset_case_cur_cadastral",
        "situation_assets",
        ["case_id", "is_current", "cadastral_ref"],
    )
    _create_index_if_possible(
        "ix_sit_asset_case_cur_registry",
        "situation_assets",
        ["case_id", "is_current", "registry_ref"],
    )
    _create_index_if_possible(
        "ix_sit_asset_case_cur_val_ac",
        "situation_assets",
        ["case_id", "is_current", "valuation_admin_concursal"],
    )
    _create_index_if_possible(
        "ix_sit_asset_case_cur_val_ext",
        "situation_assets",
        ["case_id", "is_current", "valuation_external"],
    )

    _create_index_if_possible(
        "ix_sit_pub_case_cur_auth",
        "situation_public_debts",
        ["case_id", "is_current", "authority"],
    )
    _create_index_if_possible(
        "ix_sit_pub_case_cur_taxpayer",
        "situation_public_debts",
        ["case_id", "is_current", "taxpayer_tax_id"],
    )
    _create_index_if_possible(
        "ix_sit_pub_case_cur_pstart",
        "situation_public_debts",
        ["case_id", "is_current", "period_start"],
    )
    _create_index_if_possible(
        "ix_sit_pub_case_cur_pend",
        "situation_public_debts",
        ["case_id", "is_current", "period_end"],
    )
    _create_index_if_possible(
        "ix_sit_pub_case_cur_amount",
        "situation_public_debts",
        ["case_id", "is_current", "amount_total"],
    )
    _create_index_if_possible(
        "ix_sit_pub_case_cur_status",
        "situation_public_debts",
        ["case_id", "is_current", "debt_status"],
    )

    _create_index_if_possible(
        "ix_sit_court_case_cur_proc",
        "situation_court_records",
        ["case_id", "is_current", "procedure_number"],
    )
    _create_index_if_possible(
        "ix_sit_court_case_cur_autos",
        "situation_court_records",
        ["case_id", "is_current", "autos_ref"],
    )
    _create_index_if_possible(
        "ix_sit_court_case_cur_action_date",
        "situation_court_records",
        ["case_id", "is_current", "action_date"],
    )
    _create_index_if_possible(
        "ix_sit_court_case_cur_status",
        "situation_court_records",
        ["case_id", "is_current", "status"],
    )
    _create_index_if_possible(
        "ix_sit_court_case_cur_stage",
        "situation_court_records",
        ["case_id", "is_current", "stage"],
    )

    # =========================================================
    # Documents — índices operativos (case_id + filtros)
    # =========================================================
    _create_index_if_possible(
        "ix_docs_case_deleted_created",
        "documents",
        ["case_id", "deleted_at", "created_at"],
    )
    _create_index_if_possible("ix_docs_case_doctype", "documents", ["case_id", "doc_type"])
    _create_index_if_possible("ix_docs_case_file_format", "documents", ["case_id", "file_format"])
    _create_index_if_possible("ix_docs_case_uploaded", "documents", ["case_id", "uploaded_at"])

    # =========================================================
    # Evidence — lookup clave (case_id + record_type + record_id)
    # =========================================================
    _create_index_if_possible(
        "ix_evid_case_record_lookup",
        "case_record_evidence",
        ["case_id", "record_type", "record_id"],
    )


def downgrade() -> None:
    for name, table in [
        ("ix_evid_case_record_lookup", "case_record_evidence"),
        ("ix_docs_case_uploaded", "documents"),
        ("ix_docs_case_file_format", "documents"),
        ("ix_docs_case_doctype", "documents"),
        ("ix_docs_case_deleted_created", "documents"),
        ("ix_sit_court_case_cur_stage", "situation_court_records"),
        ("ix_sit_court_case_cur_status", "situation_court_records"),
        ("ix_sit_court_case_cur_action_date", "situation_court_records"),
        ("ix_sit_court_case_cur_autos", "situation_court_records"),
        ("ix_sit_court_case_cur_proc", "situation_court_records"),
        ("ix_sit_pub_case_cur_status", "situation_public_debts"),
        ("ix_sit_pub_case_cur_amount", "situation_public_debts"),
        ("ix_sit_pub_case_cur_pend", "situation_public_debts"),
        ("ix_sit_pub_case_cur_pstart", "situation_public_debts"),
        ("ix_sit_pub_case_cur_taxpayer", "situation_public_debts"),
        ("ix_sit_pub_case_cur_auth", "situation_public_debts"),
        ("ix_sit_asset_case_cur_val_ext", "situation_assets"),
        ("ix_sit_asset_case_cur_val_ac", "situation_assets"),
        ("ix_sit_asset_case_cur_registry", "situation_assets"),
        ("ix_sit_asset_case_cur_cadastral", "situation_assets"),
        ("ix_sit_asset_case_cur_province", "situation_assets"),
        ("ix_sit_asset_case_cur_city", "situation_assets"),
        ("ix_sit_asset_case_cur_type", "situation_assets"),
        ("ix_sit_cred_case_cur_amount", "situation_credits"),
        ("ix_sit_cred_case_cur_default", "situation_credits"),
        ("ix_sit_cred_case_cur_maturity", "situation_credits"),
        ("ix_sit_cred_case_cur_contract", "situation_credits"),
        ("ix_sit_cred_case_cur_creditor_tax", "situation_credits"),
        ("ix_sit_cred_case_cur_creditor", "situation_credits"),
        ("ix_sit_inv_case_cur_status", "situation_invoices"),
        ("ix_sit_inv_case_cur_amount", "situation_invoices"),
        ("ix_sit_inv_case_cur_due", "situation_invoices"),
        ("ix_sit_inv_case_cur_issue", "situation_invoices"),
        ("ix_sit_inv_case_cur_buyer_tax", "situation_invoices"),
        ("ix_sit_inv_case_cur_supplier_tax", "situation_invoices"),
        ("ix_sit_inv_case_cur_supplier", "situation_invoices"),
    ]:
        _drop_index_if_exists(name, table)

