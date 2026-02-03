from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.case import Case
from app.models.case_central import Template, TemplateField
from app.models.document import Document


@pytest.fixture
def client_with_db():
    # Importar modelos ANTES de create_all para que sus tablas existan en metadata.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    case = Case(case_id="case_ff1", name="Caso FF1")
    session.add(case)

    doc = Document(
        document_id="doc_ff1",
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

    template = Template(
        template_id="tpl_ff1",
        code="TPL_FF1",
        target="JUZGADO",
        version="v1",
        name="Plantilla FF1",
        is_active=True,
    )
    session.add(template)
    session.flush()

    field = TemplateField(
        field_id="fld_ff1",
        template_id=template.template_id,
        field_key="procedure_ref",
        label="Número de procedimiento",
        data_type="string",
        required=False,
    )
    session.add(field)
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


def test_link_targets_form_field_returns_template_field_ids(client_with_db):
    r = client_with_db.get(
        "/api/cases/case_ff1/situation/link-targets",
        params={"record_type": "form_field", "q": "procedure", "page": 1, "page_size": 20},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] >= 1
    assert any(it["record_id"] == "fld_ff1" for it in data["items"])


def test_case_evidence_accepts_form_field_record_type(client_with_db):
    payload = {
        "record_type": "form_field",
        "record_id": "fld_ff1",
        "source_type": "DOCUMENTO",
        "certainty_level": "CONSTA",
        "justification": "Consta en documento aportado por el cliente.",
        "document_id": "doc_ff1",
        "chunk_id": None,
        "page": 1,
        "excerpt": "…extracto…",
        "added_by": "abogado",
    }
    r = client_with_db.post("/api/cases/case_ff1/evidence", json=payload)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["record_type"] == "form_field"
    assert out["record_id"] == "fld_ff1"
