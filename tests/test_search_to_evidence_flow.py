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
from app.models.document_chunk import DocumentChunk
from app.models.document_chunk import ExtractionMethod


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

    case = Case(case_id="case_se1", name="Caso Search→Evidence")
    session.add(case)
    session.commit()

    doc = Document(
        document_id="doc_se1",
        case_id=case.case_id,
        filename="burofax.pdf",
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
        storage_path="/tmp/burofax.pdf",
        created_at=datetime.utcnow(),
        raw_text="",
    )
    session.add(doc)
    session.flush()

    content = "Este burofax acredita la reclamación de deuda y el impago."
    chunk = DocumentChunk(
        chunk_id="chunk_se1",
        document_id=doc.document_id,
        case_id=case.case_id,
        chunk_index=0,
        content=content,
        page_start=1,
        page_end=1,
        start_char=0,
        end_char=len(content),
        extraction_method=ExtractionMethod.PDF_TEXT,
        content_type="text",
    )
    session.add(chunk)
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


def test_search_returns_chunk_id_and_can_create_evidence_from_result(client_with_db):
    # Buscar (debe encontrar por chunks)
    r = client_with_db.get(
        "/api/cases/case_se1/documents/search",
        params={"q": "burofax", "include_chunk_id": True, "page": 1, "page_size": 20},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] >= 1
    item = data["items"][0]
    assert item["document_id"] == "doc_se1"
    assert item.get("chunk_id") == "chunk_se1"

    # Crear evidencia (CAPA 3) usando document_id+chunk_id del resultado
    ev = client_with_db.post(
        "/api/cases/case_se1/evidence",
        json={
            "record_type": "other",
            "record_id": None,
            "source_type": "DOCUMENTO",
            "certainty_level": "CONSTA",
            "justification": "Consta en burofax aportado. Se adjunta extracto relevante.",
            "document_id": item["document_id"],
            "chunk_id": item["chunk_id"],
            "page": item.get("page") or 1,
            "excerpt": "…burofax acredita la reclamación…",
            "added_by": "abogado",
        },
    )
    assert ev.status_code == 201, ev.text
    out = ev.json()
    assert out["record_type"] == "other"
    assert out["document_id"] == "doc_se1"
    assert out["chunk_id"] == "chunk_se1"

