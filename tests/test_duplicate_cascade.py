"""Tests de invalidación en cascada."""
from datetime import datetime

from app.models.duplicate_pair import DuplicatePair
from app.services.duplicate_cascade import invalidate_pairs_for_document


def test_cascade_invalida_pares(db_session):
    """Excluir documento invalida sus pares."""
    # Setup: A-B, B-C
    pair_ab = DuplicatePair(
        pair_id="ab",
        case_id="case1",
        doc_a_id="A",
        doc_b_id="B",
        detected_at=datetime.utcnow(),
        similarity=0.95,
        similarity_method="cosine",
        duplicate_type="semantic",
        decision_version=0,
    )
    pair_bc = DuplicatePair(
        pair_id="bc",
        case_id="case1",
        doc_a_id="B",
        doc_b_id="C",
        detected_at=datetime.utcnow(),
        similarity=0.92,
        similarity_method="cosine",
        duplicate_type="semantic",
        decision_version=0,
    )
    db_session.add_all([pair_ab, pair_bc])
    db_session.commit()

    # Excluir B
    result = invalidate_pairs_for_document(
        document_id="B",
        case_id="case1",
        reason="duplicado",
        invalidated_by="test_user",
        db=db_session,
    )

    # Verificar
    assert len(result.invalidated_pairs) == 2
    assert "ab" in result.invalidated_pairs
    assert "bc" in result.invalidated_pairs

    # Verificar estado DB
    db_session.refresh(pair_ab)
    db_session.refresh(pair_bc)

    assert pair_ab.invalidated_at is not None
    assert pair_bc.invalidated_at is not None
    assert pair_ab.decision == "invalidated_by_cascade"
    assert pair_bc.decision == "invalidated_by_cascade"


def test_cascade_incrementa_version(db_session):
    """Invalidación incrementa decision_version."""
    pair = DuplicatePair(
        pair_id="xy",
        case_id="case1",
        doc_a_id="X",
        doc_b_id="Y",
        detected_at=datetime.utcnow(),
        similarity=0.99,
        similarity_method="hash",
        duplicate_type="exact",
        decision_version=0,
    )
    db_session.add(pair)
    db_session.commit()

    invalidate_pairs_for_document("X", "case1", "test", "user", db_session)

    db_session.refresh(pair)
    assert pair.decision_version == 1


def test_cascade_genera_warnings(db_session):
    """Invalidar par con decisión previa genera warning."""
    pair = DuplicatePair(
        pair_id="pq",
        case_id="case1",
        doc_a_id="P",
        doc_b_id="Q",
        detected_at=datetime.utcnow(),
        similarity=0.98,
        similarity_method="cosine",
        duplicate_type="semantic",
        decision="keep_both",
        decided_by="lawyer",
        decision_version=1,
    )
    db_session.add(pair)
    db_session.commit()

    result = invalidate_pairs_for_document("P", "case1", "test", "user", db_session)

    assert len(result.warnings) > 0
    assert "keep_both" in result.warnings[0]


def test_cascade_no_invalida_ya_invalidados(db_session):
    """No procesa pares ya invalidados."""
    pair = DuplicatePair(
        pair_id="mn",
        case_id="case1",
        doc_a_id="M",
        doc_b_id="N",
        detected_at=datetime.utcnow(),
        similarity=0.96,
        similarity_method="cosine",
        duplicate_type="semantic",
        invalidated_at=datetime.utcnow(),
        decision_version=0,
    )
    db_session.add(pair)
    db_session.commit()

    result = invalidate_pairs_for_document("M", "case1", "test", "user", db_session)

    assert len(result.invalidated_pairs) == 0
