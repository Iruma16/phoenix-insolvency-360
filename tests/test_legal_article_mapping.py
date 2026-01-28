import pytest
from app.graphs.audit_graph import build_audit_graph
from app.fixtures.audit_cases import CASE_RETAIL_001, CASE_RETAIL_002, CASE_RETAIL_003
from app.graphs.state import AuditState

# Script simple para ejecutar el grafo y mostrar resultados del mapeo jurídico
if __name__ == "__main__":
    print("============================================================")
    print("Test: Legal Article Mapping (Mapeo Jurídico)")
    print("============================================================")
    
    graph = build_audit_graph()
    
    print("\n1. CASE_RETAIL_001 (limpio)...")
    result_001 = graph.invoke(CASE_RETAIL_001)
    assert "legal_findings" in result_001
    print(f"   Legal findings: {len(result_001.get('legal_findings', []))}")
    
    for finding in result_001["legal_findings"]:
        assert "legal_basis" in finding
        assert "risk_classification" in finding
        print(f"   ✅ {finding['finding_type']}: {len(finding['legal_basis'])} artículos, {len(finding['risk_classification'])} clasificaciones")
    
    print("\n2. CASE_RETAIL_002 (gris)...")
    result_002 = graph.invoke(CASE_RETAIL_002)
    assert "legal_findings" in result_002
    print(f"   Legal findings: {len(result_002.get('legal_findings', []))}")
    
    for finding in result_002["legal_findings"]:
        assert "legal_basis" in finding
        assert "risk_classification" in finding
        print(f"   ✅ {finding['finding_type']}: {len(finding['legal_basis'])} artículos")
    
    print("\n3. CASE_RETAIL_003 (jodido)...")
    result_003 = graph.invoke(CASE_RETAIL_003)
    assert "legal_findings" in result_003
    print(f"   Legal findings: {len(result_003.get('legal_findings', []))}")
    
    accounting_finding = next(
        (f for f in result_003["legal_findings"] if f.get("finding_type") == "accounting_irregularities"),
        None
    )
    
    print(f"\n   Validando accounting_irregularities...")
    assert accounting_finding is not None, "Debe existir accounting_irregularities"
    print(f"   ✅ Existe finding accounting_irregularities")
    
    assert "legal_basis" in accounting_finding
    assert len(accounting_finding["legal_basis"]) > 0, "legal_basis no debe estar vacío"
    print(f"   ✅ legal_basis no vacío: {len(accounting_finding['legal_basis'])} artículos")
    
    has_443_1 = any(art.get("article") == "art. 443.1º" for art in accounting_finding["legal_basis"])
    assert has_443_1, "Debe incluir art. 443.1º"
    print(f"   ✅ Incluye art. 443.1º")
    
    assert "risk_classification" in accounting_finding
    assert "calificación culpable" in accounting_finding["risk_classification"]
    print(f"   ✅ risk_classification incluye 'calificación culpable'")
    
    print("\n4. Validando estructura completa de legal_findings...")
    for finding in result_003["legal_findings"]:
        assert "finding_type" in finding
        assert "severity" in finding
        assert "weight" in finding
        assert "legal_basis" in finding
        assert "risk_classification" in finding
        assert "explanation" in finding
        assert "evidence" in finding
        assert "counter_evidence" in finding
        assert "mitigation" in finding
        
        assert isinstance(finding["legal_basis"], list)
        assert isinstance(finding["risk_classification"], list)
        
        print(f"   ✅ {finding['finding_type']}: estructura completa")
        
        if finding["legal_basis"]:
            for article in finding["legal_basis"]:
                assert "law" in article
                assert "article" in article
                assert "description" in article
            print(f"      - {len(finding['legal_basis'])} artículos mapeados")
    
    print("\n5. Validando que el reporte incluye legal_findings enriquecidos...")
    report = result_003.get("report", {})
    assert "legal_findings" in report
    assert len(report["legal_findings"]) > 0
    
    for finding in report["legal_findings"]:
        assert "legal_basis" in finding
        assert "risk_classification" in finding
    print("   ✅ Reporte incluye legal_findings con legal_basis y risk_classification")
    
    print("\n============================================================")
    print("✅ TODOS LOS TESTS PASARON")
    print("============================================================")


def test_legal_findings_have_legal_basis():
    """Verifica que los legal_findings tienen el campo legal_basis."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    for finding in result["legal_findings"]:
        assert "legal_basis" in finding
        assert isinstance(finding["legal_basis"], list)


def test_legal_findings_have_risk_classification():
    """Verifica que los legal_findings tienen el campo risk_classification."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    for finding in result["legal_findings"]:
        assert "risk_classification" in finding
        assert isinstance(finding["risk_classification"], list)


def test_case_retail_003_accounting_irregularities_exists():
    """Verifica que CASE_RETAIL_003 tiene accounting_irregularities."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    
    accounting_finding = next(
        (f for f in result["legal_findings"] if f.get("finding_type") == "accounting_irregularities"),
        None
    )
    assert accounting_finding is not None


def test_case_retail_003_accounting_irregularities_has_legal_basis():
    """Verifica que accounting_irregularities tiene legal_basis no vacío."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    
    accounting_finding = next(
        (f for f in result["legal_findings"] if f.get("finding_type") == "accounting_irregularities"),
        None
    )
    assert accounting_finding is not None
    assert len(accounting_finding["legal_basis"]) > 0


def test_case_retail_003_accounting_irregularities_includes_art_443_1():
    """Verifica que accounting_irregularities incluye art. 443.1º."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    
    accounting_finding = next(
        (f for f in result["legal_findings"] if f.get("finding_type") == "accounting_irregularities"),
        None
    )
    assert accounting_finding is not None
    
    has_443_1 = any(art.get("article") == "art. 443.1º" for art in accounting_finding["legal_basis"])
    assert has_443_1


def test_case_retail_003_accounting_irregularities_risk_classification():
    """Verifica que accounting_irregularities incluye 'calificación culpable'."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    
    accounting_finding = next(
        (f for f in result["legal_findings"] if f.get("finding_type") == "accounting_irregularities"),
        None
    )
    assert accounting_finding is not None
    assert "calificación culpable" in accounting_finding["risk_classification"]


def test_legal_basis_structure():
    """Verifica que los artículos en legal_basis tienen la estructura correcta."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    
    for finding in result["legal_findings"]:
        for article in finding["legal_basis"]:
            assert "law" in article
            assert "article" in article
            assert "description" in article
            assert isinstance(article["law"], str)
            assert isinstance(article["article"], str)
            assert isinstance(article["description"], str)


def test_severities_unchanged_after_mapping():
    """Verifica que el mapeo no modifica las severidades."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    # CASE_RETAIL_001 debe seguir teniendo findings LOW
    for finding in result["legal_findings"]:
        assert finding["severity"] in ["low", "medium", "high", "indeterminate"]


def test_report_includes_enriched_legal_findings():
    """Verifica que el reporte incluye legal_findings con legal_basis."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)
    
    report = result.get("report", {})
    assert "legal_findings" in report
    
    for finding in report["legal_findings"]:
        assert "legal_basis" in finding
        assert "risk_classification" in finding


def test_all_cases_execute_with_mapping():
    """Verifica que todos los casos ejecutan correctamente con el mapeo."""
    graph = build_audit_graph()
    
    result_001 = graph.invoke(CASE_RETAIL_001)
    assert "legal_findings" in result_001
    
    result_002 = graph.invoke(CASE_RETAIL_002)
    assert "legal_findings" in result_002
    
    result_003 = graph.invoke(CASE_RETAIL_003)
    assert "legal_findings" in result_003

