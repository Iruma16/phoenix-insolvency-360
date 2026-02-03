from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.alert import Alert  # noqa: F401  (registers table in Base.metadata)
from app.models.alert_evidence import AlertEvidence  # noqa: F401
from app.models.case import Case
from app.models.document import Document
from app.models.document_chunk import DocumentChunk, ExtractionMethod
from app.services.assistant_alert_voice import VoiceOutput


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


def _seed_case_doc_and_chunk(session, *, case_id: str, doc_id: str):
    case = Case(case_id=case_id, name="Caso Alerts")
    session.add(case)
    session.commit()

    doc = Document(
        document_id=doc_id,
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
    session.add(doc)
    session.commit()

    # Chunk PDF_TEXT sin page_start => dispara alerta técnica MISSING_DATA
    session.add(
        DocumentChunk(
            chunk_id="chunk_1",
            document_id=doc_id,
            case_id=case_id,
            chunk_index=0,
            content="TGSS providencia apremio " + ("x" * 120),
            start_char=0,
            end_char=150,
            extraction_method=ExtractionMethod.PDF_TEXT,
            page_start=None,
            page_end=None,
        )
    )
    session.commit()


def test_alerts_generate_persists_and_patch_updates(client_with_db, monkeypatch):
    client, session = client_with_db
    case_id = "case_alerts_1"
    doc_id = "doc_alerts_1"
    _seed_case_doc_and_chunk(session, case_id=case_id, doc_id=doc_id)

    # Evitar LLM: patch del símbolo importado en alerts_generator
    def _fake_generate_voice_llm(*_args, **_kwargs):
        return VoiceOutput(
            title_human="Punto a revisar",
            summary_human="Esto no es concluyente.\n\nYo revisaría el soporte y la trazabilidad.",
            to_clarify=[],
            disclaimer_detail="Nota: revisión preliminar.",
        )

    monkeypatch.setattr(
        "app.services.alerts_generator.generate_voice_llm", _fake_generate_voice_llm
    )

    r = client.post(f"/api/cases/{case_id}/alerts/generate")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["case_id"] == case_id
    assert body["generated_count"] >= 1

    r2 = client.get(f"/api/cases/{case_id}/alerts")
    assert r2.status_code == 200, r2.text
    items = r2.json()
    assert isinstance(items, list) and len(items) >= 1
    alert_id = items[0]["alert_id"]

    r3 = client.get(f"/api/alerts/{alert_id}")
    assert r3.status_code == 200, r3.text
    detail = r3.json()
    assert detail["alert_id"] == alert_id
    assert detail["case_id"] == case_id
    assert isinstance(detail["evidences"], list)
    assert len(detail["evidences"]) >= 1
    # contrato extendido (siempre debe existir, aunque vacío)
    assert "to_clarify" in detail
    assert "recommended_actions" in detail
    assert "score" in detail

    r4 = client.patch(
        f"/api/alerts/{alert_id}",
        json={"status": "revisada", "lawyer_note": "Ok", "updated_by": "test"},
    )
    assert r4.status_code == 200, r4.text
    assert r4.json()["status"] == "ok"

    r5 = client.get(f"/api/alerts/{alert_id}")
    assert r5.status_code == 200, r5.text
    detail2 = r5.json()
    assert detail2["status"] == "revisada"
    assert detail2["lawyer_note"] == "Ok"
    assert detail2["updated_by"] == "test"


def test_documents_ingest_triggers_alerts_background_task(client_with_db, monkeypatch):
    client, session = client_with_db
    case_id = "case_ingest_alerts"

    # Seed caso mínimo (documents endpoint exige caso existente)
    session.add(Case(case_id=case_id, name="Caso Ingest"))
    session.commit()

    # Parchar dependencias pesadas de ingesta para un test rápido y determinista
    from app.api import documents as documents_api
    from app.services.ingesta import ParsingResult

    def _fake_store_document_file(*_args, **_kwargs):
        return {
            "original_filename": "a.txt",
            "storage_path": "/tmp/a.txt",
            "sha256_hash": "a" * 64,
            "file_size_bytes": 5,
            "mime_type": "text/plain",
        }

    def _fake_ingerir_archivo(*_args, **_kwargs):
        return ParsingResult(texto="hola", num_paginas=1, tipo_documento="txt")

    def _fake_chunking(*_args, **_kwargs):
        return None

    called = {"ok": False}

    def _fake_generate_bg(*_args, **kwargs):
        # BackgroundTasks lo llamará con case_id como kwarg
        assert kwargs.get("case_id") == case_id
        called["ok"] = True
        return 1

    monkeypatch.setattr(documents_api, "store_document_file", _fake_store_document_file)
    monkeypatch.setattr(documents_api, "ingerir_archivo", _fake_ingerir_archivo)
    monkeypatch.setattr(documents_api, "build_document_chunks_for_single_document", _fake_chunking)
    monkeypatch.setattr(
        "app.services.alerts_generator.generate_persisted_alerts_for_case_in_new_session",
        _fake_generate_bg,
    )

    files = [("files", ("a.txt", b"hola", "text/plain"))]
    r = client.post(f"/api/cases/{case_id}/documents", files=files)
    assert r.status_code in (200, 201), r.text

    # En TestClient, BackgroundTasks se ejecuta al finalizar el request
    assert called["ok"] is True
