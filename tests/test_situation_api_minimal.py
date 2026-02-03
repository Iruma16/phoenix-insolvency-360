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

    # Seed mínimo: caso + documento para evidencia
    case = Case(case_id="case_s1", name="Caso S1")
    session.add(case)
    session.commit()

    doc = Document(
        document_id="doc_s1",
        case_id=case.case_id,
        filename="aeat.pdf",
        sha256_hash="0" * 64,
        file_size_bytes=1,
        mime_type="application/pdf",
        uploaded_at=datetime.utcnow(),
        doc_type="AEAT",
        source="test",
        date_start=datetime.utcnow(),
        date_end=datetime.utcnow(),
        reliability="original",
        file_format="pdf",
        storage_path="/tmp/aeat.pdf",
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


def test_create_invoice_requires_evidence(client_with_db):
    # Sin evidencia → 422 (por pydantic min_length)
    r = client_with_db.post(
        "/api/cases/case_s1/situation/invoices",
        json={
            "created_by": "abogado",
            "reason": "Alta inicial",
            "evidence": [],
            "supplier": "Proveedor SL",
            "amount_total": 100.0,
        },
    )
    assert r.status_code in (400, 422)


def test_create_invoice_ok_with_evidence(client_with_db):
    r = client_with_db.post(
        "/api/cases/case_s1/situation/invoices",
        json={
            "created_by": "abogado",
            "reason": "Alta inicial con evidencia",
            "evidence": [
                {"document_id": "doc_s1", "page": 1, "note": "Consta en documento aportado."}
            ],
            "supplier": "Proveedor SL",
            "amount_total": 100.0,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["logical_id"]
    assert data["version"] == 1
    assert data["evidence_count"] >= 1
