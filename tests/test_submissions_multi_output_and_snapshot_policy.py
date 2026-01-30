import os
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
from app.models.case_central import CaseRecordAudit
from app.services.submission_engine import (
    TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ,
    TEMPLATE_CODE_MEMORIA_ECONOMICA_JURIDICA,
    ensure_template_solicitud_concurso_pj,
    ensure_template_memoria_economica_juridica,
)
from app.models.case_central import FormFieldValue


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    # Outputs en tmp
    monkeypatch.setenv("PHOENIX_OUTPUT_DIR", str(tmp_path))

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    case = Case(case_id="case_submo1", name="Caso Sub MultiOutput")
    session.add(case)
    session.commit()

    # Documento dummy para evidencia de fields (si se usa)
    doc = Document(
        document_id="doc_submo1",
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

    # Seed plantillas
    tpl1 = ensure_template_solicitud_concurso_pj(session)
    tpl2 = ensure_template_memoria_economica_juridica(session)

    # Seed valores manuales mínimos para plantilla PJ (required)
    required_manual = {
        "debtor.tax_id": {"text": "B12345678"},
        "debtor.address": {"text": "C/ Ejemplo 1"},
        "insolvency.kind": {"text": "ACTUAL"},
        "insolvency.facts": {"text": "Insolvencia por caída de ingresos."},
        "workers.count": {"number": 3},
        "totals.cash": {"number": 1000.0},
    }
    for k, v in required_manual.items():
        session.add(
            FormFieldValue(
                case_id=case.case_id,
                template_id=tpl1.template_id,
                field_key=k,
                value_json=v,
                evidence_id=None,
                justification="Justificación suficientemente larga para cumplir reglas." if v.get("text") == "NO CONSTA" else None,
                updated_by="abogado",
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
        setattr(c, "_db_session", session)
        yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_multi_output_generate_two_templates(client_with_db):
    db = getattr(client_with_db, "_db_session")

    # Crear submission
    r = client_with_db.post(
        "/api/cases/case_submo1/submissions",
        json={"target": "JUZGADO", "reference": "Autos 1/2026", "created_by": "abogado", "notes": "Alta"},
    )
    assert r.status_code == 201, r.text
    sub_id = r.json()["submission_id"]

    # El backend exige LISTO antes de generar: snapshot (válida) pasa BORRADOR -> LISTO.
    s = client_with_db.post(
        f"/api/cases/case_submo1/submissions/{sub_id}/snapshot",
        json={"template_code": TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ},
    )
    assert s.status_code == 200, s.text

    # Generar DOCX para plantilla PJ
    g1 = client_with_db.post(
        f"/api/cases/case_submo1/submissions/{sub_id}/generate",
        json={"template_code": TEMPLATE_CODE_SOLICITUD_CONCURSO_PJ},
    )
    assert g1.status_code == 200, g1.text

    # Generar DOCX para otra plantilla (usa generador genérico)
    g2 = client_with_db.post(
        f"/api/cases/case_submo1/submissions/{sub_id}/generate",
        json={"template_code": TEMPLATE_CODE_MEMORIA_ECONOMICA_JURIDICA},
    )
    assert g2.status_code == 200, g2.text

    # Listar outputs
    out = client_with_db.get(f"/api/cases/case_submo1/submissions/{sub_id}/generated")
    assert out.status_code == 200, out.text
    items = out.json()
    assert len(items) >= 2
    assert any(x["snapshot_id"] for x in items)

    # Auditoría: debe existir OUTPUT_GENERATE al menos 2 veces
    actions = [x[0] for x in db.query(CaseRecordAudit.action).filter(CaseRecordAudit.case_id == "case_submo1").all()]
    assert actions.count("OUTPUT_GENERATE") >= 2

