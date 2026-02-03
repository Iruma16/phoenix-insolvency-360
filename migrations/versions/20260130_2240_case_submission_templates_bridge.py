"""case_submission_templates_bridge

Revision ID: 20260130_2240_submission_templates
Revises: 20260130_2200_migrate_situation_legacy
Create Date: 2026-01-30 22:40:00

CAPA 5 (opcional hardening):
- Tabla puente case_submission_templates para asociar plantillas a un submission.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260130_2240_submission_templates"
down_revision = "20260130_2200_migrate_situation_legacy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_submission_templates",
        sa.Column("link_id", sa.String(length=36), primary_key=True),
        sa.Column("submission_id", sa.String(length=36), sa.ForeignKey("case_submissions.submission_id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), sa.ForeignKey("templates.template_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("added_by", sa.String(length=100), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("submission_id", "template_id", name="uq_case_submission_templates_submission_template"),
    )
    op.create_index("ix_case_submission_templates_submission_id", "case_submission_templates", ["submission_id"])
    op.create_index("ix_case_submission_templates_case_id", "case_submission_templates", ["case_id"])
    op.create_index("ix_case_submission_templates_template_id", "case_submission_templates", ["template_id"])


def downgrade() -> None:
    op.drop_index("ix_case_submission_templates_template_id", table_name="case_submission_templates")
    op.drop_index("ix_case_submission_templates_case_id", table_name="case_submission_templates")
    op.drop_index("ix_case_submission_templates_submission_id", table_name="case_submission_templates")
    op.drop_table("case_submission_templates")

