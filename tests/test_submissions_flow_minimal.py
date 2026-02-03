import os
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
def client_with_db(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed mínimo: caso + documento
    case = Case(case_id="case_sub_1", name="Deudor PJ SL")
    session.add(case)
    session.commit()

    doc = Document(
        document_id="doc_sub_1",
        case_id=case.case_id,
        filename="evidencia.pdf",
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
        storage_path=str(tmp_path / "evidencia.pdf"),
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
    old = os.environ.get("PHOENIX_OUTPUT_DIR")
    os.environ["PHOENIX_OUTPUT_DIR"] = str(tmp_path / "outputs")
    try:
        yield TestClient(app)
    finally:
        if old is None:
            os.environ.pop("PHOENIX_OUTPUT_DIR", None)
        else:
            os.environ["PHOENIX_OUTPUT_DIR"] = old
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_submissions_end_to_end_minimal(client_with_db):
    # 1) Crear submission
    r = client_with_db.post(
        "/api/cases/case_sub_1/submissions",
        json={"target": "JUZGADO", "reference": None, "created_by": "abogado", "notes": None},
    )
    assert r.status_code == 201, r.text
    submission_id = r.json()["submission_id"]

    template_code = "JUZ_SOL_CONCURSO_VOLUNTARIO_PJ"

    # 2) Guardar valores manuales requeridos
    r = client_with_db.put(
        f"/api/cases/case_sub_1/templates/{template_code}/values",
        json={
            "values": [
                {
                    "field_key": "debtor.tax_id",
                    "value_json": {"text": "B12345678"},
                    "updated_by": "abogado",
                },
                {
                    "field_key": "debtor.address",
                    "value_json": {"text": "C/ Mayor 1, Madrid"},
                    "updated_by": "abogado",
                },
                {
                    "field_key": "insolvency.kind",
                    "value_json": {"text": "ACTUAL"},
                    "updated_by": "abogado",
                },
                {
                    "field_key": "insolvency.facts",
                    "value_json": {"text": "Impagos reiterados y falta de liquidez."},
                    "updated_by": "abogado",
                },
                {
                    "field_key": "workers.count",
                    "value_json": {"number": 3},
                    "updated_by": "abogado",
                },
                {
                    "field_key": "totals.cash",
                    "value_json": {"number": 1200.0},
                    "updated_by": "abogado",
                },
            ]
        },
    )
    assert r.status_code == 200, r.text

    # 3) Validar OK
    r = client_with_db.post(
        f"/api/cases/case_sub_1/submissions/{submission_id}/validate",
        json={"template_code": template_code},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True, r.json()

    # 4) Snapshot
    r = client_with_db.post(
        f"/api/cases/case_sub_1/submissions/{submission_id}/snapshot",
        json={"template_code": template_code},
    )
    assert r.status_code == 200, r.text
    assert r.json()["created_items"] >= 1

    # 5) Generar DOCX
    r = client_with_db.post(
        f"/api/cases/case_sub_1/submissions/{submission_id}/generate",
        json={"template_code": template_code},
    )
    assert r.status_code == 200, r.text
    gen = r.json()["generated"]
    assert gen["format"] == "DOCX"
    assert len(gen["content_hash"]) == 64

    # 6) Descargar
    r = client_with_db.get(
        f"/api/cases/case_sub_1/submissions/{submission_id}/generated/{gen['generated_id']}/download"
    )
    assert r.status_code == 200, r.text
    assert len(r.content) > 1000
