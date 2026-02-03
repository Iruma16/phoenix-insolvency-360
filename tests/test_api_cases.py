"""
Tests para la API REST - Gestión de casos.

Valida endpoints:
- POST /cases
- POST /cases/{case_id}/documents
- POST /cases/{case_id}/analyze
"""
import shutil

import pytest
from fastapi.testclient import TestClient

from app.core.variables import DATA
from app.main import app

# Cliente de test
client = TestClient(app)

# Case ID para tests
TEST_CASE_ID = "api_test_case_001"


@pytest.fixture(autouse=True)
def cleanup_test_case():
    """Limpia el caso de test antes y después de cada test."""
    case_dir = DATA / "cases" / TEST_CASE_ID

    # Limpiar antes
    if case_dir.exists():
        shutil.rmtree(case_dir)

    yield

    # Limpiar después
    if case_dir.exists():
        shutil.rmtree(case_dir)


def test_api_root():
    """Test que el endpoint raíz funciona."""
    print("\n[TEST] GET / - Endpoint raíz...")

    response = client.get("/")

    assert response.status_code == 200
    data = response.json()

    assert "service" in data
    assert data["service"] == "Phoenix Legal API"
    assert "version" in data
    assert "endpoints" in data

    print("   ✅ Endpoint raíz operativo")


def test_api_health_check():
    """Test que el health check funciona."""
    print("\n[TEST] GET /health - Health check...")

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"

    print("   ✅ Health check operativo")


def test_create_case():
    """Test creación de caso."""
    print("\n[TEST] POST /cases - Crear caso...")

    response = client.post(
        "/cases",
        json={
            "case_id": TEST_CASE_ID,
            "company_name": "Test Company SL",
            "sector": "Servicios",
            "size": "PYME",
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["case_id"] == TEST_CASE_ID
    assert data["status"] == "created"
    assert "paths" in data

    # Verificar que se creó físicamente
    case_dir = DATA / "cases" / TEST_CASE_ID
    assert case_dir.exists()
    assert (case_dir / "documents").exists()
    assert (case_dir / "reports").exists()
    assert (case_dir / "metadata.json").exists()

    print(f"   ✅ Caso creado: {TEST_CASE_ID}")


def test_create_case_duplicate():
    """Test que no se puede crear un caso duplicado."""
    print("\n[TEST] POST /cases - Caso duplicado...")

    # Crear caso
    client.post("/cases", json={"case_id": TEST_CASE_ID})

    # Intentar crear de nuevo
    response = client.post("/cases", json={"case_id": TEST_CASE_ID})

    assert response.status_code == 409  # Conflict

    print("   ✅ Caso duplicado rechazado correctamente")


def test_upload_document():
    """Test subida de documento."""
    print("\n[TEST] POST /cases/{case_id}/documents - Subir documento...")

    # Crear caso primero
    client.post("/cases", json={"case_id": TEST_CASE_ID})

    # Crear documento de prueba
    test_content = b"Este es un documento de prueba para el caso."

    # Subir documento
    response = client.post(
        f"/cases/{TEST_CASE_ID}/documents",
        files={"file": ("test_document.txt", test_content, "text/plain")},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["case_id"] == TEST_CASE_ID
    assert data["filename"] == "test_document.txt"
    assert data["size"] == len(test_content)

    # Verificar que se guardó físicamente
    doc_path = DATA / "cases" / TEST_CASE_ID / "documents" / "test_document.txt"
    assert doc_path.exists()

    with open(doc_path, "rb") as f:
        assert f.read() == test_content

    print("   ✅ Documento subido correctamente")


def test_upload_document_case_not_exists():
    """Test que no se puede subir documento a caso inexistente."""
    print("\n[TEST] POST /cases/{case_id}/documents - Caso inexistente...")

    response = client.post(
        "/cases/nonexistent_case/documents", files={"file": ("test.txt", b"content", "text/plain")}
    )

    assert response.status_code == 404

    print("   ✅ Upload a caso inexistente rechazado")


def test_analyze_case():
    """Test análisis de caso."""
    print("\n[TEST] POST /cases/{case_id}/analyze - Analizar caso...")

    # Crear caso
    client.post("/cases", json={"case_id": TEST_CASE_ID})

    # Subir documento
    test_doc = """
    BALANCE CONTABLE
    
    Empresa: Test Company SL
    Ejercicio: 2024
    
    Activo total: 100.000 EUR
    Pasivo total: 120.000 EUR
    Patrimonio neto: -20.000 EUR (NEGATIVO)
    
    La empresa presenta insolvencia actual.
    """

    client.post(
        f"/cases/{TEST_CASE_ID}/documents",
        files={"file": ("balance.txt", test_doc.encode(), "text/plain")},
    )

    # Analizar
    response = client.post(f"/cases/{TEST_CASE_ID}/analyze")

    assert response.status_code == 200
    data = response.json()

    assert data["case_id"] == TEST_CASE_ID
    assert data["status"] == "completed"
    assert "overall_risk" in data
    assert "risks_count" in data
    assert "legal_findings_count" in data

    print("   ✅ Análisis completado:")
    print(f"      - Riesgo global: {data['overall_risk']}")
    print(f"      - Riesgos: {data['risks_count']}")
    print(f"      - Findings: {data['legal_findings_count']}")


def test_analyze_case_without_documents():
    """Test que no se puede analizar caso sin documentos."""
    print("\n[TEST] POST /cases/{case_id}/analyze - Sin documentos...")

    # Crear caso sin documentos
    client.post("/cases", json={"case_id": TEST_CASE_ID})

    # Intentar analizar
    response = client.post(f"/cases/{TEST_CASE_ID}/analyze")

    assert response.status_code == 400  # Bad Request

    print("   ✅ Análisis sin documentos rechazado")


def test_analyze_case_not_exists():
    """Test que no se puede analizar caso inexistente."""
    print("\n[TEST] POST /cases/{case_id}/analyze - Caso inexistente...")

    response = client.post("/cases/nonexistent_case/analyze")

    assert response.status_code == 404

    print("   ✅ Análisis de caso inexistente rechazado")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
