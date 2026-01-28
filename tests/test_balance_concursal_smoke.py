"""
Tests smoke para Balance de Situación Concursal.

FASE 1.3: Balance de Situación Automático
"""
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.credit import Credit, CreditNature
from app.models.financial_statement import BalanceSheet
from app.services.balance_concursal_service import BalanceConcursalService
from app.services.credit_classifier import TRLCCreditClassifier
from app.services.financial_ratios import FinancialRatiosCalculator
from app.services.insolvency_detector import TRLCInsolvencyDetector


@pytest.mark.smoke
def test_credit_classifier_salario():
    """Test clasificación de crédito salarial."""
    classifier = TRLCCreditClassifier()

    credit = Credit(
        credit_id="test-001",
        creditor_id="creditor-001",
        creditor_name="Juan Pérez",
        principal_amount=Decimal("5000"),
        interest_amount=Decimal("0"),
        total_amount=Decimal("5000"),
        nature=CreditNature.SALARIO,
    )

    classified = classifier.classify_credit(credit)

    assert classified.trlc_classification is not None
    assert classified.classification_reasoning is not None


@pytest.mark.smoke
def test_ratios_calculator_basic():
    """Test cálculo de ratios básicos."""
    calculator = FinancialRatiosCalculator()

    balance = BalanceSheet(
        activo_corriente=Decimal("100000"),
        activo_no_corriente=Decimal("50000"),
        total_activo=Decimal("150000"),
        pasivo_corriente=Decimal("60000"),
        pasivo_no_corriente=Decimal("40000"),
        total_pasivo=Decimal("100000"),
        patrimonio_neto=Decimal("50000"),
    )

    ratios = calculator.calculate_all_ratios(balance)

    assert "liquidez" in ratios
    assert ratios["liquidez"].status == "CALCULADO"
    assert ratios["liquidez"].value is not None


@pytest.mark.smoke
def test_insolvency_detector_pn_negativo_sin_impagos():
    """Test que PN negativo sin impagos NO genera insolvencia actual."""
    detector = TRLCInsolvencyDetector()

    balance = BalanceSheet(
        total_activo=Decimal("80000"),
        total_pasivo=Decimal("100000"),
        patrimonio_neto=Decimal("-20000"),  # Negativo
        activo_corriente=Decimal("30000"),
        pasivo_corriente=Decimal("40000"),
    )

    result = detector.detectar_insolvencia_actual(balance, [], [])  # Sin impagos

    # PN negativo sin impagos → NO insolvencia actual
    assert result["existe_insolvencia_actual"] == False
    assert result["nivel_gravedad"] in ["MEDIA", "NINGUNA"]


@pytest.mark.smoke
def test_insolvency_detector_impagos_exigibles():
    """Test que impagos exigibles SÍ generan insolvencia actual."""
    detector = TRLCInsolvencyDetector()

    balance = BalanceSheet(
        total_activo=Decimal("100000"),
        total_pasivo=Decimal("80000"),
        patrimonio_neto=Decimal("20000"),  # Positivo
        activo_corriente=Decimal("40000"),
        pasivo_corriente=Decimal("50000"),
    )

    impagos = [
        {"creditor_id": "C1", "amount": Decimal("10000"), "exigible": True},
        {"creditor_id": "C2", "amount": Decimal("5000"), "exigible": True},
    ]

    result = detector.detectar_insolvencia_actual(balance, [], impagos)

    # Impagos exigibles → SÍ insolvencia actual
    assert result["existe_insolvencia_actual"] == True
    assert result["nivel_gravedad"] == "CRÍTICA"


@pytest.mark.smoke
def test_balance_concursal_service_e2e():
    """Test E2E del servicio completo."""
    service = BalanceConcursalService()

    balance = BalanceSheet(
        activo_corriente=Decimal("100000"),
        activo_no_corriente=Decimal("50000"),
        total_activo=Decimal("150000"),
        pasivo_corriente=Decimal("60000"),
        pasivo_no_corriente=Decimal("40000"),
        total_pasivo=Decimal("100000"),
        patrimonio_neto=Decimal("50000"),
    )

    creditos = [
        Credit(
            credit_id="C1",
            creditor_id="CRED1",
            creditor_name="Banco X",
            principal_amount=Decimal("50000"),
            interest_amount=Decimal("0"),
            total_amount=Decimal("50000"),
            nature=CreditNature.FINANCIERO,
        ),
        Credit(
            credit_id="C2",
            creditor_id="CRED2",
            creditor_name="Trabajador Y",
            principal_amount=Decimal("10000"),
            interest_amount=Decimal("0"),
            total_amount=Decimal("10000"),
            nature=CreditNature.SALARIO,
        ),
    ]

    output = service.analyze_balance_concursal(
        case_id="TEST-CASE-001",
        balance=balance,
        creditos=creditos,
    )

    assert output.balance_id is not None
    assert output.case_id == "TEST-CASE-001"
    assert len(output.creditos) == 2
    assert output.dictamen is not None
    assert output.dictamen.base_legal is not None  # P0.11
    assert len(output.dictamen.base_legal) > 0
    assert output.confidence is not None
    assert "classification" in output.confidence
    assert "TRLC" in output.ruleset_version  # P0.5


@pytest.mark.smoke
def test_credit_fecha_validation():
    """Test P0.3: Validación de fechas incoherentes."""
    with pytest.raises(ValidationError, match="no puede ser anterior"):
        Credit(
            credit_id="C1",
            creditor_id="CRED1",
            creditor_name="Test",
            principal_amount=Decimal("1000"),
            interest_amount=Decimal("0"),
            total_amount=Decimal("1000"),
            nature=CreditNature.FINANCIERO,
            devengo_date=date(2024, 12, 1),
            due_date=date(2024, 11, 1),  # Anterior a devengo → ERROR
        )
