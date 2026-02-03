"""extend_situation_fields_link_targets

Revision ID: 20260130_1810_situation_link_fields
Revises: 20260130_1700_case_record_audit
Create Date: 2026-01-30 18:10:00

Añade campos “abogado” mínimos para robustez del enlace de evidencia:
- invoices: supplier_tax_id, contract_ref
- credits: creditor_tax_id, outstanding_principal
- assets: location
- public_debts: expediente_aplazamiento
- court_records: claimant, stage

Notas:
- Campos nuevos son NULLABLE para no romper datos existentes.
- SQLite: se usa batch_alter_table.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260130_1810_situation_link_fields"
down_revision = "20260130_1700_case_record_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("situation_invoices") as b:
        b.add_column(sa.Column("supplier_tax_id", sa.String(length=30), nullable=True))
        b.add_column(sa.Column("contract_ref", sa.String(length=200), nullable=True))

    with op.batch_alter_table("situation_credits") as b:
        b.add_column(sa.Column("creditor_tax_id", sa.String(length=30), nullable=True))
        b.add_column(sa.Column("outstanding_principal", sa.Float(), nullable=True))

    with op.batch_alter_table("situation_assets") as b:
        b.add_column(sa.Column("location", sa.String(length=255), nullable=True))

    with op.batch_alter_table("situation_public_debts") as b:
        b.add_column(sa.Column("expediente_aplazamiento", sa.String(length=120), nullable=True))

    with op.batch_alter_table("situation_court_records") as b:
        b.add_column(sa.Column("claimant", sa.String(length=255), nullable=True))
        b.add_column(sa.Column("stage", sa.String(length=120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("situation_court_records") as b:
        b.drop_column("stage")
        b.drop_column("claimant")

    with op.batch_alter_table("situation_public_debts") as b:
        b.drop_column("expediente_aplazamiento")

    with op.batch_alter_table("situation_assets") as b:
        b.drop_column("location")

    with op.batch_alter_table("situation_credits") as b:
        b.drop_column("outstanding_principal")
        b.drop_column("creditor_tax_id")

    with op.batch_alter_table("situation_invoices") as b:
        b.drop_column("contract_ref")
        b.drop_column("supplier_tax_id")

