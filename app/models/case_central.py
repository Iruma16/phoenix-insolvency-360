from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def stable_json_hash(payload: dict) -> str:
    """
    Hash determinista de un JSON (ordenando claves).
    Útil para snapshots inmutables y detección de cambios.
    """
    s = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class EvidenceSourceType(str, Enum):
    DOCUMENTO = "DOCUMENTO"
    CLIENTE = "CLIENTE"
    CONTABILIDAD = "CONTABILIDAD"
    CRITERIO_PROFESIONAL = "CRITERIO_PROFESIONAL"


class CertaintyLevel(str, Enum):
    CONSTA = "CONSTA"
    NO_CONSTA = "NO_CONSTA"
    ESTIMADO = "ESTIMADO"


class SubmissionTarget(str, Enum):
    JUZGADO = "JUZGADO"
    ADMIN_CONCURSAL = "ADMIN_CONCURSAL"
    CLIENTE = "CLIENTE"
    INTERNO = "INTERNO"


class SubmissionStatus(str, Enum):
    BORRADOR = "BORRADOR"
    LISTO = "LISTO"
    PRESENTADO = "PRESENTADO"
    ANULADO = "ANULADO"


class OutputFormat(str, Enum):
    DOCX = "DOCX"
    PDF = "PDF"
    XLSX = "XLSX"


class MappingSourceKind(str, Enum):
    SQL_QUERY = "SQL_QUERY"
    AGGREGATION = "AGGREGATION"
    CONSTANT = "CONSTANT"
    MANUAL = "MANUAL"


class MappingFallback(str, Enum):
    NO_CONSTA = "NO_CONSTA"
    EMPTY = "EMPTY"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"


class CaseRecordEvidence(Base):
    """
    CAPA 3 — Evidencia central del caso.

    Soporta:
    - Evidencia documental (document_id requerido)
    - Evidencia no documental (CLIENTE/CONTABILIDAD/CRITERIO_PROFESIONAL) con document_id nulo
    - Certeza (CONSTA/NO_CONSTA/ESTIMADO)
    """

    __tablename__ = "case_record_evidence"

    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    record_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    record_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    certainty_level: Mapped[str] = mapped_column(String(20), nullable=False)

    justification: Mapped[str] = mapped_column(Text, nullable=False)

    document_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("documents.document_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    chunk_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_by: Mapped[str] = mapped_column(String(100), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Índice lógico (consultas rápidas por record_type+record_id)
        UniqueConstraint(
            "evidence_id",
            name="uq_case_record_evidence_id",
        ),
        CheckConstraint(
            "source_type IN ('DOCUMENTO','CLIENTE','CONTABILIDAD','CRITERIO_PROFESIONAL')",
            name="ck_case_record_evidence_source_type",
        ),
        CheckConstraint(
            "certainty_level IN ('CONSTA','NO_CONSTA','ESTIMADO')",
            name="ck_case_record_evidence_certainty",
        ),
        # Regla dura: si source_type=DOCUMENTO, document_id obligatorio
        CheckConstraint(
            "(source_type <> 'DOCUMENTO') OR (document_id IS NOT NULL)",
            name="ck_case_record_evidence_document_required_if_documento",
        ),
    )


class CaseSubmission(Base):
    """
    CAPA 5 — Acto (submission) con múltiples outputs.
    """

    __tablename__ = "case_submissions"

    submission_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    target: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, default=SubmissionStatus.BORRADOR.value
    )

    reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    presented_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "target IN ('JUZGADO','ADMIN_CONCURSAL','CLIENTE','INTERNO')",
            name="ck_case_submissions_target",
        ),
        CheckConstraint(
            "status IN ('BORRADOR','LISTO','PRESENTADO','ANULADO')",
            name="ck_case_submissions_status",
        ),
    )


class CaseSubmissionTemplate(Base):
    """
    Plantillas asociadas explícitamente a un submission (acto).
    Permite UX: “un acto con varias plantillas/outputs”.
    """

    __tablename__ = "case_submission_templates"

    link_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    submission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("case_submissions.submission_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("templates.template_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    added_by: Mapped[str] = mapped_column(String(100), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "submission_id", "template_id", name="uq_case_submission_templates_submission_template"
        ),
    )


class CaseSubmissionItem(Base):
    """
    Snapshot inmutable de fuentes usadas para un submission.
    """

    __tablename__ = "case_submission_items"

    item_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    submission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("case_submissions.submission_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    snapshot_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    entity: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    record_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    logical_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    record_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    record_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    evidence_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CaseGeneratedDocument(Base):
    """
    Artefactos generados (fichero + hash).
    """

    __tablename__ = "case_generated_documents"

    generated_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    submission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("case_submissions.submission_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    snapshot_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("templates.template_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    format: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    generator_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "format IN ('DOCX','PDF','XLSX')", name="ck_case_generated_documents_format"
        ),
    )


class Template(Base):
    """
    Catálogo de plantillas.
    """

    __tablename__ = "templates"

    template_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    target: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TemplateField(Base):
    __tablename__ = "template_fields"

    field_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("templates.template_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    data_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # string/number/date/bool/json
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("template_id", "field_key", name="uq_template_fields_template_key"),
    )


class FieldMapping(Base):
    __tablename__ = "field_mapping"

    mapping_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("templates.template_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_spec_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    fallback: Mapped[str] = mapped_column(
        String(20), nullable=False, default=MappingFallback.MANUAL_REQUIRED.value
    )

    __table_args__ = (
        UniqueConstraint("template_id", "field_key", name="uq_field_mapping_template_key"),
        CheckConstraint(
            "source_kind IN ('SQL_QUERY','AGGREGATION','CONSTANT','MANUAL')",
            name="ck_field_mapping_source_kind",
        ),
        CheckConstraint(
            "fallback IN ('NO_CONSTA','EMPTY','MANUAL_REQUIRED')",
            name="ck_field_mapping_fallback",
        ),
    )


class FormFieldValue(Base):
    """
    Valores manuales por caso/plantilla/campo.
    """

    __tablename__ = "form_field_values"

    value_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("templates.template_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    value_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    evidence_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("case_record_evidence.evidence_id", ondelete="SET NULL"),
        nullable=True,
    )
    justification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    updated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "case_id", "template_id", "field_key", name="uq_form_field_values_case_template_key"
        ),
    )


class AuditAction(str, Enum):
    """
    Acciones estandarizadas para auditoría append-only (CAPA 4).
    """

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    SOFT_DELETE = "SOFT_DELETE"
    ADD_EVIDENCE = "ADD_EVIDENCE"
    SUBMISSION_CREATE = "SUBMISSION_CREATE"
    SUBMISSION_STATUS_CHANGE = "SUBMISSION_STATUS_CHANGE"
    SNAPSHOT_CREATE = "SNAPSHOT_CREATE"
    OUTPUT_GENERATE = "OUTPUT_GENERATE"


class CaseRecordAudit(Base):
    """
    CAPA 4 — Auditoría canónica (append-only).

    Regla:
    - Nunca se edita/borrar: solo se inserta.
    - Referencia polimórfica: record_type + logical_id/record_id (según entidad).
    """

    __tablename__ = "case_record_audit"

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Catálogo canónico (record_type)
    record_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Identidad del registro (preferir logical_id si hay versionado)
    logical_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    record_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)

    before_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "record_type IN ('invoice','loan','asset','public_debt','court_claim','form_field','other')",
            name="ck_case_record_audit_record_type",
        ),
        CheckConstraint(
            "action IN ('CREATE','UPDATE','SOFT_DELETE','ADD_EVIDENCE','SUBMISSION_CREATE','SUBMISSION_STATUS_CHANGE','SNAPSHOT_CREATE','OUTPUT_GENERATE')",
            name="ck_case_record_audit_action",
        ),
        # Justificación mínima (defensivo). Nota: SQLite también soporta LENGTH().
        CheckConstraint(
            "LENGTH(justification) >= 10", name="ck_case_record_audit_justification_minlen"
        ),
    )
