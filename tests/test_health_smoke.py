import pytest
from fastapi.testclient import TestClient


@pytest.mark.smoke
def test_api_health_smoke():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "healthy"
