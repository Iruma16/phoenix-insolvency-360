from __future__ import annotations

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
from app.models.document_chunk import DocumentChunk, ExtractionMethod
from app.services.assistant_alert_voice import VoiceOutput


@pytest.fixture
def client_with_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Patch voice LLM to deterministic output (no network)
    def _fake_voice(*_args, **_kwargs):
        return VoiceOutput(
            title_human="Punto a revisar",
            summary_human="Esto no es concluyente.\n\nYo revisaría el soporte.",
            to_clarify=[],
            disclaimer_detail="Nota",
        )

    monkeypatch.setattr("app.services.alerts_generator.generate_voice_llm", _fake_voice)

    def _override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_smoke_generate_and_get_alerts_structure(client_with_db):
    client, session = client_with_db
    case_id = "case_smoke_1"

    session.add(Case(case_id=case_id, name="Caso Smoke"))
    session.add(
        Document(
            document_id="doc_smoke",
            case_id=case_id,
            filename="tgss.pdf",
            sha256_hash="0" * 64,
            file_size_bytes=10,
            mime_type="application/pdf",
            uploaded_at=datetime.utcnow(),
            doc_type="TGSS",
            doc_type_confidence=1.0,
            doc_type_source="inferred",
            source="test",
            date_start=datetime.utcnow(),
            date_end=datetime.utcnow(),
            reliability="original",
            file_format="pdf",
            storage_path="/tmp/tgss.pdf",
            created_at=datetime.utcnow(),
            deleted_at=None,
        )
    )
    session.commit()

    session.add(
        DocumentChunk(
            chunk_id="chunk_smoke",
            document_id="doc_smoke",
            case_id=case_id,
            chunk_index=0,
            content="TGSS providencia apremio " + ("x" * 120),
            start_char=0,
            end_char=200,
            extraction_method=ExtractionMethod.PDF_TEXT,
            page_start=None,  # dispara MISSING_DATA técnica
            page_end=None,
        )
    )
    session.commit()

    # Generate persisted desk alerts
    r = client.post(f"/api/cases/{case_id}/alerts/generate")
    assert r.status_code == 200, r.text

    # List
    r2 = client.get(f"/api/cases/{case_id}/alerts")
    assert r2.status_code == 200, r2.text
    items = r2.json()
    assert isinstance(items, list)
    assert len(items) >= 1
    item = items[0]
    for k in [
        "alert_id",
        "case_id",
        "domain",
        "relevance",
        "title_human",
        "summary_human",
        "status",
        "lawyer_note",
        "para_informe",
        "updated_at",
    ]:
        assert k in item

    # Detail
    alert_id = item["alert_id"]
    r3 = client.get(f"/api/alerts/{alert_id}")
    assert r3.status_code == 200, r3.text
    detail = r3.json()
    assert "evidences" in detail
    assert isinstance(detail["evidences"], list)
    assert len(detail["evidences"]) >= 1
