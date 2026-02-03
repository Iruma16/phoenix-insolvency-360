"""create_situation_tables

Revision ID: 20260130_1230_situation
Revises: 20260130_1200_doc_types_v2
Create Date: 2026-01-30 12:30:00

Cuadro de situación (SQL):
- Tablas por entidad (facturas, créditos, bienes, deuda pública, juzgado)
- Evidencia obligatoria (append-only)
- Auditoría append-only
"""

from alembic import op
import sqlalchemy as sa


revision = "20260130_1230_situation"
down_revision = "20260130_1200_doc_types_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Evidencia (polimórfica por entity+record_id)
    op.create_table(
        "situation_evidence",
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("entity", sa.String(length=40), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=40), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.document_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("evidence_id"),
    )
    op.create_index("ix_situation_evidence_case_id", "situation_evidence", ["case_id"])
    op.create_index("ix_situation_evidence_entity", "situation_evidence", ["entity"])
    op.create_index("ix_situation_evidence_record_id", "situation_evidence", ["record_id"])
    op.create_index("ix_situation_evidence_document_id", "situation_evidence", ["document_id"])

    # Auditoría
    op.create_table(
        "situation_audit_log",
        sa.Column("audit_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("entity", sa.String(length=40), nullable=False),
        sa.Column("logical_id", sa.String(length=36), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index("ix_situation_audit_case_id", "situation_audit_log", ["case_id"])
    op.create_index("ix_situation_audit_entity", "situation_audit_log", ["entity"])
    op.create_index("ix_situation_audit_logical_id", "situation_audit_log", ["logical_id"])
    op.create_index("ix_situation_audit_record_id", "situation_audit_log", ["record_id"])

    # Facturas
    op.create_table(
        "situation_invoices",
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("logical_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("supersedes_record_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("supplier", sa.String(length=255), nullable=False),
        sa.Column("invoice_number", sa.String(length=100), nullable=True),
        sa.Column("issue_date", sa.String(length=10), nullable=True),
        sa.Column("due_date", sa.String(length=10), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("amount_total", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("record_id"),
    )
    op.create_index("ix_situation_invoices_case_id", "situation_invoices", ["case_id"])
    op.create_index("ix_situation_invoices_logical_id", "situation_invoices", ["logical_id"])
    op.create_index("ix_situation_invoices_is_current", "situation_invoices", ["is_current"])

    # Créditos
    op.create_table(
        "situation_credits",
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("logical_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("supersedes_record_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("creditor", sa.String(length=255), nullable=False),
        sa.Column("contract_ref", sa.String(length=200), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("amount_total", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("secured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("guarantee_details", sa.Text(), nullable=True),
        sa.Column("maturity_date", sa.String(length=10), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("record_id"),
    )
    op.create_index("ix_situation_credits_case_id", "situation_credits", ["case_id"])
    op.create_index("ix_situation_credits_logical_id", "situation_credits", ["logical_id"])
    op.create_index("ix_situation_credits_is_current", "situation_credits", ["is_current"])

    # Bienes
    op.create_table(
        "situation_assets",
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("logical_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("supersedes_record_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("asset_type", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("valuation_admin_concursal", sa.Float(), nullable=True),
        sa.Column("valuation_external", sa.Float(), nullable=True),
        sa.Column("valuation_date", sa.String(length=10), nullable=True),
        sa.Column("liens", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("record_id"),
    )
    op.create_index("ix_situation_assets_case_id", "situation_assets", ["case_id"])
    op.create_index("ix_situation_assets_logical_id", "situation_assets", ["logical_id"])
    op.create_index("ix_situation_assets_is_current", "situation_assets", ["is_current"])

    # Deuda pública
    op.create_table(
        "situation_public_debts",
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("logical_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("supersedes_record_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("authority", sa.String(length=20), nullable=False),
        sa.Column("concept", sa.String(length=255), nullable=True),
        sa.Column("period_start", sa.String(length=10), nullable=True),
        sa.Column("period_end", sa.String(length=10), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("amount_total", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("deferred", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("record_id"),
    )
    op.create_index("ix_situation_public_debts_case_id", "situation_public_debts", ["case_id"])
    op.create_index("ix_situation_public_debts_logical_id", "situation_public_debts", ["logical_id"])
    op.create_index("ix_situation_public_debts_is_current", "situation_public_debts", ["is_current"])

    # Juzgado / actuaciones
    op.create_table(
        "situation_court_records",
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("logical_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("supersedes_record_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("court", sa.String(length=255), nullable=True),
        sa.Column("procedure_number", sa.String(length=100), nullable=True),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("action_date", sa.String(length=10), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("amount_claimed", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("record_id"),
    )
    op.create_index("ix_situation_court_case_id", "situation_court_records", ["case_id"])
    op.create_index("ix_situation_court_logical_id", "situation_court_records", ["logical_id"])
    op.create_index("ix_situation_court_is_current", "situation_court_records", ["is_current"])


def downgrade() -> None:
    op.drop_index("ix_situation_court_is_current", table_name="situation_court_records")
    op.drop_index("ix_situation_court_logical_id", table_name="situation_court_records")
    op.drop_index("ix_situation_court_case_id", table_name="situation_court_records")
    op.drop_table("situation_court_records")

    op.drop_index("ix_situation_public_debts_is_current", table_name="situation_public_debts")
    op.drop_index("ix_situation_public_debts_logical_id", table_name="situation_public_debts")
    op.drop_index("ix_situation_public_debts_case_id", table_name="situation_public_debts")
    op.drop_table("situation_public_debts")

    op.drop_index("ix_situation_assets_is_current", table_name="situation_assets")
    op.drop_index("ix_situation_assets_logical_id", table_name="situation_assets")
    op.drop_index("ix_situation_assets_case_id", table_name="situation_assets")
    op.drop_table("situation_assets")

    op.drop_index("ix_situation_credits_is_current", table_name="situation_credits")
    op.drop_index("ix_situation_credits_logical_id", table_name="situation_credits")
    op.drop_index("ix_situation_credits_case_id", table_name="situation_credits")
    op.drop_table("situation_credits")

    op.drop_index("ix_situation_invoices_is_current", table_name="situation_invoices")
    op.drop_index("ix_situation_invoices_logical_id", table_name="situation_invoices")
    op.drop_index("ix_situation_invoices_case_id", table_name="situation_invoices")
    op.drop_table("situation_invoices")

    op.drop_index("ix_situation_audit_record_id", table_name="situation_audit_log")
    op.drop_index("ix_situation_audit_logical_id", table_name="situation_audit_log")
    op.drop_index("ix_situation_audit_entity", table_name="situation_audit_log")
    op.drop_index("ix_situation_audit_case_id", table_name="situation_audit_log")
    op.drop_table("situation_audit_log")

    op.drop_index("ix_situation_evidence_document_id", table_name="situation_evidence")
    op.drop_index("ix_situation_evidence_record_id", table_name="situation_evidence")
    op.drop_index("ix_situation_evidence_entity", table_name="situation_evidence")
    op.drop_index("ix_situation_evidence_case_id", table_name="situation_evidence")
    op.drop_table("situation_evidence")

