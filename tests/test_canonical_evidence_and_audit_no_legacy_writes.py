import pytest
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.case import Case
from app.models.case_central import CaseRecordAudit, CaseRecordEvidence
from app.models.document import Document
from app.models.situation import SituationAuditLog, SituationEvidence


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

    case = Case(case_id="case_can_1", name="Caso Canon 1")
    session.add(case)
    session.commit()

    doc = Document(
        document_id="doc_can_1",
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


def test_capa2_writes_canonical_evidence_and_audit_only(client_with_db):
    db = getattr(client_with_db, "_db_session")

    # Crear una factura con evidencia vía CAPA2
    r = client_with_db.post(
        "/api/cases/case_can_1/situation/invoices",
        json={
            "created_by": "abogado",
            "reason": "Alta con evidencia canónica",
            "evidence": [{"document_id": "doc_can_1", "page": 1, "note": "Consta en documento aportado."}],
            "supplier": "Proveedor SL",
            "amount_total": 100.0,
            "status": "pendiente",
        },
    )
    assert r.status_code == 200, r.text
    record_id = r.json()["record_id"]
    logical_id = r.json()["logical_id"]

    # Evidencia listada desde case_record_evidence
    ev = client_with_db.get(f"/api/cases/case_can_1/situation/INVOICE/{record_id}/evidence")
    assert ev.status_code == 200, ev.text
    items = ev.json()["items"]
    assert len(items) == 1
    assert items[0]["document_id"] == "doc_can_1"
    assert db.query(CaseRecordEvidence).count() == 1

    # Auditoría canónica debe existir (CREATE)
    au = client_with_db.get(f"/api/cases/case_can_1/situation/INVOICE/{logical_id}/audit")
    assert au.status_code == 200, au.text
    actions = [x["action"] for x in au.json()["items"]]
    assert "CREATE" in actions
    assert db.query(CaseRecordAudit).count() >= 1

    # Legacy no debe recibir writes
    assert db.query(SituationEvidence).count() == 0
    assert db.query(SituationAuditLog).count() == 0

