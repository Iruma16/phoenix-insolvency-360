from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.case import Case
from app.models.document import Document
from app.models.situation import SituationInvoice


@pytest.fixture
def client_with_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    case = Case(case_id="case_ev1", name="Caso EV1")
    session.add(case)
    session.commit()

    doc = Document(
        document_id="doc_ev1",
        case_id=case.case_id,
        filename="dummy.pdf",
        sha256_hash="0" * 64,
        file_size_bytes=1,
        mime_type="application/pdf",
        uploaded_at=datetime.utcnow(),
        doc_type="OTRO",
        source="test",
        date_start=datetime.utcnow(),
        date_end=datetime.utcnow(),
        reliability="original",
        file_format="pdf",
        storage_path="/tmp/dummy.pdf",
        created_at=datetime.utcnow(),
    )
    session.add(doc)

    inv = SituationInvoice(
        logical_id="inv_ev1",
        case_id=case.case_id,
        version=1,
        is_current=True,
        created_by="abogado",
        supplier="Proveedor SL",
        amount_total=10.0,
        currency="EUR",
    )
    session.add(inv)
    session.commit()

    def _override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    try:
        c = TestClient(app)
        setattr(c, "_db_session", session)
        yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_rejects_non_document_source_with_document_id(client_with_db):
    r = client_with_db.post(
        "/api/cases/case_ev1/evidence",
        json={
            "record_type": "other",
            "record_id": None,
            "source_type": "CLIENTE",
            "certainty_level": "ESTIMADO",
            "justification": "Estimación aportada por el cliente con explicación suficiente.",
            "document_id": "doc_ev1",
            "chunk_id": None,
            "page": None,
            "excerpt": None,
            "added_by": "abogado",
        },
    )
    assert r.status_code == 422, r.text


def test_rejects_no_consta_with_short_justification(client_with_db):
    r = client_with_db.post(
        "/api/cases/case_ev1/evidence",
        json={
            "record_type": "other",
            "record_id": None,
            "source_type": "CLIENTE",
            "certainty_level": "NO_CONSTA",
            "justification": "No consta.",
            "document_id": None,
            "chunk_id": None,
            "page": None,
            "excerpt": None,
            "added_by": "abogado",
        },
    )
    assert r.status_code == 422, r.text


def test_rejects_record_id_missing_for_invoice_record_type(client_with_db):
    r = client_with_db.post(
        "/api/cases/case_ev1/evidence",
        json={
            "record_type": "invoice",
            "record_id": None,
            "source_type": "DOCUMENTO",
            "certainty_level": "CONSTA",
            "justification": "Consta en documento aportado por el cliente.",
            "document_id": "doc_ev1",
            "chunk_id": None,
            "page": 1,
            "excerpt": "…extracto…",
            "added_by": "abogado",
        },
    )
    assert r.status_code == 422, r.text


def test_rejects_record_id_not_in_case(client_with_db):
    r = client_with_db.post(
        "/api/cases/case_ev1/evidence",
        json={
            "record_type": "invoice",
            "record_id": "inv_no_exist",
            "source_type": "DOCUMENTO",
            "certainty_level": "CONSTA",
            "justification": "Consta en documento aportado por el cliente.",
            "document_id": "doc_ev1",
            "chunk_id": None,
            "page": 1,
            "excerpt": "…extracto…",
            "added_by": "abogado",
        },
    )
    assert r.status_code == 422, r.text
