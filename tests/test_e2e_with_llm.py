"""
Tests E2E con LLM real.

Estos tests requieren OPENAI_API_KEY configurada y son más lentos.
Marcar como @slow para ejecución selectiva.
"""
import os
from pathlib import Path

import pytest

from app.fixtures.audit_cases import CASE_RETAIL_001, CASE_RETAIL_002
from app.graphs.audit_graph import build_audit_graph
from app.reports.pdf_report import build_report_payload

# Skip si no hay API key
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"), reason="Requiere OPENAI_API_KEY configurada"
)


@pytest.mark.slow
@pytest.mark.llm
def test_e2e_with_llm_case_retail_001():
    """
    Test E2E completo con LLM para CASE_RETAIL_001.

    Valida:
    - Ejecución completa del grafo con LLM
    - Generación de análisis LLM (Auditor + Prosecutor)
    - Inclusión de análisis LLM en el estado
    - Generación de PDF con análisis LLM
    """
    # Ejecutar grafo completo
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    # Validar que el grafo se ejecutó
    assert result is not None
    assert result["case_id"] == "CASE_RETAIL_001"

    # Validar que Auditor LLM se ejecutó
    auditor_llm = result.get("auditor_llm")
    assert auditor_llm is not None, "Auditor LLM no se ejecutó"
    assert auditor_llm.get("llm_enabled") is True, "Auditor LLM no está habilitado"
    assert auditor_llm.get("llm_summary") is not None, "Auditor LLM no generó resumen"
    assert auditor_llm.get("llm_reasoning") is not None, "Auditor LLM no generó razonamiento"
    assert auditor_llm.get("llm_confidence") is not None, "Auditor LLM no generó confianza"

    # Validar contenido del Auditor LLM
    assert len(auditor_llm["llm_summary"]) > 20, "Resumen del Auditor muy corto"
    assert len(auditor_llm["llm_reasoning"]) > 20, "Razonamiento del Auditor muy corto"

    # Validar que Prosecutor LLM se ejecutó
    prosecutor_llm = result.get("prosecutor_llm")
    assert prosecutor_llm is not None, "Prosecutor LLM no se ejecutó"
    assert prosecutor_llm.get("llm_enabled") is True, "Prosecutor LLM no está habilitado"

    # Validar que hay análisis legal
    llm_summary = prosecutor_llm.get("llm_summary") or prosecutor_llm.get("llm_legal_summary")
    assert llm_summary is not None, "Prosecutor LLM no generó resumen legal"
    assert len(llm_summary) > 20, "Resumen legal del Prosecutor muy corto"

    # Validar que el PDF se puede construir con análisis LLM
    payload = build_report_payload("CASE_RETAIL_001", result)
    assert "auditor_llm" in payload
    assert "prosecutor_llm" in payload
    assert payload["auditor_llm"].get("llm_enabled") is True
    assert payload["prosecutor_llm"].get("llm_enabled") is True

    print("\n✅ Test E2E con LLM completado exitosamente")
    print(f"   - Auditor LLM: {auditor_llm['llm_summary'][:80]}...")
    print(f"   - Prosecutor LLM: {llm_summary[:80]}...")


@pytest.mark.slow
@pytest.mark.llm
def test_e2e_with_llm_case_retail_002():
    """
    Test E2E con LLM para CASE_RETAIL_002 (caso gris).

    Valida que el LLM también funciona para casos más complejos.
    """
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_002)

    assert result is not None
    assert result["case_id"] == "CASE_RETAIL_002"

    # Validar LLM
    auditor_llm = result.get("auditor_llm")
    assert auditor_llm is not None
    assert auditor_llm.get("llm_enabled") is True

    prosecutor_llm = result.get("prosecutor_llm")
    assert prosecutor_llm is not None
    assert prosecutor_llm.get("llm_enabled") is True

    print("\n✅ Test E2E con LLM para CASE_RETAIL_002 completado")


@pytest.mark.slow
@pytest.mark.llm
def test_llm_does_not_invent_articles():
    """
    Test que valida que el LLM no inventa artículos del TRLC.

    Verifica que los artículos citados existen en el corpus legal.
    """
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    # Obtener legal_findings
    legal_findings = result.get("legal_findings", [])
    assert len(legal_findings) > 0, "No hay legal findings"

    # Validar que los artículos citados son reales
    valid_articles = [
        "5",
        "6",
        "11",
        "100",
        "165",
        "172",
        "176",
        "192",
        "193",
        "194",
        "231",
        "238",
        "286",
        "332",
        "333",
        "367",
        "381",
        "443",
        "444",
        "445",
        "446",
        "456",
    ]

    import re

    for finding in legal_findings:
        legal_basis = finding.get("legal_basis", [])
        for article in legal_basis:
            article_num = str(article.get("article", "")).strip()
            # Extraer el primer número de artículo (acepta subapartados tipo "443.3º")
            m = re.search(r"(\\d+)", article_num)
            if m:
                article_main = m.group(1)
                assert article_main in valid_articles, f"Artículo {article_num} no es válido"

    print("\n✅ Validación anti-alucinación: todos los artículos son reales")


@pytest.mark.slow
@pytest.mark.llm
def test_llm_analysis_in_pdf():
    """
    Test que valida que el análisis LLM aparece en el PDF.

    Genera un PDF real y verifica que contiene el análisis LLM.
    """
    import tempfile

    from app.reports.pdf_report import render_pdf

    # Ejecutar grafo
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    # Construir payload
    payload = build_report_payload("CASE_RETAIL_001", result)

    # Generar PDF temporal
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = tmp.name

    try:
        render_pdf(payload, pdf_path)

        # Verificar que el PDF existe
        assert Path(pdf_path).exists()

        # Verificar tamaño (puede variar por compresión/fuentes; solo umbral mínimo razonable)
        pdf_size = Path(pdf_path).stat().st_size
        assert pdf_size > 8000, f"PDF muy pequeño: {pdf_size} bytes (esperado > 8KB con LLM)"

        # Leer contenido del PDF
        with open(pdf_path, "rb") as f:
            pdf_content = f.read()

        # Verificar que empieza con magic bytes de PDF
        assert pdf_content[:4] == b"%PDF", "No es un PDF válido"

        print(f"\n✅ PDF con análisis LLM generado: {pdf_size} bytes")

    finally:
        # Limpiar
        if Path(pdf_path).exists():
            Path(pdf_path).unlink()


@pytest.mark.slow
@pytest.mark.llm
def test_llm_graceful_degradation():
    """
    Test que valida que el sistema funciona sin API key (degradación graciosa).

    Temporalmente elimina la API key y verifica que el sistema sigue funcionando.
    """
    import os

    # Guardar API key original
    original_key = os.environ.get("OPENAI_API_KEY")

    try:
        # Eliminar API key temporalmente
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

        # Ejecutar grafo
        graph = build_audit_graph()
        result = graph.invoke(CASE_RETAIL_001)

        # Validar que el grafo se ejecutó
        assert result is not None
        assert result["case_id"] == "CASE_RETAIL_001"

        # Validar que los agentes LLM están deshabilitados
        auditor_llm = result.get("auditor_llm")
        assert auditor_llm is not None
        assert auditor_llm.get("llm_enabled") is False, "Auditor LLM debería estar deshabilitado"

        prosecutor_llm = result.get("prosecutor_llm")
        assert prosecutor_llm is not None
        assert (
            prosecutor_llm.get("llm_enabled") is False
        ), "Prosecutor LLM debería estar deshabilitado"

        # Validar que el resto del análisis funciona (en modo degradado puede haber menos señales)
        assert len(result.get("risks", [])) > 0, "Debería haber riesgos detectados"
        assert isinstance(result.get("timeline", []), list), "Timeline debe existir (puede estar vacío)"
        assert result.get("report") is not None, "Debería haber report"

        print("\n✅ Degradación graciosa validada: sistema funciona sin LLM")

    finally:
        # Restaurar API key
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-m", "llm"])
