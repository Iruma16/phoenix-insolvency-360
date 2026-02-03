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
from app.services.submission_engine import (
    TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ,
    ensure_template_solicitud_concurso_pj,
)


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

    case = Case(case_id="case_tpl1", name="Caso Plantillas 1")
    session.add(case)
    session.commit()

    # Documento dummy (por si se requiere evidence_id en algún flujo)
    doc = Document(
        document_id="doc_tpl1",
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
        c = TestClient(app)
        setattr(c, "_db_session", session)
        yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_mapping_endpoint_returns_all_fields_and_no_missing(client_with_db):
    db = getattr(client_with_db, "_db_session")
    tpl = ensure_template_solicitud_concurso_pj(db)
    r = client_with_db.get(f"/api/cases/case_tpl1/templates/{tpl.code}/mapping")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["template_code"] == TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ
    assert isinstance(body["items"], list) and len(body["items"]) > 0
    assert body["missing_mappings"] == []


def test_no_consta_critical_requires_justification_and_maybe_evidence(client_with_db):
    db = getattr(client_with_db, "_db_session")
    tpl = ensure_template_solicitud_concurso_pj(db)

    # debtor.tax_id es critical + evidence_required en la seed
    r = client_with_db.put(
        f"/api/cases/case_tpl1/templates/{tpl.code}/values",
        json={
            "values": [
                {
                    "field_key": "debtor.tax_id",
                    "value_json": {"text": "NO CONSTA"},
                    "updated_by": "abogado",
                    # falta justification y evidence_id
                }
            ]
        },
    )
    assert r.status_code == 422
