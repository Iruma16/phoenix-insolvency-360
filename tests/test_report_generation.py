"""
Test para validar el nodo build_report del grafo de auditoría.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.graphs.audit_graph import build_audit_graph
from app.fixtures.audit_cases import CASE_RETAIL_001


def test_report_is_created():
    """Test que verifica que el reporte se crea en el grafo."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    assert "report" in result, "El resultado no contiene la clave 'report'"
    assert result["report"] is not None, "El report es None"


def test_report_has_case_id():
    """Test que verifica que el reporte contiene el case_id correcto."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    report = result["report"]
    assert "case_id" in report, "El report no contiene 'case_id'"
    assert report["case_id"] == "CASE_RETAIL_001", \
        f"Se esperaba case_id 'CASE_RETAIL_001', se obtuvo '{report['case_id']}'"


def test_report_has_overall_risk():
    """Test que verifica que el reporte contiene overall_risk."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    report = result["report"]
    assert "overall_risk" in report, "El report no contiene 'overall_risk'"


def test_overall_risk_is_low_for_case_retail_001():
    """Test que verifica que overall_risk es 'low' para CASE_RETAIL_001."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    report = result["report"]
    assert report["overall_risk"] == "low", \
        f"Se esperaba overall_risk 'low', se obtuvo '{report['overall_risk']}'"


def test_report_has_risk_summary():
    """Test que verifica que el reporte contiene risk_summary."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    report = result["report"]
    assert "risk_summary" in report, "El report no contiene 'risk_summary'"
    assert isinstance(report["risk_summary"], list), "risk_summary no es una lista"


def test_risk_summary_matches_risks_count():
    """Test que verifica que risk_summary tiene el mismo número de elementos que risks."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    risks = result["risks"]
    report = result["report"]
    risk_summary = report["risk_summary"]
    
    assert len(risk_summary) == len(risks), \
        f"Se esperaban {len(risks)} riesgos en risk_summary, se obtuvieron {len(risk_summary)}"


def test_report_has_next_steps():
    """Test que verifica que el reporte contiene next_steps."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    report = result["report"]
    assert "next_steps" in report, "El report no contiene 'next_steps'"
    assert isinstance(report["next_steps"], list), "next_steps no es una lista"


def test_next_steps_is_not_empty():
    """Test que verifica que next_steps contiene recomendaciones."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    report = result["report"]
    assert len(report["next_steps"]) > 0, "next_steps está vacío"


def test_report_has_timeline_summary():
    """Test que verifica que el reporte contiene timeline_summary."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    report = result["report"]
    assert "timeline_summary" in report, "El report no contiene 'timeline_summary'"
    assert isinstance(report["timeline_summary"], str), "timeline_summary no es string"
    assert len(report["timeline_summary"]) > 0, "timeline_summary está vacío"


def test_report_structure():
    """Test que verifica que el reporte tiene la estructura completa esperada."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    report = result["report"]
    required_keys = ["case_id", "overall_risk", "timeline_summary", "risk_summary", "next_steps"]
    
    for key in required_keys:
        assert key in report, f"El report no contiene la clave requerida '{key}'"


if __name__ == "__main__":
    print("=" * 70)
    print("Test: Generación de Reporte")
    print("=" * 70)
    
    try:
        print("\n1. Construyendo y ejecutando grafo...")
        graph = build_audit_graph()
        result = graph.invoke(CASE_RETAIL_001)
        print("   ✅ Grafo ejecutado exitosamente")
        
        print("\n2. Validando reporte...")
        assert "report" in result
        report = result["report"]
        print("   ✅ Reporte generado")
        
        print("\n3. Contenido del reporte:")
        print(f"\n   Case ID: {report['case_id']}")
        print(f"   Overall Risk: {report['overall_risk']}")
        
        print(f"\n   Timeline Summary:")
        print(f"   {report['timeline_summary']}")
        
        print(f"\n   Risk Summary ({len(report['risk_summary'])} riesgos):")
        for i, risk in enumerate(report['risk_summary'], 1):
            print(f"      {i}. {risk['risk_type']} [{risk['severity']}]")
            print(f"         {risk['explanation']}")
        
        print(f"\n   Next Steps:")
        for i, step in enumerate(report['next_steps'], 1):
            print(f"      {i}. {step}")
        
        print("\n4. Validando estructura...")
        required_keys = ["case_id", "overall_risk", "timeline_summary", "risk_summary", "next_steps"]
        for key in required_keys:
            assert key in report
        print("   ✅ Reporte tiene la estructura completa")
        
        print("\n5. Validando valores...")
        assert report["case_id"] == "CASE_RETAIL_001"
        assert report["overall_risk"] == "low"
        assert len(report["risk_summary"]) == len(result["risks"])
        assert len(report["next_steps"]) > 0
        print("   ✅ Todos los valores son correctos")
        
        print("\n" + "=" * 70)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

