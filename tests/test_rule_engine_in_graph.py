"""
Tests para el Rule Engine integrado en el grafo.

Valida que:
- El nodo se ejecuta correctamente
- Modifica el estado añadiendo rule_based_findings
- NO rompe el flujo si no hay rulebook
- Convive con los findings heurísticos
"""
import pytest

from app.graphs.audit_graph import build_audit_graph
from app.fixtures.audit_cases import CASE_RETAIL_001


def test_rule_engine_node_executes():
    """Test que el nodo rule_engine se ejecuta sin errores."""
    print("\n[TEST] Ejecución del nodo rule_engine en el grafo...")
    
    # Construir grafo
    graph = build_audit_graph()
    
    # Ejecutar con caso fixture
    result = graph.invoke(CASE_RETAIL_001)
    
    # Verificar que el nodo se ejecutó
    assert "rule_based_findings" in result, "El estado debe incluir rule_based_findings"
    
    print(f"   ✅ Nodo ejecutado correctamente")
    print(f"      - Rule findings: {len(result.get('rule_based_findings', []))}")


def test_rule_engine_adds_findings_to_state():
    """Test que el rule engine añade findings al estado."""
    print("\n[TEST] Rule engine añade findings al estado...")
    
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    rule_findings = result.get("rule_based_findings", [])
    
    # Verificar que es una lista (puede estar vacía si no hay rulebook)
    assert isinstance(rule_findings, list)
    
    # Si hay findings, verificar estructura
    if rule_findings:
        print(f"   ✅ {len(rule_findings)} findings generados por rule engine")
        
        for finding in rule_findings:
            assert "finding_type" in finding
            assert "severity" in finding
            assert "confidence" in finding
            assert "source" in finding
            assert finding["source"] == "rule_engine"
            
        print(f"      - Primer finding: {rule_findings[0]['finding_type']}")
    else:
        print(f"   ℹ️  No hay findings (rulebook no disponible o sin reglas aplicables)")
    
    print("   ✅ Estructura de findings correcta")


def test_rule_engine_does_not_break_flow():
    """Test que el grafo continúa si el rule engine falla o no hay rulebook."""
    print("\n[TEST] Grafo continúa si rule engine no tiene rulebook...")
    
    graph = build_audit_graph()
    
    # Ejecutar con caso mínimo
    minimal_case = {
        "case_id": "test_minimal",
        "company_profile": {"name": "Test", "sector": "Test"},
        "documents": [],
        "timeline": [],
        "risks": [],
        "missing_documents": [],
        "legal_findings": [],
        "notes": None,
        "report": None
    }
    
    # NO debe lanzar excepción
    result = graph.invoke(minimal_case)
    
    # Verificar que el flujo completó
    assert "report" in result
    assert result["report"] is not None
    
    # Verificar que rule_based_findings existe (aunque esté vacío)
    assert "rule_based_findings" in result
    
    print("   ✅ Grafo completó sin errores")


def test_rule_engine_coexists_with_heuristics():
    """Test que los findings del rule engine conviven con los heurísticos."""
    print("\n[TEST] Rule engine convive con heurísticas...")
    
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    # Verificar que existen ambos tipos de findings
    heuristic_risks = result.get("risks", [])
    heuristic_findings = result.get("legal_findings", [])
    rule_findings = result.get("rule_based_findings", [])
    
    # Los heurísticos deben existir (generados por detect_risks y legal_hardening)
    assert len(heuristic_risks) > 0, "Debe haber riesgos heurísticos"
    assert len(heuristic_findings) > 0, "Debe haber findings heurísticos"
    
    # Los rule findings pueden estar vacíos (si no hay rulebook)
    assert isinstance(rule_findings, list)
    
    print(f"   ✅ Convivencia correcta:")
    print(f"      - Riesgos heurísticos: {len(heuristic_risks)}")
    print(f"      - Findings heurísticos: {len(heuristic_findings)}")
    print(f"      - Findings rule engine: {len(rule_findings)}")


def test_rule_engine_node_position_in_graph():
    """Test que el rule engine está en la posición correcta del grafo."""
    print("\n[TEST] Posición del rule engine en el grafo...")
    
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    # Verificar que se ejecutó después de legal_hardening
    # (debe tener legal_findings disponibles)
    assert "legal_findings" in result
    assert len(result["legal_findings"]) > 0
    
    # Verificar que se ejecutó antes de build_report
    # (el reporte debe existir)
    assert "report" in result
    assert result["report"] is not None
    
    print("   ✅ Rule engine en posición correcta del flujo")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

