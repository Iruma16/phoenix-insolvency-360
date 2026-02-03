"""submission_snapshot_id_linking

Revision ID: 20260130_2030_submission_snapshot_id
Revises: 20260130_1930_situation_capa2_fields
Create Date: 2026-01-30 20:30:00

CAPA 5 — Blindaje reproducibilidad:
- Añade snapshot_id a case_submission_items (para agrupar items por snapshot).
- Añade snapshot_id a case_generated_documents (para enlazar output ↔ snapshot).
"""

from alembic import op
import sqlalchemy as sa


revision = "20260130_2030_submission_snapshot_id"
down_revision = "20260130_1930_situation_capa2_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("case_submission_items") as b:
        b.add_column(sa.Column("snapshot_id", sa.String(length=36), nullable=True))
        b.create_index("ix_case_submission_items_snapshot_id", ["snapshot_id"])

    with op.batch_alter_table("case_generated_documents") as b:
        b.add_column(sa.Column("snapshot_id", sa.String(length=36), nullable=True))
        b.create_index("ix_case_generated_documents_snapshot_id", ["snapshot_id"])


def downgrade() -> None:
    with op.batch_alter_table("case_generated_documents") as b:
        b.drop_index("ix_case_generated_documents_snapshot_id")
        b.drop_column("snapshot_id")

    with op.batch_alter_table("case_submission_items") as b:
        b.drop_index("ix_case_submission_items_snapshot_id")
        b.drop_column("snapshot_id")

