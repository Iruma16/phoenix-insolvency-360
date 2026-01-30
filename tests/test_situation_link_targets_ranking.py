import pytest
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.case import Case
from app.models.document import Document


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

    case = Case(case_id="case_lt1", name="Caso LT1")
    session.add(case)
    session.commit()

    doc = Document(
        document_id="doc_lt1",
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
    session.commit()

    def _override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _evidence():
    return [{"document_id": "doc_lt1", "page": 1, "note": "Consta en documento aportado."}]


def test_link_targets_invoice_ranks_invoice_number_over_supplier(client_with_db):
    # Invoice A: match in invoice_number (should rank first)
    a = client_with_db.post(
        "/api/cases/case_lt1/situation/invoices",
        json={
            "created_by": "abogado",
            "reason": "Alta A con evidencia suficiente",
            "evidence": _evidence(),
            "supplier": "Proveedor Normal",
            "invoice_number": "INV-999",
            "amount_total": 100.0,
        },
    )
    assert a.status_code == 200, a.text
    a_id = a.json()["record_id"]

    # Invoice B: match only in supplier (should rank after A)
    b = client_with_db.post(
        "/api/cases/case_lt1/situation/invoices",
        json={
            "created_by": "abogado",
            "reason": "Alta B con evidencia suficiente",
            "evidence": _evidence(),
            "supplier": "INV-999 Suministros SL",
            "amount_total": 200.0,
        },
    )
    assert b.status_code == 200, b.text

    r = client_with_db.get(
        "/api/cases/case_lt1/situation/link-targets",
        params={"record_type": "invoice", "q": "INV-999", "page": 1, "page_size": 10},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) >= 2
    assert items[0]["record_id"] == a_id

