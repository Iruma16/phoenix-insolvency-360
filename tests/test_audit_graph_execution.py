"""
Test de integración para validar la ejecución del grafo de auditoría.
"""

from app.fixtures.audit_cases import CASE_RETAIL_001
from app.graphs.audit_graph import build_audit_graph


def test_audit_graph_can_be_built():
    """Test que verifica que el grafo de auditoría se puede construir."""
    graph = build_audit_graph()
    assert graph is not None, "El grafo no se pudo construir"


def test_audit_graph_executes_with_fixture():
    """Test que verifica que el grafo se ejecuta con el fixture CASE_RETAIL_001."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    assert result is not None, "El resultado del grafo es None"
    assert "case_id" in result, "El resultado no contiene la clave 'case_id'"
    assert (
        result["case_id"] == "CASE_RETAIL_001"
    ), f"El case_id esperado es 'CASE_RETAIL_001', pero se obtuvo '{result['case_id']}'"


def test_audit_graph_preserves_state_structure():
    """Test que verifica que el grafo preserva la estructura del estado."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    assert "case_id" in result
    assert "company_profile" in result
    assert "documents" in result
    assert "timeline" in result
    assert "risks" in result
    assert "missing_documents" in result
    assert "notes" in result


def test_audit_graph_preserves_documents():
    """Test que verifica que el grafo preserva los documentos del fixture."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)

    assert (
        len(result["documents"]) == 4
    ), f"Se esperaban 4 documentos, se obtuvieron {len(result['documents'])}"


if __name__ == "__main__":
    print("=" * 70)
    print("Test de integración: Ejecución del grafo de auditoría")
    print("=" * 70)

    try:
        print("\n1. Construyendo grafo...")
        graph = build_audit_graph()
        print("   ✅ Grafo construido exitosamente")

        print("\n2. Ejecutando grafo con CASE_RETAIL_001...")
        result = graph.invoke(CASE_RETAIL_001)
        print("   ✅ Grafo ejecutado exitosamente")

        print("\n3. Validando resultado...")
        assert result is not None
        print("   ✅ Resultado no es None")

        assert "case_id" in result
        print("   ✅ Contiene clave 'case_id'")

        assert result["case_id"] == "CASE_RETAIL_001"
        print(f"   ✅ case_id = '{result['case_id']}'")

        print("\n" + "=" * 70)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        raise
