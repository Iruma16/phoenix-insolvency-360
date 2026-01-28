"""
Test para validar el grafo de auditoría con CASE_RETAIL_002 (caso gris).
"""

from app.fixtures.audit_cases import CASE_RETAIL_002
from app.graphs.audit_graph import build_audit_graph


def test_case_retail_002_executes():
    """Test que verifica que el grafo se ejecuta con CASE_RETAIL_002."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_002)

    assert result is not None, "El resultado es None"
    assert result["case_id"] == "CASE_RETAIL_002"


def test_case_retail_002_has_report():
    """Test que verifica que se genera reporte para CASE_RETAIL_002."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_002)

    assert "report" in result, "No se generó reporte"
    assert result["report"] is not None, "El reporte es None"


def test_case_retail_002_overall_risk_is_medium():
    """Test que verifica que el overall_risk es 'medium' para CASE_RETAIL_002."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_002)

    report = result["report"]
    assert (
        report["overall_risk"] == "medium"
    ), f"Se esperaba overall_risk 'medium', se obtuvo '{report['overall_risk']}'"


def test_case_retail_002_has_delay_filing_medium():
    """Test que verifica que existe riesgo delay_filing con severity medium."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_002)

    risks = result["risks"]
    delay_filing_risk = next((r for r in risks if r["risk_type"] == "delay_filing"), None)

    assert delay_filing_risk is not None, "No se encontró riesgo delay_filing"
    assert (
        delay_filing_risk["severity"] == "medium"
    ), f"Se esperaba delay_filing con severity 'medium', se obtuvo '{delay_filing_risk['severity']}'"


def test_case_retail_002_has_document_inconsistency_medium():
    """Test que verifica que existe riesgo document_inconsistency con severity medium."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_002)

    risks = result["risks"]
    inconsistency_risk = next(
        (r for r in risks if r["risk_type"] == "document_inconsistency"), None
    )

    assert inconsistency_risk is not None, "No se encontró riesgo document_inconsistency"
    assert (
        inconsistency_risk["severity"] == "medium"
    ), f"Se esperaba document_inconsistency con severity 'medium', se obtuvo '{inconsistency_risk['severity']}'"


def test_case_retail_002_timeline_created():
    """Test que verifica que se crea timeline para CASE_RETAIL_002."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_002)

    assert "timeline" in result
    assert len(result["timeline"]) > 0, "El timeline está vacío"


def test_case_retail_002_risks_detected():
    """Test que verifica que se detectan riesgos en CASE_RETAIL_002."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_002)

    assert "risks" in result
    assert len(result["risks"]) > 0, "No se detectaron riesgos"


if __name__ == "__main__":
    print("=" * 70)
    print("Test: CASE_RETAIL_002 (Caso Gris)")
    print("=" * 70)

    try:
        print("\n1. Ejecutando grafo con CASE_RETAIL_002...")
        graph = build_audit_graph()
        result = graph.invoke(CASE_RETAIL_002)
        print(f"   ✅ Grafo ejecutado para caso {result['case_id']}")

        print("\n2. Timeline generado:")
        for i, event in enumerate(result["timeline"], 1):
            print(f"   {i}. {event['date']}: {event['description']}")

        print("\n3. Riesgos detectados:")
        for i, risk in enumerate(result["risks"], 1):
            print(f"   {i}. {risk['risk_type']} [{risk['severity']}]")
            print(f"      {risk['explanation']}")

        print("\n4. Reporte generado:")
        report = result["report"]
        print(f"   Overall Risk: {report['overall_risk']}")
        print(f"   Timeline Summary: {report['timeline_summary']}")
        print("\n   Next Steps:")
        for i, step in enumerate(report["next_steps"], 1):
            print(f"   {i}. {step}")

        print("\n5. Validando expectativas del caso gris...")
        assert (
            report["overall_risk"] == "medium"
        ), f"Expected overall_risk 'medium', got '{report['overall_risk']}'"
        print("   ✅ Overall risk es 'medium'")

        delay_filing = next((r for r in result["risks"] if r["risk_type"] == "delay_filing"), None)
        assert (
            delay_filing and delay_filing["severity"] == "medium"
        ), f"Expected delay_filing 'medium', got '{delay_filing['severity'] if delay_filing else 'not found'}'"
        print("   ✅ delay_filing es 'medium'")

        inconsistency = next(
            (r for r in result["risks"] if r["risk_type"] == "document_inconsistency"), None
        )
        assert (
            inconsistency and inconsistency["severity"] == "medium"
        ), f"Expected document_inconsistency 'medium', got '{inconsistency['severity'] if inconsistency else 'not found'}'"
        print("   ✅ document_inconsistency es 'medium'")

        print("\n" + "=" * 70)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        raise
