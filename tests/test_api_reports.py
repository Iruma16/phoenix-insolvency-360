"""
Tests para la API REST - Gestión de reportes.

Valida endpoint:
- GET /cases/{case_id}/reports/latest
"""
import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import shutil

from app.api.public import app
from app.core.variables import DATA


# Cliente de test
client = TestClient(app)

# Case ID para tests
TEST_CASE_ID = "api_test_reports_001"


@pytest.fixture(autouse=True)
def cleanup_test_case():
    """Limpia el caso de test antes y después de cada test."""
    case_dir = DATA / "cases" / TEST_CASE_ID
    
    if case_dir.exists():
        shutil.rmtree(case_dir)
    
    yield
    
    if case_dir.exists():
        shutil.rmtree(case_dir)


def test_download_latest_report():
    """Test descarga del último reporte PDF."""
    print("\n[TEST] GET /cases/{case_id}/reports/latest - Descargar PDF...")
    
    # Crear caso
    client.post("/cases", json={"case_id": TEST_CASE_ID})
    
    # Subir documento
    test_doc = "Documento de prueba para generar reporte."
    client.post(
        f"/cases/{TEST_CASE_ID}/documents",
        files={"file": ("doc.txt", test_doc.encode(), "text/plain")}
    )
    
    # Analizar (genera PDF)
    analyze_response = client.post(f"/cases/{TEST_CASE_ID}/analyze")
    assert analyze_response.status_code == 200
    
    # Descargar PDF
    response = client.get(f"/cases/{TEST_CASE_ID}/reports/latest")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    
    # Verificar que es un PDF válido
    content = response.content
    assert content.startswith(b"%PDF"), "El contenido debe ser un PDF válido"
    assert len(content) > 1000, "El PDF debe tener tamaño razonable"
    
    print(f"   ✅ PDF descargado correctamente")
    print(f"      - Tamaño: {len(content):,} bytes")


def test_download_report_case_not_exists():
    """Test que no se puede descargar reporte de caso inexistente."""
    print("\n[TEST] GET /cases/{case_id}/reports/latest - Caso inexistente...")
    
    response = client.get("/cases/nonexistent_case/reports/latest")
    
    assert response.status_code == 404
    
    print("   ✅ Descarga de caso inexistente rechazada")


def test_download_report_no_reports():
    """Test que no se puede descargar reporte si no se ha analizado."""
    print("\n[TEST] GET /cases/{case_id}/reports/latest - Sin reportes...")
    
    # Crear caso sin analizar
    client.post("/cases", json={"case_id": TEST_CASE_ID})
    
    # Intentar descargar
    response = client.get(f"/cases/{TEST_CASE_ID}/reports/latest")
    
    assert response.status_code == 404
    
    print("   ✅ Descarga sin reportes rechazada")


def test_full_workflow_create_upload_analyze_download():
    """Test del flujo completo: crear → subir → analizar → descargar."""
    print("\n[TEST] Flujo completo API...")
    
    # 1. Crear caso
    print("   1. Creando caso...")
    response = client.post(
        "/cases",
        json={
            "case_id": TEST_CASE_ID,
            "company_name": "Test Workflow SL"
        }
    )
    assert response.status_code == 201
    
    # 2. Subir documentos
    print("   2. Subiendo documentos...")
    doc1 = "Balance contable con patrimonio neto negativo."
    doc2 = "Acta de junta reconociendo insolvencia."
    
    client.post(
        f"/cases/{TEST_CASE_ID}/documents",
        files={"file": ("balance.txt", doc1.encode(), "text/plain")}
    )
    client.post(
        f"/cases/{TEST_CASE_ID}/documents",
        files={"file": ("acta.txt", doc2.encode(), "text/plain")}
    )
    
    # 3. Analizar
    print("   3. Analizando caso...")
    response = client.post(f"/cases/{TEST_CASE_ID}/analyze")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "completed"
    
    # 4. Descargar PDF
    print("   4. Descargando PDF...")
    response = client.get(f"/cases/{TEST_CASE_ID}/reports/latest")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    
    print("   ✅ Flujo completo ejecutado correctamente")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

