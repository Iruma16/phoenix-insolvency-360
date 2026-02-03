"""create alerts tables

Revision ID: 20260130_2355
Revises: 20260130_2240_submission_templates
Create Date: 2026-01-30 23:55:00

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20260130_2355"
down_revision = "20260130_2240_submission_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("alert_id", sa.String(length=64), primary_key=True),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String(length=20), nullable=False),
        sa.Column("relevance", sa.String(length=10), nullable=False),
        sa.Column("title_human", sa.Text(), nullable=False),
        sa.Column("summary_human", sa.Text(), nullable=False),
        sa.Column("disclaimer_detail", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_alert_ids", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pendiente'")),
        sa.Column("lawyer_note", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("para_informe", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("changed_since_last_review", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_by", sa.String(length=100), nullable=True),
        sa.Column("rules_version", sa.String(length=64), nullable=True),
        sa.Column("voice_prompt_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_alerts_case_id", "alerts", ["case_id"])
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_para_informe", "alerts", ["para_informe"])
    op.create_index("ix_alerts_domain", "alerts", ["domain"])
    op.create_index("ix_alerts_relevance", "alerts", ["relevance"])
    op.create_index("ix_alerts_fingerprint", "alerts", ["fingerprint"])

    op.create_table(
        "alert_evidences",
        sa.Column("evidence_id", sa.String(length=36), primary_key=True),
        sa.Column("alert_id", sa.String(length=64), sa.ForeignKey("alerts.alert_id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.document_id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column("chunk_id", sa.String(length=64), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("start_char", sa.Integer(), nullable=True),
        sa.Column("end_char", sa.Integer(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.create_index("ix_alert_evidences_alert_id", "alert_evidences", ["alert_id"])
    op.create_index("ix_alert_evidences_document_id", "alert_evidences", ["document_id"])
    op.create_index("ix_alert_evidences_chunk_id", "alert_evidences", ["chunk_id"])


def downgrade() -> None:
    op.drop_index("ix_alert_evidences_chunk_id", table_name="alert_evidences")
    op.drop_index("ix_alert_evidences_document_id", table_name="alert_evidences")
    op.drop_index("ix_alert_evidences_alert_id", table_name="alert_evidences")
    op.drop_table("alert_evidences")

    op.drop_index("ix_alerts_fingerprint", table_name="alerts")
    op.drop_index("ix_alerts_relevance", table_name="alerts")
    op.drop_index("ix_alerts_domain", table_name="alerts")
    op.drop_index("ix_alerts_para_informe", table_name="alerts")
    op.drop_index("ix_alerts_status", table_name="alerts")
    op.drop_index("ix_alerts_case_id", table_name="alerts")
    op.drop_table("alerts")

