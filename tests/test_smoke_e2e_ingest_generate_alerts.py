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

    def _override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app), session, monkeypatch
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_smoke_ingest_dataset_then_generate_alerts(client_with_db):
    client, session, monkeypatch = client_with_db
    case_id = "case_ingest_smoke"
    session.add(Case(case_id=case_id, name="Caso Ingest Smoke"))
    session.commit()

    # Patch ingestion so it doesn't touch filesystem/LLM but still creates DocumentChunk.
    from app.api import documents as documents_api
    from app.services.ingesta import ParsingResult

    def _fake_store_document_file(*_args, **_kwargs):
        return {
            "original_filename": "dataset.txt",
            "storage_path": "/tmp/dataset.txt",
            "sha256_hash": "a" * 64,
            "file_size_bytes": 5,
            "mime_type": "text/plain",
        }

    def _fake_ingerir_archivo(*_args, **_kwargs):
        return ParsingResult(
            texto="TGSS providencia apremio 2024-01 2024-02 Importe principal 1.000,00 €",
            num_paginas=1,
            tipo_documento="txt",
        )

    def _fake_chunking(*, db, document_id: str, case_id: str, text: str, parsing_result, overwrite: bool, **_):
        # Minimal chunk to allow analysis_alerts to build evidence.
        db.add(
            DocumentChunk(
                chunk_id=f"chunk_{document_id[:6]}",
                document_id=document_id,
                case_id=case_id,
                chunk_index=0,
                content=text + ("x" * 60),
                start_char=0,
                end_char=max(120, len(text)),
                extraction_method=ExtractionMethod.PDF_TEXT,
                page_start=1,
                page_end=1,
            )
        )
        db.commit()

    # Avoid auto-generation background task doing work during ingestion
    monkeypatch.setattr(
        "app.services.alerts_generator.generate_persisted_alerts_for_case_in_new_session",
        lambda **_: 0,
    )

    # Avoid LLM in /alerts/generate
    monkeypatch.setattr(
        "app.services.alerts_generator.generate_voice_llm",
        lambda *_args, **_kwargs: VoiceOutput(
            title_human="Punto a revisar",
            summary_human="Esto no es concluyente.\n\nYo revisaría el soporte.",
            to_clarify=[],
            disclaimer_detail="Nota",
        ),
    )

    monkeypatch.setattr(documents_api, "store_document_file", _fake_store_document_file)
    monkeypatch.setattr(documents_api, "ingerir_archivo", _fake_ingerir_archivo)
    monkeypatch.setattr(documents_api, "build_document_chunks_for_single_document", _fake_chunking)

    files = [("files", ("dataset.txt", b"hola", "text/plain"))]
    r = client.post(f"/api/cases/{case_id}/documents", files=files)
    assert r.status_code in (200, 201), r.text

    r2 = client.post(f"/api/cases/{case_id}/alerts/generate")
    assert r2.status_code == 200, r2.text

    r3 = client.get(f"/api/cases/{case_id}/alerts")
    assert r3.status_code == 200, r3.text
    assert isinstance(r3.json(), list)

