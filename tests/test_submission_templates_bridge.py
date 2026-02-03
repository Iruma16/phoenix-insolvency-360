import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.case import Case
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

    case = Case(case_id="case_st1", name="Caso ST1")
    session.add(case)
    session.commit()

    # Seed template
    ensure_template_solicitud_concurso_pj(session)

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


def test_add_and_list_submission_templates(client_with_db):
    # create submission
    r = client_with_db.post(
        "/api/cases/case_st1/submissions",
        json={
            "target": "JUZGADO",
            "reference": "Autos 1/2026",
            "created_by": "abogado",
            "notes": "Alta",
        },
    )
    assert r.status_code == 201, r.text
    sub_id = r.json()["submission_id"]

    add = client_with_db.post(
        f"/api/cases/case_st1/submissions/{sub_id}/templates",
        json={
            "template_code": "JUZ_SOL_CONCURSO_VOLUNTARIO_PJ",
            "actor": "abogado",
            "reason": "Añadir plantilla al acto para preparar outputs.",
        },
    )
    assert add.status_code == 200, add.text
    assert add.json()["template_code"] == "JUZ_SOL_CONCURSO_VOLUNTARIO_PJ"

    lst = client_with_db.get(f"/api/cases/case_st1/submissions/{sub_id}/templates")
    assert lst.status_code == 200, lst.text
    items = lst.json()["items"]
    assert any(it["template_code"] == "JUZ_SOL_CONCURSO_VOLUNTARIO_PJ" for it in items)
