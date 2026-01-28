"""
Test para validar el grafo de auditoría con CASE_RETAIL_003 (caso jodido/alto riesgo).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.graphs.audit_graph import build_audit_graph
from app.fixtures.audit_cases import CASE_RETAIL_001, CASE_RETAIL_002, CASE_RETAIL_003


def test_case_retail_003_executes():
    """Test que verifica que el grafo se ejecuta con CASE_RETAIL_003."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    
    assert result is not None, "El resultado es None"
    assert result["case_id"] == "CASE_RETAIL_003"


def test_case_retail_003_overall_risk_is_high():
    """Test que verifica que el overall_risk es 'high' para CASE_RETAIL_003."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    
    report = result["report"]
    assert report["overall_risk"] == "high", \
        f"Se esperaba overall_risk 'high', se obtuvo '{report['overall_risk']}'"


def test_case_retail_003_delay_filing_is_high():
    """Test que verifica que delay_filing tiene severity high."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    
    risks = result["risks"]
    delay_filing = next((r for r in risks if r["risk_type"] == "delay_filing"), None)
    
    assert delay_filing is not None, "No se encontró riesgo delay_filing"
    assert delay_filing["severity"] == "high", \
        f"Se esperaba delay_filing 'high', se obtuvo '{delay_filing['severity']}'"


def test_case_retail_003_document_inconsistency_is_high():
    """Test que verifica que document_inconsistency tiene severity high."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    
    risks = result["risks"]
    inconsistency = next((r for r in risks if r["risk_type"] == "document_inconsistency"), None)
    
    assert inconsistency is not None, "No se encontró riesgo document_inconsistency"
    assert inconsistency["severity"] == "high", \
        f"Se esperaba document_inconsistency 'high', se obtuvo '{inconsistency['severity']}'"


def test_case_retail_003_documentation_gap_is_high():
    """Test que verifica que documentation_gap tiene severity high."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    
    risks = result["risks"]
    doc_gap = next((r for r in risks if r["risk_type"] == "documentation_gap"), None)
    
    assert doc_gap is not None, "No se encontró riesgo documentation_gap"
    assert doc_gap["severity"] == "high", \
        f"Se esperaba documentation_gap 'high', se obtuvo '{doc_gap['severity']}'"


def test_case_retail_003_accounting_red_flags_is_high():
    """Test que verifica que accounting_red_flags tiene severity high."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    
    risks = result["risks"]
    red_flags = next((r for r in risks if r["risk_type"] == "accounting_red_flags"), None)
    
    assert red_flags is not None, "No se encontró riesgo accounting_red_flags"
    assert red_flags["severity"] == "high", \
        f"Se esperaba accounting_red_flags 'high', se obtuvo '{red_flags['severity']}'"


def test_regression_case_retail_001_still_low():
    """Test de regresión: CASE_RETAIL_001 sigue siendo low."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    report = result["report"]
    assert report["overall_risk"] == "low", \
        f"REGRESIÓN: CASE_RETAIL_001 cambió de 'low' a '{report['overall_risk']}'"


def test_regression_case_retail_002_still_medium():
    """Test de regresión: CASE_RETAIL_002 sigue siendo medium."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_002)
    
    report = result["report"]
    assert report["overall_risk"] == "medium", \
        f"REGRESIÓN: CASE_RETAIL_002 cambió de 'medium' a '{report['overall_risk']}'"


if __name__ == "__main__":
    print("=" * 70)
    print("Test: CASE_RETAIL_003 (Caso Jodido / Alto Riesgo)")
    print("=" * 70)
    
    try:
        print("\n1. Ejecutando grafo con CASE_RETAIL_003...")
        graph = build_audit_graph()
        result = graph.invoke(CASE_RETAIL_003)
        print(f"   ✅ Grafo ejecutado para caso {result['case_id']}")
        
        print("\n2. Timeline generado:")
        for i, event in enumerate(result["timeline"], 1):
            print(f"   {i}. {event['date']}: {event['description']}")
        
        print("\n3. Riesgos detectados:")
        for i, risk in enumerate(result["risks"], 1):
            print(f"   {i}. {risk['risk_type']} [{risk['severity'].upper()}]")
            print(f"      {risk['explanation']}")
        
        print("\n4. Reporte generado:")
        report = result["report"]
        print(f"   Overall Risk: {report['overall_risk'].upper()}")
        print(f"\n   Next Steps:")
        for i, step in enumerate(report['next_steps'], 1):
            print(f"   {i}. {step}")
        
        print("\n5. Validando caso jodido (todos HIGH)...")
        assert report["overall_risk"] == "high"
        print("   ✅ Overall risk es 'high'")
        
        for risk_type in ["delay_filing", "document_inconsistency", "documentation_gap", "accounting_red_flags"]:
            risk = next((r for r in result["risks"] if r["risk_type"] == risk_type), None)
            assert risk and risk["severity"] == "high", f"Expected {risk_type} 'high'"
            print(f"   ✅ {risk_type} es 'high'")
        
        print("\n6. Tests de regresión...")
        result_001 = graph.invoke(CASE_RETAIL_001)
        assert result_001["report"]["overall_risk"] == "low"
        print("   ✅ CASE_RETAIL_001 sigue siendo 'low'")
        
        result_002 = graph.invoke(CASE_RETAIL_002)
        assert result_002["report"]["overall_risk"] == "medium"
        print("   ✅ CASE_RETAIL_002 sigue siendo 'medium'")
        
        print("\n" + "=" * 70)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

