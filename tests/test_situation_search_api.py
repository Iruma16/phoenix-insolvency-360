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

    case = Case(case_id="case_search", name="Caso Search")
    session.add(case)
    session.commit()

    doc = Document(
        document_id="doc_search",
        case_id=case.case_id,
        filename="factura_aqualia.pdf",
        sha256_hash="0" * 64,
        file_size_bytes=1,
        mime_type="application/pdf",
        uploaded_at=datetime.utcnow(),
        doc_type="FACTURAS",
        source="test",
        date_start=datetime.utcnow(),
        date_end=datetime.utcnow(),
        reliability="original",
        file_format="pdf",
        storage_path="/tmp/factura_aqualia.pdf",
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


def test_situation_search_returns_invoice_group(client_with_db):
    # Crear una factura en cuadro de situación
    r = client_with_db.post(
        "/api/cases/case_search/situation/invoices",
        json={
            "created_by": "abogado",
            "reason": "Alta inicial con evidencia suficiente",
            "evidence": [{"document_id": "doc_search", "page": 1, "note": "Consta en documento aportado (factura)."}],
            "supplier": "AQUALIA SA",
            "invoice_number": "AQ-2026-001",
            "issue_date": "2026-01-10",
            "due_date": "2026-02-10",
            "amount_total": 123.45,
            "status": "pendiente",
        },
    )
    assert r.status_code == 200, r.text

    # Buscar por proveedor (case insensitive)
    s = client_with_db.get(
        "/api/cases/case_search/situation/search",
        params={"q": "aqualia", "record_types": ["invoice"], "page": 1, "page_size": 20},
    )
    assert s.status_code == 200, s.text
    data = s.json()
    assert data["q"] == "aqualia"
    assert "invoice" in data["groups"]
    inv_group = data["groups"]["invoice"]
    assert inv_group["total"] >= 1
    assert len(inv_group["items"]) >= 1
    first = inv_group["items"][0]
    assert first["entity"] == "INVOICE"
    assert first["data"]["supplier"] == "AQUALIA SA"
    assert first["data"]["invoice_number"] == "AQ-2026-001"

