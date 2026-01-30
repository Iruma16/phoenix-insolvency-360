"""case_record_audit_canonical

Revision ID: 20260130_1700_case_record_audit
Revises: 20260130_1500_case_central
Create Date: 2026-01-30 17:00:00

CAPA 4 — Auditoría canónica (append-only) + migración desde situation_audit_log.
Además:
- Normaliza record_type canónico en case_record_evidence (INVOICE->invoice, etc.)
- Normaliza record_type en case_submission_items (form_fields -> form_field)
"""

from alembic import op
import sqlalchemy as sa


revision = "20260130_1700_case_record_audit"
down_revision = "20260130_1500_case_central"
branch_labels = None
depends_on = None


_ENTITY_TO_RECORD_TYPE_CASE_SQL = """
CASE
  WHEN entity = 'INVOICE' THEN 'invoice'
  WHEN entity = 'CREDIT' THEN 'loan'
  WHEN entity = 'ASSET' THEN 'asset'
  WHEN entity = 'PUBLIC_DEBT' THEN 'public_debt'
  WHEN entity = 'COURT' THEN 'court_claim'
  ELSE 'other'
END
"""


def upgrade() -> None:
    # =========================================================
    # CAPA 4 — Auditoría canónica
    # =========================================================
    op.create_table(
        "case_record_audit",
        sa.Column("audit_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("record_type", sa.String(length=50), nullable=False),
        sa.Column("logical_id", sa.String(length=36), nullable=True),
        sa.Column("record_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("audit_id"),
        sa.CheckConstraint(
            "record_type IN ('invoice','loan','asset','public_debt','court_claim','form_field','other')",
            name="ck_case_record_audit_record_type",
        ),
        sa.CheckConstraint(
            "action IN ('CREATE','UPDATE','SOFT_DELETE','ADD_EVIDENCE','SUBMISSION_CREATE','SUBMISSION_STATUS_CHANGE','SNAPSHOT_CREATE','OUTPUT_GENERATE')",
            name="ck_case_record_audit_action",
        ),
        sa.CheckConstraint("LENGTH(justification) >= 10", name="ck_case_record_audit_justification_minlen"),
    )
    op.create_index("ix_case_record_audit_case_id", "case_record_audit", ["case_id"])
    op.create_index(
        "ix_case_record_audit_record",
        "case_record_audit",
        ["case_id", "record_type", "logical_id", "record_id"],
    )
    op.create_index("ix_case_record_audit_action", "case_record_audit", ["action"])

    # ---------------------------------------------------------
    # Migración histórica desde situation_audit_log -> case_record_audit
    # ---------------------------------------------------------
    # Nota: el objetivo es migrar TODO el histórico (estrategia B).
    op.execute(
        sa.text(
            f"""
            INSERT INTO case_record_audit (
              audit_id, case_id, record_type, logical_id, record_id,
              action, actor, justification, before_json, after_json, created_at
            )
            SELECT
              audit_id,
              case_id,
              {_ENTITY_TO_RECORD_TYPE_CASE_SQL} as record_type,
              logical_id,
              record_id,
              action,
              actor,
              reason as justification,
              "before" as before_json,
              "after" as after_json,
              created_at
            FROM situation_audit_log
            """
        )
    )

    # =========================================================
    # Normalización record_type canónico (CAPA 3 / CAPA 5)
    # =========================================================
    # case_record_evidence: record_type venía como entity (INVOICE/CREDIT/...)
    op.execute(
        sa.text(
            """
            UPDATE case_record_evidence
            SET record_type = CASE record_type
              WHEN 'INVOICE' THEN 'invoice'
              WHEN 'CREDIT' THEN 'loan'
              WHEN 'ASSET' THEN 'asset'
              WHEN 'PUBLIC_DEBT' THEN 'public_debt'
              WHEN 'COURT' THEN 'court_claim'
              ELSE record_type
            END
            WHERE record_type IN ('INVOICE','CREDIT','ASSET','PUBLIC_DEBT','COURT')
            """
        )
    )

    # case_submission_items: normalizar form_fields -> form_field
    op.execute(
        sa.text(
            """
            UPDATE case_submission_items
            SET record_type = 'form_field'
            WHERE record_type = 'form_fields'
            """
        )
    )


def downgrade() -> None:
    # Best-effort: revertir cambio en case_submission_items (opcional)
    op.execute(
        sa.text(
            """
            UPDATE case_submission_items
            SET record_type = 'form_fields'
            WHERE record_type = 'form_field'
            """
        )
    )
    op.drop_index("ix_case_record_audit_action", table_name="case_record_audit")
    op.drop_index("ix_case_record_audit_record", table_name="case_record_audit")
    op.drop_index("ix_case_record_audit_case_id", table_name="case_record_audit")
    op.drop_table("case_record_audit")

