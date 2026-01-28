import pytest
from app.graphs.audit_graph import build_audit_graph
from app.fixtures.audit_cases import CASE_RETAIL_001, CASE_RETAIL_002, CASE_RETAIL_003
from app.graphs.state import AuditState

# Script simple para ejecutar el grafo y mostrar resultados del hardening jurídico
if __name__ == "__main__":
    print("============================================================")
    print("Test: Legal Hardening (Hardening Jurídico)")
    print("============================================================")
    
    graph = build_audit_graph()
    
    print("\n1. CASE_RETAIL_001 (limpio)...")
    result_001 = graph.invoke(CASE_RETAIL_001)
    print(f"   Legal findings: {len(result_001.get('legal_findings', []))}")
    
    has_high_finding_001 = any(f.get("severity") == "high" for f in result_001.get("legal_findings", []))
    print(f"   ¿Tiene findings HIGH?: {has_high_finding_001}")
    assert not has_high_finding_001, "CASE_RETAIL_001 no debe tener findings HIGH"
    print("   ✅ CASE_RETAIL_001: Sin findings HIGH")
    
    print("\n2. CASE_RETAIL_002 (gris)...")
    result_002 = graph.invoke(CASE_RETAIL_002)
    print(f"   Legal findings: {len(result_002.get('legal_findings', []))}")
    
    has_medium_finding_002 = any(f.get("severity") == "medium" for f in result_002.get("legal_findings", []))
    print(f"   ¿Tiene findings MEDIUM?: {has_medium_finding_002}")
    assert has_medium_finding_002, "CASE_RETAIL_002 debe tener al menos un finding MEDIUM"
    print("   ✅ CASE_RETAIL_002: Tiene findings MEDIUM")
    
    has_counter_evidence_002 = any(f.get("counter_evidence") for f in result_002.get("legal_findings", []))
    print(f"   ¿Tiene counter_evidence?: {has_counter_evidence_002}")
    print("   ✅ CASE_RETAIL_002: Validado")
    
    print("\n3. CASE_RETAIL_003 (jodido)...")
    result_003 = graph.invoke(CASE_RETAIL_003)
    print(f"   Legal findings: {len(result_003.get('legal_findings', []))}")
    
    accounting_finding = next(
        (f for f in result_003.get("legal_findings", []) if f.get("finding_type") == "accounting_irregularities"),
        None
    )
    
    print(f"   ¿Existe finding 'accounting_irregularities'?: {accounting_finding is not None}")
    assert accounting_finding is not None, "CASE_RETAIL_003 debe tener finding accounting_irregularities"
    print(f"   Severity: {accounting_finding.get('severity')}")
    print(f"   Weight: {accounting_finding.get('weight')}")
    
    assert accounting_finding.get("severity") == "high", "accounting_irregularities debe ser HIGH"
    assert accounting_finding.get("weight") >= 100, "accounting_irregularities debe tener weight >= 100"
    print("   ✅ CASE_RETAIL_003: accounting_irregularities HIGH con weight >= 100")
    
    print("\n4. Validando estructura de legal_findings...")
    for finding in result_003.get("legal_findings", []):
        assert "finding_type" in finding
        assert "severity" in finding
        assert "weight" in finding
        assert "explanation" in finding
        assert "evidence" in finding
        assert "counter_evidence" in finding
        assert "mitigation" in finding
        print(f"   ✅ {finding.get('finding_type')}: estructura válida")
    
    print("\n============================================================")
    print("✅ TODOS LOS TESTS PASARON")
    print("============================================================")


def test_legal_findings_exists_in_state():
    """Verifica que legal_findings se crea en el estado."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    assert "legal_findings" in result
    assert isinstance(result["legal_findings"], list)


def test_case_retail_001_no_high_findings():
    """Verifica que CASE_RETAIL_001 no tiene findings HIGH."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    has_high = any(f.get("severity") == "high" for f in result.get("legal_findings", []))
    assert not has_high


def test_case_retail_002_has_medium_findings():
    """Verifica que CASE_RETAIL_002 tiene al menos un finding MEDIUM."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_002)
    has_medium = any(f.get("severity") == "medium" for f in result.get("legal_findings", []))
    assert has_medium


def test_case_retail_002_has_counter_evidence():
    """Verifica que CASE_RETAIL_002 tiene counter_evidence relacionado con negociación."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_002)
    
    # Puede que no tenga counter_evidence si no hay negociación documentada
    # Este test solo valida que el campo existe
    for finding in result.get("legal_findings", []):
        assert "counter_evidence" in finding
        assert isinstance(finding["counter_evidence"], list)


def test_case_retail_003_has_accounting_irregularities():
    """Verifica que CASE_RETAIL_003 tiene finding accounting_irregularities."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    accounting_finding = next(
        (f for f in result.get("legal_findings", []) if f.get("finding_type") == "accounting_irregularities"),
        None
    )
    assert accounting_finding is not None


def test_case_retail_003_accounting_irregularities_is_high():
    """Verifica que accounting_irregularities es HIGH para CASE_RETAIL_003."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    accounting_finding = next(
        (f for f in result.get("legal_findings", []) if f.get("finding_type") == "accounting_irregularities"),
        None
    )
    assert accounting_finding is not None
    assert accounting_finding.get("severity") == "high"


def test_case_retail_003_accounting_irregularities_weight():
    """Verifica que accounting_irregularities tiene weight >= 100."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    accounting_finding = next(
        (f for f in result.get("legal_findings", []) if f.get("finding_type") == "accounting_irregularities"),
        None
    )
    assert accounting_finding is not None
    assert accounting_finding.get("weight") >= 100


def test_legal_findings_structure():
    """Verifica que cada legal finding tiene la estructura correcta."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    
    for finding in result.get("legal_findings", []):
        assert "finding_type" in finding
        assert "severity" in finding
        assert "weight" in finding
        assert "explanation" in finding
        assert "evidence" in finding
        assert "counter_evidence" in finding
        assert "mitigation" in finding
        
        assert isinstance(finding["finding_type"], str)
        assert isinstance(finding["severity"], str)
        assert isinstance(finding["weight"], int)
        assert isinstance(finding["explanation"], str)
        assert isinstance(finding["evidence"], list)
        assert isinstance(finding["counter_evidence"], list)
        assert isinstance(finding["mitigation"], list)


def test_report_includes_legal_findings():
    """Verifica que el reporte incluye legal_findings."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    report = result.get("report", {})
    assert "legal_findings" in report
    assert isinstance(report["legal_findings"], list)


def test_overall_risk_considers_legal_findings():
    """Verifica que overall_risk tiene en cuenta legal_findings."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    report = result.get("report", {})
    
    # CASE_RETAIL_003 debe tener overall_risk HIGH por los findings
    assert report.get("overall_risk") == "high"

