from __future__ import annotations

from datetime import datetime
from pathlib import Path

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
def client_with_db(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    def _override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app), session, tmp_path, monkeypatch
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_download_document_original_serves_file(client_with_db):
    client, session, tmp_path, monkeypatch = client_with_db

    # Patch settings.data_dir so the endpoint allows access
    from app.core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "data_dir", tmp_path)

    case_id = "case_dl_1"
    doc_id = "doc_dl_1"
    session.add(Case(case_id=case_id, name="Caso DL"))
    session.commit()

    # Create file under DATA/default/cases/<case_id>/documents/original/<doc_id>.pdf
    p = tmp_path / "default" / "cases" / case_id / "documents" / "original"
    p.mkdir(parents=True, exist_ok=True)
    f = p / f"{doc_id}.pdf"
    f.write_bytes(b"%PDF-1.4 dummy")

    session.add(
        Document(
            document_id=doc_id,
            case_id=case_id,
            filename="x.pdf",
            sha256_hash="0" * 64,
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
            storage_path=str(f),
            created_at=datetime.utcnow(),
            deleted_at=None,
        )
    )
    session.commit()

    r = client.get(f"/api/cases/{case_id}/documents/{doc_id}/download")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")

