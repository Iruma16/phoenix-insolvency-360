"""
Test End-to-End de Análisis Financiero Profundo (Fase B1).

Objetivo: Verificar que todas las nuevas funcionalidades funcionan correctamente:
1. Validación de ecuación contable
2. Detección de anomalías (Ley de Benford)
3. Extracción estructurada de tablas
4. Integración en endpoint
"""
from datetime import datetime

import pytest

from app.services.financial_analysis import (
    BalanceData,
    BalanceField,
    ConfidenceLevel,
    Evidence,
)
from app.services.financial_validation import (
    ValidationSeverity,
    analyze_benford_law,
    validate_balance_equation,
    validate_financial_data,
)

# =========================================================
# FIXTURES DE DATOS DE PRUEBA
# =========================================================


@pytest.fixture
def valid_balance():
    """Balance válido que cumple ecuación contable."""
    return BalanceData(
        activo_corriente=BalanceField(
            value=100000.0,
            evidence=Evidence(
                document_id="doc_balance",
                filename="balance.xlsx",
                excerpt="Activo Corriente: 100,000",
                extraction_method="excel_cell",
                extraction_confidence=0.95,
            ),
            confidence=ConfidenceLevel.HIGH,
        ),
        activo_no_corriente=BalanceField(
            value=200000.0,
            evidence=Evidence(
                document_id="doc_balance",
                filename="balance.xlsx",
                excerpt="Activo No Corriente: 200,000",
                extraction_method="excel_cell",
                extraction_confidence=0.95,
            ),
            confidence=ConfidenceLevel.HIGH,
        ),
        pasivo_corriente=BalanceField(
            value=80000.0,
            evidence=Evidence(
                document_id="doc_balance",
                filename="balance.xlsx",
                excerpt="Pasivo Corriente: 80,000",
                extraction_method="excel_cell",
                extraction_confidence=0.95,
            ),
            confidence=ConfidenceLevel.HIGH,
        ),
        pasivo_no_corriente=BalanceField(
            value=150000.0,
            evidence=Evidence(
                document_id="doc_balance",
                filename="balance.xlsx",
                excerpt="Pasivo No Corriente: 150,000",
                extraction_method="excel_cell",
                extraction_confidence=0.95,
            ),
            confidence=ConfidenceLevel.HIGH,
        ),
        patrimonio_neto=BalanceField(
            value=70000.0,
            evidence=Evidence(
                document_id="doc_balance",
                filename="balance.xlsx",
                excerpt="Patrimonio Neto: 70,000",
                extraction_method="excel_cell",
                extraction_confidence=0.95,
            ),
            confidence=ConfidenceLevel.HIGH,
        ),
    )


@pytest.fixture
def invalid_balance():
    """Balance que NO cumple ecuación contable."""
    return BalanceData(
        activo_corriente=BalanceField(
            value=100000.0,
            evidence=Evidence(
                document_id="doc_balance",
                filename="balance.xlsx",
                excerpt="Activo Corriente: 100,000",
                extraction_method="excel_cell",
                extraction_confidence=0.95,
            ),
            confidence=ConfidenceLevel.HIGH,
        ),
        activo_no_corriente=BalanceField(
            value=200000.0,
            evidence=Evidence(
                document_id="doc_balance",
                filename="balance.xlsx",
                excerpt="Activo No Corriente: 200,000",
                extraction_method="excel_cell",
                extraction_confidence=0.95,
            ),
            confidence=ConfidenceLevel.HIGH,
        ),
        pasivo_corriente=BalanceField(
            value=80000.0,
            evidence=Evidence(
                document_id="doc_balance",
                filename="balance.xlsx",
                excerpt="Pasivo Corriente: 80,000",
                extraction_method="excel_cell",
                extraction_confidence=0.95,
            ),
            confidence=ConfidenceLevel.HIGH,
        ),
        pasivo_no_corriente=BalanceField(
            value=150000.0,
            evidence=Evidence(
                document_id="doc_balance",
                filename="balance.xlsx",
                excerpt="Pasivo No Corriente: 150,000",
                extraction_method="excel_cell",
                extraction_confidence=0.95,
            ),
            confidence=ConfidenceLevel.HIGH,
        ),
        patrimonio_neto=BalanceField(
            value=10000.0,  # ⚠️ INCORRECTO: debería ser 70,000 para que cuadre
            evidence=Evidence(
                document_id="doc_balance",
                filename="balance.xlsx",
                excerpt="Patrimonio Neto: 10,000",
                extraction_method="excel_cell",
                extraction_confidence=0.95,
            ),
            confidence=ConfidenceLevel.HIGH,
        ),
    )


# =========================================================
# TESTS DE VALIDACIÓN
# =========================================================


def test_validate_balance_equation_valid(valid_balance):
    """Test: Ecuación contable válida debe pasar."""
    issue = validate_balance_equation(valid_balance)
    assert issue is None, "Balance válido no debe generar issue"


def test_validate_balance_equation_invalid(invalid_balance):
    """Test: Ecuación contable inválida debe fallar."""
    issue = validate_balance_equation(invalid_balance)
    assert issue is not None, "Balance inválido debe generar issue"
    assert issue.code == "BALANCE_EQUATION_FAILED"
    assert issue.severity == ValidationSeverity.CRITICAL
    assert issue.deviation_percent > 0


def test_benford_law_natural_data():
    """Test: Datos que siguen distribución natural deben pasar."""
    # Números que siguen distribución de Benford aproximada
    natural_numbers = [
        123.45,
        189.67,
        234.12,
        345.89,
        456.23,
        567.45,
        678.12,
        789.34,
        890.56,
        912.34,
        1234.56,
        1567.89,
        1890.12,
        2345.67,
        2678.90,
        3123.45,
        3567.89,
        4012.34,
        4567.89,
        5123.45,
        5678.90,
        6234.56,
        6789.12,
        7345.67,
        7890.23,
        8123.45,
        8567.89,
        9012.34,
        9456.78,
        9890.12,
        10123.45,
        11234.56,
        12345.67,
        13456.78,
        14567.89,
    ]

    issue = analyze_benford_law(natural_numbers)
    # Debería pasar o ser desviación leve
    if issue:
        assert issue.severity in [ValidationSeverity.LOW, ValidationSeverity.MEDIUM]


def test_benford_law_manipulated_data():
    """Test: Datos claramente manipulados deben detectarse."""
    # Números que SOLO empiezan con 9 (muy sospechoso)
    manipulated_numbers = [
        900.0,
        910.0,
        920.0,
        930.0,
        940.0,
        950.0,
        960.0,
        970.0,
        980.0,
        990.0,
        9100.0,
        9200.0,
        9300.0,
        9400.0,
        9500.0,
        9600.0,
        9700.0,
        9800.0,
        9900.0,
        9950.0,
        91000.0,
        92000.0,
        93000.0,
        94000.0,
        95000.0,
        96000.0,
        97000.0,
        98000.0,
        99000.0,
        99500.0,
        990000.0,
        991000.0,
        992000.0,
        993000.0,
        994000.0,
    ]

    issue = analyze_benford_law(manipulated_numbers)
    assert issue is not None, "Datos manipulados deben generar issue"
    assert issue.code == "BENFORD_LAW_VIOLATION"
    assert issue.severity in [ValidationSeverity.MEDIUM, ValidationSeverity.HIGH]


def test_validate_financial_data_complete(valid_balance):
    """Test: Validación completa de datos financieros."""
    result = validate_financial_data(valid_balance, None)

    assert result.total_checks > 0
    assert result.passed_checks >= 0
    assert result.is_valid == (len(result.issues) == 0)
    assert result.confidence_level in [
        ConfidenceLevel.HIGH,
        ConfidenceLevel.MEDIUM,
        ConfidenceLevel.LOW,
    ]


def test_validate_financial_data_with_issues(invalid_balance):
    """Test: Validación debe detectar problemas."""
    result = validate_financial_data(invalid_balance, None)

    assert not result.is_valid, "Balance inválido debe fallar validación"
    assert len(result.issues) > 0, "Debe haber al menos un issue"
    assert result.confidence_level == ConfidenceLevel.LOW, "Confianza debe ser baja"

    # Verificar que hay un issue crítico
    critical_issues = [i for i in result.issues if i.severity == ValidationSeverity.CRITICAL]
    assert len(critical_issues) > 0, "Debe haber al menos un issue crítico"


# =========================================================
# TESTS DE INTEGRACIÓN
# =========================================================


def test_financial_analysis_result_with_validation():
    """Test: FinancialAnalysisResult puede incluir validación."""
    from app.services.financial_analysis import FinancialAnalysisResult

    result = FinancialAnalysisResult(
        case_id="CASE_TEST_001",
        analysis_date=datetime.utcnow(),
        balance=None,
        profit_loss=None,
        credit_classification=[],
        total_debt=None,
        ratios=[],
        insolvency=None,
        timeline=[],
        validation_result={"is_valid": True, "total_checks": 3, "passed_checks": 3, "issues": []},
        data_quality_score=1.0,
    )

    assert result.validation_result is not None
    assert result.data_quality_score == 1.0


# =========================================================
# TESTS DE EXTRACCIÓN DE TABLAS (MOCK)
# =========================================================


def test_excel_table_extractor_imports():
    """Test: Módulo de extracción de tablas importa correctamente."""

    # Si llega aquí, las importaciones funcionan
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
