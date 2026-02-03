"""extend alerts contract (score, checklist, actions, versioning)

Revision ID: 20260131_1200
Revises: 20260130_2355
Create Date: 2026-01-31 12:00:00

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260131_1200"
down_revision = "20260130_2355"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # alerts: score + contract extensions
    op.add_column("alerts", sa.Column("score", sa.Integer(), nullable=True))
    op.add_column("alerts", sa.Column("to_clarify", sa.JSON(), nullable=True))
    op.add_column("alerts", sa.Column("recommended_actions", sa.JSON(), nullable=True))

    op.add_column("alerts", sa.Column("generator_version", sa.String(length=64), nullable=True))
    op.add_column("alerts", sa.Column("dataset_version", sa.String(length=64), nullable=True))
    op.add_column("alerts", sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("alerts", sa.Column("generated_by", sa.String(length=100), nullable=True))

    op.create_index("ix_alerts_score", "alerts", ["score"])

    # alert_evidences: add human signal
    op.add_column("alert_evidences", sa.Column("signal", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("alert_evidences", "signal")

    op.drop_index("ix_alerts_score", table_name="alerts")
    op.drop_column("alerts", "generated_by")
    op.drop_column("alerts", "generated_at")
    op.drop_column("alerts", "dataset_version")
    op.drop_column("alerts", "generator_version")
    op.drop_column("alerts", "recommended_actions")
    op.drop_column("alerts", "to_clarify")
    op.drop_column("alerts", "score")

