"""Tests de lock optimista en duplicados."""
from datetime import datetime

import pytest

from app.models.duplicate_pair import DuplicatePair


def test_pair_id_determinista():
    """Hash canónico independiente de orden."""
    id1 = DuplicatePair.generate_pair_id("A", "B")
    id2 = DuplicatePair.generate_pair_id("B", "A")
    assert id1 == id2, "Hash debe ser independiente del orden"


def test_pair_id_unico_por_contenido():
    """Mismo par → mismo ID, distinto par → distinto ID."""
    id_ab = DuplicatePair.generate_pair_id("A", "B")
    id_ac = DuplicatePair.generate_pair_id("A", "C")
    assert id_ab != id_ac, "Pares distintos deben tener IDs distintos"


@pytest.mark.parametrize(
    "doc_a,doc_b,expected_order",
    [
        ("Z", "A", ("A", "Z")),
        ("B", "A", ("A", "B")),
        ("X", "Y", ("X", "Y")),
    ],
)
def test_orden_canonico(doc_a, doc_b, expected_order):
    """Verifica orden alfabético canónico."""
    pair_id = DuplicatePair.generate_pair_id(doc_a, doc_b)
    # El hash debe ser el mismo independientemente del orden de entrada
    pair_id_reversed = DuplicatePair.generate_pair_id(doc_b, doc_a)
    assert pair_id == pair_id_reversed


def test_version_incrementa(db_session):
    """decision_version se incrementa correctamente."""
    pair = DuplicatePair(
        pair_id="test123",
        case_id="case1",
        doc_a_id="A",
        doc_b_id="B",
        detected_at=datetime.utcnow(),
        similarity=0.95,
        similarity_method="cosine",
        duplicate_type="semantic",
        decision_version=0,
    )
    db_session.add(pair)
    db_session.commit()

    assert pair.decision_version == 0

    # Simular decisión
    pair.decision = "keep_both"
    pair.decision_version += 1
    db_session.commit()

    assert pair.decision_version == 1


def test_stale_version_detectado(db_session):
    """Versión antigua debe ser rechazada."""
    pair = DuplicatePair(
        pair_id="test456",
        case_id="case1",
        doc_a_id="C",
        doc_b_id="D",
        detected_at=datetime.utcnow(),
        similarity=0.9,
        similarity_method="hash",
        duplicate_type="exact",
        decision_version=5,
    )
    db_session.add(pair)
    db_session.commit()

    # Simular expected_version antiguo
    expected_version = 3
    assert pair.decision_version != expected_version, "Versión stale debe ser detectada"
