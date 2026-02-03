"""migrate_legacy_situation_evidence_audit_to_canonical

Revision ID: 20260130_2200_migrate_situation_legacy
Revises: 20260130_2130_perf_indexes
Create Date: 2026-01-30 22:00:00

Migración de datos (CAPA 1.x):
- situation_evidence -> case_record_evidence
- situation_audit_log -> case_record_audit

Notas:
- Idempotente: si detecta fila equivalente en destino, la omite.
- No elimina tablas legacy (deprecación suave).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op


revision = "20260130_2200_migrate_situation_legacy"
down_revision = "20260130_2130_perf_indexes"
branch_labels = None
depends_on = None


def _map_entity_to_record_type(entity: str) -> str:
    e = (entity or "").strip().upper()
    if e == "INVOICE":
        return "invoice"
    if e == "CREDIT":
        return "loan"
    if e == "ASSET":
        return "asset"
    if e == "PUBLIC_DEBT":
        return "public_debt"
    if e == "COURT":
        return "court_claim"
    return "other"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    # Destinos deben existir (si no, no hacemos nada).
    if "case_record_evidence" not in tables or "case_record_audit" not in tables:
        return

    meta = sa.MetaData()
    meta.bind = bind

    case_record_evidence = sa.Table("case_record_evidence", meta, autoload_with=bind)
    case_record_audit = sa.Table("case_record_audit", meta, autoload_with=bind)

    # =========================================================
    # situation_evidence -> case_record_evidence
    # =========================================================
    if "situation_evidence" in tables:
        legacy_ev = sa.Table("situation_evidence", meta, autoload_with=bind)

        rows = bind.execute(sa.select(legacy_ev)).fetchall()
        for r in rows:
            # r.* depende del dialecto; usar mapping por nombre
            row = dict(r._mapping)  # type: ignore[attr-defined]
            case_id = row.get("case_id")
            entity = row.get("entity")
            record_id = row.get("record_id")
            document_id = row.get("document_id")
            chunk_id = row.get("chunk_id")
            page = row.get("page")
            note = row.get("note")
            created_by = row.get("created_by")
            created_at = row.get("created_at")

            rt = _map_entity_to_record_type(str(entity or ""))

            # Idempotencia: si ya existe una fila equivalente, omitir
            exists = bind.execute(
                sa.select(case_record_evidence.c.evidence_id).where(
                    sa.and_(
                        case_record_evidence.c.case_id == case_id,
                        case_record_evidence.c.record_type == rt,
                        case_record_evidence.c.record_id == record_id,
                        case_record_evidence.c.source_type == "DOCUMENTO",
                        case_record_evidence.c.certainty_level == "CONSTA",
                        case_record_evidence.c.justification == note,
                        case_record_evidence.c.document_id == document_id,
                        case_record_evidence.c.chunk_id == chunk_id,
                        case_record_evidence.c.page == page,
                        case_record_evidence.c.added_by == created_by,
                    )
                )
            ).first()
            if exists:
                continue

            bind.execute(
                sa.insert(case_record_evidence).values(
                    evidence_id=str(uuid.uuid4()),
                    case_id=case_id,
                    record_type=rt,
                    record_id=record_id,
                    source_type="DOCUMENTO",
                    certainty_level="CONSTA",
                    justification=note,
                    document_id=document_id,
                    chunk_id=chunk_id,
                    page=page,
                    excerpt=None,
                    added_by=created_by,
                    added_at=created_at,
                )
            )

    # =========================================================
    # situation_audit_log -> case_record_audit
    # =========================================================
    if "situation_audit_log" in tables:
        legacy_a = sa.Table("situation_audit_log", meta, autoload_with=bind)

        rows = bind.execute(sa.select(legacy_a)).fetchall()
        for r in rows:
            row = dict(r._mapping)  # type: ignore[attr-defined]
            case_id = row.get("case_id")
            entity = row.get("entity")
            logical_id = row.get("logical_id")
            record_id = row.get("record_id")
            action = row.get("action")
            actor = row.get("actor")
            reason = row.get("reason")
            before = row.get("before")
            after = row.get("after")
            created_at = row.get("created_at")

            rt = _map_entity_to_record_type(str(entity or ""))

            exists = bind.execute(
                sa.select(case_record_audit.c.audit_id).where(
                    sa.and_(
                        case_record_audit.c.case_id == case_id,
                        case_record_audit.c.record_type == rt,
                        case_record_audit.c.logical_id == logical_id,
                        case_record_audit.c.record_id == record_id,
                        case_record_audit.c.action == action,
                        case_record_audit.c.actor == actor,
                        case_record_audit.c.justification == reason,
                        case_record_audit.c.created_at == created_at,
                    )
                )
            ).first()
            if exists:
                continue

            bind.execute(
                sa.insert(case_record_audit).values(
                    audit_id=str(uuid.uuid4()),
                    case_id=case_id,
                    record_type=rt,
                    logical_id=logical_id,
                    record_id=record_id,
                    action=action,
                    actor=actor,
                    justification=reason,
                    before_json=before,
                    after_json=after,
                    created_at=created_at,
                )
            )


def downgrade() -> None:
    # No-op: no borramos evidencia/auditoría canónica en downgrade.
    pass

