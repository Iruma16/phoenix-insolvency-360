"""situation_indexes_constraints

Revision ID: 20260130_1315_situation_ix_ck
Revises: 20260130_1245_doc_type_backfill
Create Date: 2026-01-30 13:15:00

Añade índices “abogado” y constraints simples para Cuadro de situación:
- índices compuestos por case_id + campos frecuentes de filtro
- checks de no-negatividad para importes/valoraciones (cuando el dialecto lo permite)

Notas:
- En SQLite, algunos cambios (checks) requieren recreación de tabla. Se hace con batch_alter_table.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260130_1315_situation_ix_ck"
down_revision = "20260130_1245_doc_type_backfill"
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


def upgrade() -> None:
    # =========================================================
    # Índices
    # =========================================================

    # Facturas
    _create_index_if_possible("ix_sit_inv_case_supplier", "situation_invoices", ["case_id", "supplier"])
    _create_index_if_possible("ix_sit_inv_case_due_date", "situation_invoices", ["case_id", "due_date"])
    _create_index_if_possible("ix_sit_inv_case_amount", "situation_invoices", ["case_id", "amount_total"])
    _create_index_if_possible("ix_sit_inv_case_status", "situation_invoices", ["case_id", "status"])

    # Créditos
    _create_index_if_possible("ix_sit_cred_case_creditor", "situation_credits", ["case_id", "creditor"])
    _create_index_if_possible("ix_sit_cred_case_amount", "situation_credits", ["case_id", "amount_total"])
    _create_index_if_possible("ix_sit_cred_case_maturity", "situation_credits", ["case_id", "maturity_date"])

    # Bienes
    _create_index_if_possible("ix_sit_asset_case_type", "situation_assets", ["case_id", "asset_type"])
    _create_index_if_possible(
        "ix_sit_asset_case_val_ac", "situation_assets", ["case_id", "valuation_admin_concursal"]
    )
    _create_index_if_possible(
        "ix_sit_asset_case_val_ext", "situation_assets", ["case_id", "valuation_external"]
    )

    # Deuda pública
    _create_index_if_possible("ix_sit_pub_case_auth", "situation_public_debts", ["case_id", "authority"])
    _create_index_if_possible("ix_sit_pub_case_amount", "situation_public_debts", ["case_id", "amount_total"])
    _create_index_if_possible("ix_sit_pub_case_deferred", "situation_public_debts", ["case_id", "deferred"])

    # Juzgado
    _create_index_if_possible("ix_sit_court_case_proc", "situation_court_records", ["case_id", "procedure_number"])
    _create_index_if_possible("ix_sit_court_case_type", "situation_court_records", ["case_id", "action_type"])
    _create_index_if_possible("ix_sit_court_case_amount", "situation_court_records", ["case_id", "amount_claimed"])

    # =========================================================
    # Constraints: no-negatividad
    # =========================================================
    # SQLite: usar batch_alter_table para añadir CHECKs (recrea tabla).
    with op.batch_alter_table("situation_invoices") as batch:
        batch.create_check_constraint("ck_sit_inv_amount_nonneg", "amount_total >= 0")
    with op.batch_alter_table("situation_credits") as batch:
        batch.create_check_constraint("ck_sit_cred_amount_nonneg", "amount_total >= 0")
    with op.batch_alter_table("situation_public_debts") as batch:
        batch.create_check_constraint("ck_sit_pub_amount_nonneg", "amount_total >= 0")
    with op.batch_alter_table("situation_assets") as batch:
        batch.create_check_constraint(
            "ck_sit_asset_val_ac_nonneg",
            "valuation_admin_concursal IS NULL OR valuation_admin_concursal >= 0",
        )
        batch.create_check_constraint(
            "ck_sit_asset_val_ext_nonneg",
            "valuation_external IS NULL OR valuation_external >= 0",
        )
    with op.batch_alter_table("situation_court_records") as batch:
        batch.create_check_constraint(
            "ck_sit_court_amount_nonneg",
            "amount_claimed IS NULL OR amount_claimed >= 0",
        )


def downgrade() -> None:
    # Constraints
    with op.batch_alter_table("situation_court_records") as batch:
        batch.drop_constraint("ck_sit_court_amount_nonneg", type_="check")
    with op.batch_alter_table("situation_assets") as batch:
        batch.drop_constraint("ck_sit_asset_val_ext_nonneg", type_="check")
        batch.drop_constraint("ck_sit_asset_val_ac_nonneg", type_="check")
    with op.batch_alter_table("situation_public_debts") as batch:
        batch.drop_constraint("ck_sit_pub_amount_nonneg", type_="check")
    with op.batch_alter_table("situation_credits") as batch:
        batch.drop_constraint("ck_sit_cred_amount_nonneg", type_="check")
    with op.batch_alter_table("situation_invoices") as batch:
        batch.drop_constraint("ck_sit_inv_amount_nonneg", type_="check")

    # Índices (SQLite: DROP INDEX IF EXISTS)
    if _is_sqlite():
        for ix in [
            "ix_sit_inv_case_supplier",
            "ix_sit_inv_case_due_date",
            "ix_sit_inv_case_amount",
            "ix_sit_inv_case_status",
            "ix_sit_cred_case_creditor",
            "ix_sit_cred_case_amount",
            "ix_sit_cred_case_maturity",
            "ix_sit_asset_case_type",
            "ix_sit_asset_case_val_ac",
            "ix_sit_asset_case_val_ext",
            "ix_sit_pub_case_auth",
            "ix_sit_pub_case_amount",
            "ix_sit_pub_case_deferred",
            "ix_sit_court_case_proc",
            "ix_sit_court_case_type",
            "ix_sit_court_case_amount",
        ]:
            op.execute(sa.text(f"DROP INDEX IF EXISTS {ix}"))
    else:
        op.drop_index("ix_sit_court_case_amount", table_name="situation_court_records")
        op.drop_index("ix_sit_court_case_type", table_name="situation_court_records")
        op.drop_index("ix_sit_court_case_proc", table_name="situation_court_records")
        op.drop_index("ix_sit_pub_case_deferred", table_name="situation_public_debts")
        op.drop_index("ix_sit_pub_case_amount", table_name="situation_public_debts")
        op.drop_index("ix_sit_pub_case_auth", table_name="situation_public_debts")
        op.drop_index("ix_sit_asset_case_val_ext", table_name="situation_assets")
        op.drop_index("ix_sit_asset_case_val_ac", table_name="situation_assets")
        op.drop_index("ix_sit_asset_case_type", table_name="situation_assets")
        op.drop_index("ix_sit_cred_case_maturity", table_name="situation_credits")
        op.drop_index("ix_sit_cred_case_amount", table_name="situation_credits")
        op.drop_index("ix_sit_cred_case_creditor", table_name="situation_credits")
        op.drop_index("ix_sit_inv_case_status", table_name="situation_invoices")
        op.drop_index("ix_sit_inv_case_amount", table_name="situation_invoices")
        op.drop_index("ix_sit_inv_case_due_date", table_name="situation_invoices")
        op.drop_index("ix_sit_inv_case_supplier", table_name="situation_invoices")

