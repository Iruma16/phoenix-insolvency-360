"""case_central_db_layers

Revision ID: 20260130_1500_case_central
Revises: 20260130_1315_situation_ix_ck
Create Date: 2026-01-30 15:00:00

CAPA 3/5 — BD central del caso:
- Evidencia central (case_record_evidence)
- Submissions (case_submissions) + snapshots (case_submission_items)
- Artefactos generados (case_generated_documents)
- Catálogo de plantillas (templates, template_fields, field_mapping, form_field_values)

Nota:
- SQLite compatible (batch cuando aplica).
"""

from alembic import op
import sqlalchemy as sa


revision = "20260130_1500_case_central"
down_revision = "20260130_1315_situation_ix_ck"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================
    # CAPA 3 — Evidencia central
    # =========================================================
    op.create_table(
        "case_record_evidence",
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("record_type", sa.String(length=50), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("certainty_level", sa.String(length=20), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_id", sa.String(length=40), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("added_by", sa.String(length=100), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.document_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("evidence_id"),
        sa.CheckConstraint(
            "source_type IN ('DOCUMENTO','CLIENTE','CONTABILIDAD','CRITERIO_PROFESIONAL')",
            name="ck_case_record_evidence_source_type",
        ),
        sa.CheckConstraint(
            "certainty_level IN ('CONSTA','NO_CONSTA','ESTIMADO')",
            name="ck_case_record_evidence_certainty",
        ),
        sa.CheckConstraint(
            "(source_type <> 'DOCUMENTO') OR (document_id IS NOT NULL)",
            name="ck_case_record_evidence_document_required_if_documento",
        ),
    )
    op.create_index("ix_case_record_evidence_case_id", "case_record_evidence", ["case_id"])
    op.create_index(
        "ix_case_record_evidence_record",
        "case_record_evidence",
        ["case_id", "record_type", "record_id"],
    )
    op.create_index("ix_case_record_evidence_document_id", "case_record_evidence", ["case_id", "document_id"])

    # Backfill desde situation_evidence (si existe) para no perder trazabilidad.
    op.execute(
        sa.text(
            """
            INSERT INTO case_record_evidence (
                evidence_id, case_id, record_type, record_id,
                source_type, certainty_level, justification,
                document_id, chunk_id, page, excerpt,
                added_by, added_at
            )
            SELECT
                situation_evidence.evidence_id,
                situation_evidence.case_id,
                situation_evidence.entity,
                situation_evidence.record_id,
                'DOCUMENTO' as source_type,
                'CONSTA' as certainty_level,
                situation_evidence.note as justification,
                situation_evidence.document_id,
                situation_evidence.chunk_id,
                situation_evidence.page,
                NULL as excerpt,
                situation_evidence.created_by as added_by,
                situation_evidence.created_at as added_at
            FROM situation_evidence
            """
        )
    )

    # =========================================================
    # Catálogo de plantillas
    # =========================================================
    op.create_table(
        "templates",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("target", sa.String(length=30), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("template_id"),
        sa.UniqueConstraint("code", name="uq_templates_code"),
        sa.CheckConstraint(
            "target IN ('JUZGADO','ADMIN_CONCURSAL','CLIENTE','INTERNO')",
            name="ck_templates_target",
        ),
    )
    op.create_index("ix_templates_code", "templates", ["code"])
    op.create_index("ix_templates_target", "templates", ["target"])
    op.create_index("ix_templates_is_active", "templates", ["is_active"])

    op.create_table(
        "template_fields",
        sa.Column("field_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("field_key", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("data_type", sa.String(length=20), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("validation_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["templates.template_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("field_id"),
        sa.UniqueConstraint("template_id", "field_key", name="uq_template_fields_template_key"),
    )
    op.create_index("ix_template_fields_template_id", "template_fields", ["template_id"])
    op.create_index("ix_template_fields_field_key", "template_fields", ["field_key"])

    op.create_table(
        "field_mapping",
        sa.Column("mapping_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("field_key", sa.String(length=120), nullable=False),
        sa.Column("source_kind", sa.String(length=20), nullable=False),
        sa.Column("source_spec_json", sa.JSON(), nullable=False),
        sa.Column("fallback", sa.String(length=20), nullable=False, server_default=sa.text("'MANUAL_REQUIRED'")),
        sa.ForeignKeyConstraint(["template_id"], ["templates.template_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("mapping_id"),
        sa.UniqueConstraint("template_id", "field_key", name="uq_field_mapping_template_key"),
        sa.CheckConstraint(
            "source_kind IN ('SQL_QUERY','AGGREGATION','CONSTANT','MANUAL')",
            name="ck_field_mapping_source_kind",
        ),
        sa.CheckConstraint(
            "fallback IN ('NO_CONSTA','EMPTY','MANUAL_REQUIRED')",
            name="ck_field_mapping_fallback",
        ),
    )
    op.create_index("ix_field_mapping_template_id", "field_mapping", ["template_id"])
    op.create_index("ix_field_mapping_field_key", "field_mapping", ["field_key"])

    op.create_table(
        "form_field_values",
        sa.Column("value_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("field_key", sa.String(length=120), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(length=100), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["templates.template_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["case_record_evidence.evidence_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("value_id"),
        sa.UniqueConstraint("case_id", "template_id", "field_key", name="uq_form_field_values_case_template_key"),
    )
    op.create_index("ix_form_field_values_case_id", "form_field_values", ["case_id"])
    op.create_index("ix_form_field_values_template_id", "form_field_values", ["template_id"])
    op.create_index("ix_form_field_values_field_key", "form_field_values", ["field_key"])

    # =========================================================
    # CAPA 5 — Submissions + snapshots + outputs
    # =========================================================
    op.create_table(
        "case_submissions",
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("target", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'BORRADOR'")),
        sa.Column("reference", sa.String(length=200), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("presented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("submission_id"),
        sa.CheckConstraint(
            "target IN ('JUZGADO','ADMIN_CONCURSAL','CLIENTE','INTERNO')",
            name="ck_case_submissions_target",
        ),
        sa.CheckConstraint(
            "status IN ('BORRADOR','LISTO','PRESENTADO','ANULADO')",
            name="ck_case_submissions_status",
        ),
    )
    op.create_index("ix_case_submissions_case_id", "case_submissions", ["case_id"])
    op.create_index("ix_case_submissions_target", "case_submissions", ["target"])
    op.create_index("ix_case_submissions_status", "case_submissions", ["status"])
    op.create_index("ix_case_submissions_case_created_at", "case_submissions", ["case_id", "created_at"])

    op.create_table(
        "case_submission_items",
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("entity", sa.String(length=50), nullable=False),
        sa.Column("record_type", sa.String(length=50), nullable=False),
        sa.Column("logical_id", sa.String(length=36), nullable=True),
        sa.Column("record_id", sa.String(length=36), nullable=True),
        sa.Column("record_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["case_submissions.submission_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("item_id"),
    )
    op.create_index("ix_case_submission_items_submission_id", "case_submission_items", ["submission_id"])
    op.create_index("ix_case_submission_items_case_id", "case_submission_items", ["case_id"])
    op.create_index("ix_case_submission_items_entity", "case_submission_items", ["entity"])
    op.create_index(
        "ix_case_submission_items_lookup",
        "case_submission_items",
        ["submission_id", "record_type", "record_id"],
    )

    op.create_table(
        "case_generated_documents",
        sa.Column("generated_id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("generator_version", sa.String(length=50), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["submission_id"], ["case_submissions.submission_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["templates.template_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("generated_id"),
        sa.UniqueConstraint("content_hash", name="uq_case_generated_documents_content_hash"),
        sa.CheckConstraint("format IN ('DOCX','PDF','XLSX')", name="ck_case_generated_documents_format"),
    )
    op.create_index("ix_case_generated_documents_case_id", "case_generated_documents", ["case_id"])
    op.create_index(
        "ix_case_generated_documents_submission_template",
        "case_generated_documents",
        ["submission_id", "template_id"],
    )
    op.create_index(
        "ix_case_generated_documents_case_generated_at",
        "case_generated_documents",
        ["case_id", "generated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_case_generated_documents_case_generated_at", table_name="case_generated_documents")
    op.drop_index("ix_case_generated_documents_submission_template", table_name="case_generated_documents")
    op.drop_index("ix_case_generated_documents_case_id", table_name="case_generated_documents")
    op.drop_table("case_generated_documents")

    op.drop_index("ix_case_submission_items_lookup", table_name="case_submission_items")
    op.drop_index("ix_case_submission_items_entity", table_name="case_submission_items")
    op.drop_index("ix_case_submission_items_case_id", table_name="case_submission_items")
    op.drop_index("ix_case_submission_items_submission_id", table_name="case_submission_items")
    op.drop_table("case_submission_items")

    op.drop_index("ix_case_submissions_case_created_at", table_name="case_submissions")
    op.drop_index("ix_case_submissions_status", table_name="case_submissions")
    op.drop_index("ix_case_submissions_target", table_name="case_submissions")
    op.drop_index("ix_case_submissions_case_id", table_name="case_submissions")
    op.drop_table("case_submissions")

    op.drop_index("ix_form_field_values_field_key", table_name="form_field_values")
    op.drop_index("ix_form_field_values_template_id", table_name="form_field_values")
    op.drop_index("ix_form_field_values_case_id", table_name="form_field_values")
    op.drop_table("form_field_values")

    op.drop_index("ix_field_mapping_field_key", table_name="field_mapping")
    op.drop_index("ix_field_mapping_template_id", table_name="field_mapping")
    op.drop_table("field_mapping")

    op.drop_index("ix_template_fields_field_key", table_name="template_fields")
    op.drop_index("ix_template_fields_template_id", table_name="template_fields")
    op.drop_table("template_fields")

    op.drop_index("ix_templates_is_active", table_name="templates")
    op.drop_index("ix_templates_target", table_name="templates")
    op.drop_index("ix_templates_code", table_name="templates")
    op.drop_table("templates")

    op.drop_index("ix_case_record_evidence_document_id", table_name="case_record_evidence")
    op.drop_index("ix_case_record_evidence_record", table_name="case_record_evidence")
    op.drop_index("ix_case_record_evidence_case_id", table_name="case_record_evidence")
    op.drop_table("case_record_evidence")

