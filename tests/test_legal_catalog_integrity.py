import re
from datetime import datetime

import pytest

from app.fixtures.audit_cases import CASE_RETAIL_003
from app.graphs.audit_graph import build_audit_graph
from app.legal.legal_mapping import LEGAL_MAP

# Script simple para ejecutar verificación del catálogo legal
if __name__ == "__main__":
    print("============================================================")
    print("Test: Legal Catalog Integrity (Control de Calidad)")
    print("============================================================")

    print("\n1. Validando estructura de LEGAL_MAP...")
    assert isinstance(LEGAL_MAP, dict), "LEGAL_MAP debe ser un diccionario"
    assert len(LEGAL_MAP) > 0, "LEGAL_MAP no debe estar vacío"
    print(f"   ✅ LEGAL_MAP tiene {len(LEGAL_MAP)} tipos de findings")

    print("\n2. Validando que todos los findings tienen articles y risk_types...")
    for finding_type, mapping in LEGAL_MAP.items():
        assert "articles" in mapping, f"{finding_type} debe tener 'articles'"
        assert "risk_types" in mapping, f"{finding_type} debe tener 'risk_types'"
        assert isinstance(mapping["articles"], list), f"{finding_type}.articles debe ser lista"
        assert isinstance(mapping["risk_types"], list), f"{finding_type}.risk_types debe ser lista"
        assert len(mapping["articles"]) > 0, f"{finding_type}.articles no debe estar vacío"
        assert len(mapping["risk_types"]) > 0, f"{finding_type}.risk_types no debe estar vacío"
        print(
            f"   ✅ {finding_type}: {len(mapping['articles'])} artículos, {len(mapping['risk_types'])} risk_types"
        )

    print("\n3. Validando estructura de cada artículo...")
    required_fields = ["law", "article", "description", "source", "boe_url", "last_verified"]
    valid_sources = {"BOE", "CENDOJ", "Texto Refundido LC"}
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    all_articles = []
    for finding_type, mapping in LEGAL_MAP.items():
        for article in mapping["articles"]:
            # Verificar campos obligatorios
            for field in required_fields:
                assert (
                    field in article
                ), f"{finding_type}: artículo {article.get('article', 'N/A')} debe tener campo '{field}'"

            # Verificar source
            assert (
                article["source"] in valid_sources
            ), f"{finding_type}: source '{article['source']}' debe ser uno de {valid_sources}"

            # Verificar boe_url
            assert article["boe_url"].startswith(
                "http"
            ), f"{finding_type}: boe_url debe empezar por 'http'"

            # Verificar last_verified (formato YYYY-MM-DD)
            assert date_pattern.match(
                article["last_verified"]
            ), f"{finding_type}: last_verified '{article['last_verified']}' debe tener formato YYYY-MM-DD"

            # Verificar que la fecha es válida
            try:
                datetime.strptime(article["last_verified"], "%Y-%m-%d")
            except ValueError:
                raise AssertionError(
                    f"{finding_type}: last_verified '{article['last_verified']}' no es una fecha válida"
                )

            # Guardar para detección de duplicados
            article_key = (article["law"], article["article"])
            all_articles.append(article_key)

            print(
                f"   ✅ {finding_type} → {article['article']} (verificado: {article['last_verified']})"
            )

    print("\n4. Verificando que no hay artículos duplicados...")
    unique_articles = set(all_articles)
    assert (
        len(all_articles) == len(unique_articles)
    ), f"Se detectaron artículos duplicados: {len(all_articles)} total vs {len(unique_articles)} únicos"
    print(f"   ✅ No hay duplicados: {len(unique_articles)} artículos únicos")

    print("\n5. Test de no regresión del grafo...")
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)

    assert "legal_findings" in result, "legal_findings debe estar presente"
    assert len(result["legal_findings"]) > 0, "legal_findings no debe estar vacío"
    print(f"   ✅ legal_findings presente: {len(result['legal_findings'])} findings")

    # Verificar que legal_basis incluye los nuevos campos
    for finding in result["legal_findings"]:
        if finding.get("legal_basis"):
            for article in finding["legal_basis"]:
                assert "source" in article, "Artículo debe tener campo 'source'"
                assert "boe_url" in article, "Artículo debe tener campo 'boe_url'"
                assert "last_verified" in article, "Artículo debe tener campo 'last_verified'"
    print("   ✅ legal_basis incluye metadatos de verificación")

    # Verificar que overall_risk no ha cambiado
    assert (
        result["report"]["overall_risk"] == "high"
    ), f"overall_risk debe ser 'high' para CASE_RETAIL_003, se obtuvo '{result['report']['overall_risk']}'"
    print("   ✅ overall_risk sigue siendo 'high' (sin regresión)")

    print("\n============================================================")
    print("✅ TODOS LOS TESTS DE INTEGRIDAD PASARON")
    print("============================================================")


def test_legal_map_is_dict():
    """Verifica que LEGAL_MAP es un diccionario."""
    assert isinstance(LEGAL_MAP, dict)


def test_legal_map_not_empty():
    """Verifica que LEGAL_MAP no está vacío."""
    assert len(LEGAL_MAP) > 0


def test_all_findings_have_articles():
    """Verifica que todos los findings tienen una lista de articles no vacía."""
    for finding_type, mapping in LEGAL_MAP.items():
        assert "articles" in mapping
        assert isinstance(mapping["articles"], list)
        assert len(mapping["articles"]) > 0


def test_all_findings_have_risk_types():
    """Verifica que todos los findings tienen una lista de risk_types no vacía."""
    for finding_type, mapping in LEGAL_MAP.items():
        assert "risk_types" in mapping
        assert isinstance(mapping["risk_types"], list)
        assert len(mapping["risk_types"]) > 0


def test_all_articles_have_required_fields():
    """Verifica que todos los artículos tienen los campos obligatorios."""
    required_fields = ["law", "article", "description", "source", "boe_url", "last_verified"]

    for finding_type, mapping in LEGAL_MAP.items():
        for article in mapping["articles"]:
            for field in required_fields:
                assert (
                    field in article
                ), f"{finding_type}: artículo {article.get('article', 'N/A')} debe tener campo '{field}'"


def test_all_sources_are_valid():
    """Verifica que todos los sources son válidos."""
    valid_sources = {"BOE", "CENDOJ", "Texto Refundido LC"}

    for finding_type, mapping in LEGAL_MAP.items():
        for article in mapping["articles"]:
            assert (
                article["source"] in valid_sources
            ), f"{finding_type}: source '{article['source']}' debe ser uno de {valid_sources}"


def test_all_boe_urls_start_with_http():
    """Verifica que todas las URLs empiezan por http."""
    for finding_type, mapping in LEGAL_MAP.items():
        for article in mapping["articles"]:
            assert article["boe_url"].startswith(
                "http"
            ), f"{finding_type}: boe_url debe empezar por 'http'"


def test_all_last_verified_have_correct_format():
    """Verifica que last_verified tiene formato YYYY-MM-DD."""
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    for finding_type, mapping in LEGAL_MAP.items():
        for article in mapping["articles"]:
            assert date_pattern.match(
                article["last_verified"]
            ), f"{finding_type}: last_verified '{article['last_verified']}' debe tener formato YYYY-MM-DD"


def test_all_last_verified_are_valid_dates():
    """Verifica que last_verified son fechas válidas."""
    for finding_type, mapping in LEGAL_MAP.items():
        for article in mapping["articles"]:
            try:
                datetime.strptime(article["last_verified"], "%Y-%m-%d")
            except ValueError:
                pytest.fail(
                    f"{finding_type}: last_verified '{article['last_verified']}' no es una fecha válida"
                )


def test_no_duplicate_articles():
    """Verifica que no hay artículos duplicados."""
    all_articles = []

    for finding_type, mapping in LEGAL_MAP.items():
        for article in mapping["articles"]:
            article_key = (article["law"], article["article"])
            all_articles.append(article_key)

    unique_articles = set(all_articles)
    assert (
        len(all_articles) == len(unique_articles)
    ), f"Se detectaron artículos duplicados: {len(all_articles)} total vs {len(unique_articles)} únicos"


def test_graph_executes_with_enriched_catalog():
    """Test de no regresión: el grafo ejecuta correctamente con el catálogo enriquecido."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)

    assert "legal_findings" in result
    assert len(result["legal_findings"]) > 0


def test_legal_basis_includes_metadata():
    """Verifica que legal_basis incluye los metadatos de verificación."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)

    for finding in result["legal_findings"]:
        if finding.get("legal_basis"):
            for article in finding["legal_basis"]:
                assert "source" in article
                assert "boe_url" in article
                assert "last_verified" in article


def test_overall_risk_unchanged():
    """Test de no regresión: overall_risk no ha cambiado para CASE_RETAIL_003."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_003)

    assert result["report"]["overall_risk"] == "high"


def test_notes_field_exists():
    """Verifica que el campo notes existe en todos los artículos."""
    for finding_type, mapping in LEGAL_MAP.items():
        for article in mapping["articles"]:
            assert "notes" in article, f"{finding_type}: artículo debe tener campo 'notes'"


def test_all_findings_mapped():
    """Verifica que hay al menos 4 tipos de findings mapeados."""
    expected_findings = {
        "accounting_irregularities",
        "delay_filing",
        "document_inconsistency",
        "documentation_gap",
    }
    actual_findings = set(LEGAL_MAP.keys())
    assert expected_findings.issubset(
        actual_findings
    ), f"Faltan findings esperados: {expected_findings - actual_findings}"
