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
from app.services.document_pre_ingestion_validation import check_format_supported


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

    case = Case(case_id="case_docs1", name="Caso Docs 1")
    session.add(case)
    session.commit()

    # Seed 3 documentos activos
    for i in range(3):
        session.add(
            Document(
                document_id=f"doc_{i}",
                case_id=case.case_id,
                filename=f"f{i}.pdf",
                sha256_hash=("a" * 63) + str(i),
                file_size_bytes=10,
                mime_type="application/pdf",
                uploaded_at=datetime.utcnow(),
                doc_type="OTRO",
                doc_type_confidence=0.0,
                doc_type_source="inferred",
                source="test",
                date_start=datetime.utcnow(),
                date_end=datetime.utcnow(),
                reliability="original",
                file_format="pdf",
                storage_path=f"/tmp/f{i}.pdf",
                created_at=datetime.utcnow(),
                deleted_at=None,
            )
        )
    session.commit()

    def _override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    try:
        c = TestClient(app)
        yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_documents_paged_endpoint_returns_total_and_limits(client_with_db):
    r = client_with_db.get("/api/cases/case_docs1/documents/paged?page=1&page_size=2")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2


def test_doc_legacy_rejected_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("PHOENIX_ENABLE_DOC_LEGACY", raising=False)
    p = tmp_path / "legacy.doc"
    p.write_bytes(b"dummy")
    ok, code, msg = check_format_supported(p)
    assert ok is False
    assert code is not None
    assert "DOC" in str(code.value)
    assert "PHOENIX_ENABLE_DOC_LEGACY" in msg


def test_doc_legacy_allowed_when_flag_set(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOENIX_ENABLE_DOC_LEGACY", "1")
    p = tmp_path / "legacy.doc"
    p.write_bytes(b"dummy")
    ok, code, msg = check_format_supported(p)
    assert ok is True
    assert code is None
    assert "soportado" in msg.lower()
