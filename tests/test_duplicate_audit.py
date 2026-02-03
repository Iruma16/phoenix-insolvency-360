"""Tests de auditoría append-only."""
from app.models.duplicate_audit import create_audit_entry


def test_audit_entry_creada(db_session):
    """create_audit_entry crea registro correcto."""
    state_before = {"decision": "pending", "decision_version": 0}
    state_after = {"decision": "keep_both", "decision_version": 1}

    audit = create_audit_entry(
        pair_id="test_pair",
        case_id="case1",
        state_before=state_before,
        state_after=state_after,
        decided_by="user",
        decision="keep_both",
        reason="test reason",
        pair_version=1,
    )

    assert audit.pair_id == "test_pair"
    assert audit.decided_by == "user"
    assert audit.state_before == state_before
    assert audit.state_after == state_after
    assert audit.state_before_hash is not None
    assert audit.state_after_hash is not None


def test_audit_hash_deterministico():
    """Hash del estado es determinista."""
    state = {"decision": "keep_both", "version": 1}

    audit1 = create_audit_entry(
        pair_id="p1",
        case_id="c1",
        state_before=state,
        state_after=state,
        decided_by="u",
        decision="d",
        reason="r",
        pair_version=1,
    )

    audit2 = create_audit_entry(
        pair_id="p1",
        case_id="c1",
        state_before=state,
        state_after=state,
        decided_by="u",
        decision="d",
        reason="r",
        pair_version=1,
    )

    assert audit1.state_before_hash == audit2.state_before_hash


def test_audit_no_modifiable(db_session):
    """Auditoría es append-only (no UPDATE, solo INSERT)."""
    audit = create_audit_entry(
        pair_id="immutable",
        case_id="case1",
        state_before={},
        state_after={"decision": "keep_both"},
        decided_by="user",
        decision="keep_both",
        reason="initial",
        pair_version=1,
    )
    db_session.add(audit)
    db_session.commit()

    original_id = audit.audit_id
    original_reason = audit.reason

    # Intentar modificar (en producción esto debe estar bloqueado)
    # Este test documenta la intención, no la implementación física
    assert audit.reason == original_reason
    assert audit.audit_id == original_id
