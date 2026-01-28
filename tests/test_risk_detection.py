"""
Test para validar el nodo detect_risks del grafo de auditoría.
"""

from app.fixtures.audit_cases import CASE_RETAIL_001
from app.graphs.audit_graph import build_audit_graph


def test_risks_are_created():
    """Test que verifica que los riesgos se crean en el grafo."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    assert "risks" in result, "El resultado no contiene la clave 'risks'"
    assert result["risks"] is not None, "Los risks son None"


def test_risks_is_not_empty():
    """Test que verifica que se detectan riesgos."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    assert len(result["risks"]) > 0, "No se detectaron riesgos"


def test_risk_structure():
    """Test que verifica que cada riesgo tiene la estructura correcta."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    required_keys = ["risk_type", "severity", "explanation", "evidence"]

    for risk in result["risks"]:
        for key in required_keys:
            assert key in risk, f"Riesgo sin clave '{key}': {risk}"


def test_document_inconsistency_exists():
    """Test que verifica que se detecta el riesgo document_inconsistency."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    risk_types = [risk["risk_type"] for risk in result["risks"]]
    assert (
        "document_inconsistency" in risk_types
    ), f"No se encontró 'document_inconsistency' en los riesgos: {risk_types}"


def test_document_inconsistency_severity_is_low():
    """Test que verifica que document_inconsistency tiene severity 'low' para CASE_RETAIL_001."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    inconsistency_risk = None
    for risk in result["risks"]:
        if risk["risk_type"] == "document_inconsistency":
            inconsistency_risk = risk
            break

    assert inconsistency_risk is not None, "No se encontró el riesgo document_inconsistency"
    assert (
        inconsistency_risk["severity"] == "low"
    ), f"Se esperaba severity 'low', se obtuvo '{inconsistency_risk['severity']}'"


def test_evidence_is_list():
    """Test que verifica que evidence es siempre una lista."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    for risk in result["risks"]:
        assert isinstance(
            risk["evidence"], list
        ), f"Evidence no es lista en riesgo {risk['risk_type']}: {type(risk['evidence'])}"


def test_severity_values_are_valid():
    """Test que verifica que severity tiene valores válidos."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    valid_severities = ["low", "medium", "high", "indeterminate"]

    for risk in result["risks"]:
        assert (
            risk["severity"] in valid_severities
        ), f"Severity inválido '{risk['severity']}' en riesgo {risk['risk_type']}"


def test_all_core_risk_types_detected():
    """Test que verifica que se detectan los 4 tipos de riesgo core."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    expected_risk_types = [
        "delay_filing",
        "document_inconsistency",
        "documentation_gap",
        "accounting_red_flags",
    ]

    detected_types = [risk["risk_type"] for risk in result["risks"]]

    for expected in expected_risk_types:
        assert expected in detected_types, f"Tipo de riesgo esperado '{expected}' no fue detectado"


if __name__ == "__main__":
    print("=" * 70)
    print("Test: Detección de Riesgos")
    print("=" * 70)

    try:
        print("\n1. Construyendo y ejecutando grafo...")
        graph = build_audit_graph()
        result = graph.invoke(CASE_RETAIL_001)
        print("   ✅ Grafo ejecutado exitosamente")

        print("\n2. Validando riesgos detectados...")
        assert "risks" in result
        risks = result["risks"]
        assert len(risks) > 0
        print(f"   ✅ Se detectaron {len(risks)} riesgos")

        print("\n3. Riesgos encontrados:")
        for i, risk in enumerate(risks, 1):
            print(f"\n   {i}. {risk['risk_type'].upper()}")
            print(f"      Severidad: {risk['severity']}")
            print(f"      Explicación: {risk['explanation']}")
            if risk["evidence"]:
                print(f"      Evidencia: {', '.join(risk['evidence'])}")
            else:
                print("      Evidencia: ninguna")

        print("\n4. Validando estructura...")
        required_keys = ["risk_type", "severity", "explanation", "evidence"]
        for risk in risks:
            for key in required_keys:
                assert key in risk
        print("   ✅ Todos los riesgos tienen la estructura correcta")

        print("\n5. Validando riesgo 'document_inconsistency'...")
        inconsistency = next((r for r in risks if r["risk_type"] == "document_inconsistency"), None)
        assert inconsistency is not None
        assert inconsistency["severity"] == "low"
        print("   ✅ document_inconsistency detectado con severity 'low'")

        print("\n6. Validando que evidence es lista...")
        for risk in risks:
            assert isinstance(risk["evidence"], list)
        print("   ✅ Todas las evidencias son listas")

        print("\n" + "=" * 70)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        raise
