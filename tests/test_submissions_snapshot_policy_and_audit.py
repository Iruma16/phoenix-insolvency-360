from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.case import Case
from app.models.case_central import CaseRecordAudit, CaseRecordEvidence, FormFieldValue
from app.models.document import Document
from app.models.situation import SituationInvoice
from app.services.submission_engine import ensure_template_solicitud_concurso_pj


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

    case = Case(case_id="case_sub1", name="Caso Sub1")
    session.add(case)
    session.commit()

    doc = Document(
        document_id="doc_sub1",
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


def test_snapshot_creates_snapshot_id_and_audit_entries(client_with_db):
    db = getattr(client_with_db, "_db_session")

    # Seed plantilla + valores manuales requeridos para que validate+snapshot pase.
    tpl = ensure_template_solicitud_concurso_pj(db)
    required_manual = {
        "debtor.tax_id": {"text": "B12345678"},
        "debtor.address": {"text": "C/ Ejemplo 1"},
        "insolvency.kind": {"text": "ACTUAL"},
        "insolvency.facts": {"text": "Insolvencia por caída de ingresos."},
        "workers.count": {"number": 3},
        "totals.cash": {"number": 1000.0},
    }
    for k, v in required_manual.items():
        db.add(
            FormFieldValue(
                case_id="case_sub1",
                template_id=tpl.template_id,
                field_key=k,
                value_json=v,
                evidence_id=None,
                justification=None,
                updated_by="abogado",
            )
        )
    db.commit()

    # Seed CAPA2 + evidencia para comprobar evidence_ids
    inv = SituationInvoice(
        logical_id="inv_l1",
        case_id="case_sub1",
        version=1,
        is_current=True,
        created_by="abogado",
        supplier="Proveedor SL",
        supplier_tax_id="B00000000",
        invoice_number="F-1",
        issue_date="2026-01-01",
        due_date="2026-02-01",
        currency="EUR",
        amount_total=100.0,
    )
    db.add(inv)
    db.flush()
    db.add(
        CaseRecordEvidence(
            case_id="case_sub1",
            record_type="invoice",
            record_id=inv.record_id,
            source_type="DOCUMENTO",
            certainty_level="CONSTA",
            justification="Consta en documento aportado.",
            document_id="doc_sub1",
            chunk_id=None,
            page=1,
            excerpt="…extracto…",
            added_by="abogado",
        )
    )
    db.commit()

    # Crear submission (debe auditar SUBMISSION_CREATE)
    r = client_with_db.post(
        "/api/cases/case_sub1/submissions",
        json={
            "target": "JUZGADO",
            "reference": "Autos 1/2026",
            "created_by": "abogado",
            "notes": "Alta",
        },
    )
    assert r.status_code == 201, r.text
    submission_id = r.json()["submission_id"]

    # Snapshot
    s = client_with_db.post(
        f"/api/cases/case_sub1/submissions/{submission_id}/snapshot",
        json={"template_code": tpl.code},
    )
    assert s.status_code == 200, s.text
    body = s.json()
    assert body["snapshot_id"]
    assert body["created_items"] >= 1

    # Auditoría: debe existir SUBMISSION_CREATE y SNAPSHOT_CREATE
    actions = [
        x[0]
        for x in db.query(CaseRecordAudit.action)
        .filter(CaseRecordAudit.case_id == "case_sub1")
        .all()
    ]
    assert "SUBMISSION_CREATE" in actions
    assert "SNAPSHOT_CREATE" in actions
