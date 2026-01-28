"""
TESTS: Budget Management (Endurecimiento #7)

OBJETIVO: Validar presupuesto y ledger determinista.

PRINCIPIO: Presupuesto HARD. Si se excede → NO se ejecuta.
"""
import pytest
from unittest.mock import Mock

from app.core.finops.budget import (
    CaseBudget,
    BudgetLedger,
    BudgetEntry,
    DEFAULT_CASE_BUDGET_USD,
)
from app.core.finops.exceptions import BudgetExceededException
from app.core.finops.gates import check_budget_or_fail, record_actual_cost
from app.core.finops.pricing import estimate_cost_usd


# ============================
# TEST 1: CASE BUDGET
# ============================

def test_case_budget_invariant():
    """INVARIANTE: spent_usd + remaining_usd == budget_usd."""
    budget = CaseBudget(case_id="CASE_001", budget_usd=10.0)
    
    assert budget.budget_usd == 10.0
    assert budget.spent_usd == 0.0
    assert budget.remaining_usd == 10.0
    
    budget.record_spend(3.0)
    
    assert budget.spent_usd == 3.0
    assert budget.remaining_usd == 7.0
    assert budget.spent_usd + budget.remaining_usd == pytest.approx(budget.budget_usd)


def test_case_budget_can_spend():
    """can_spend debe verificar presupuesto disponible."""
    budget = CaseBudget(case_id="CASE_001", budget_usd=5.0)
    
    assert budget.can_spend(3.0) is True
    assert budget.can_spend(5.0) is True
    assert budget.can_spend(6.0) is False
    
    budget.record_spend(3.0)
    
    assert budget.can_spend(2.0) is True
    assert budget.can_spend(3.0) is False


# ============================
# TEST 2: BUDGET LEDGER
# ============================

def test_ledger_initialize_budget():
    """Ledger debe inicializar presupuesto por caso."""
    ledger = BudgetLedger()
    ledger.initialize_budget("CASE_001", budget_usd=15.0)
    
    budget = ledger.get_budget("CASE_001")
    
    assert budget.case_id == "CASE_001"
    assert budget.budget_usd == 15.0


def test_ledger_auto_initialize():
    """get_budget debe auto-inicializar con DEFAULT si no existe."""
    ledger = BudgetLedger()
    
    budget = ledger.get_budget("CASE_002")
    
    assert budget.budget_usd == DEFAULT_CASE_BUDGET_USD


def test_ledger_record_entry():
    """Ledger debe registrar entrada y actualizar presupuesto."""
    ledger = BudgetLedger()
    ledger.initialize_budget("CASE_001", budget_usd=10.0)
    
    ledger.record_entry(
        case_id="CASE_001",
        phase="embed",
        provider="openai",
        model="text-embedding-3-small",
        input_tokens=1000,
        output_tokens=0,
        cost_usd=0.00002,
        pricing_version="2026-01-06",
        pricing_fingerprint="abc123",
    )
    
    # Verificar entrada
    entries = ledger.get_entries(case_id="CASE_001")
    assert len(entries) == 1
    assert entries[0].phase == "embed"
    assert entries[0].cost_usd == 0.00002
    
    # Verificar presupuesto actualizado
    budget = ledger.get_budget("CASE_001")
    assert budget.spent_usd == 0.00002
    assert budget.remaining_usd == pytest.approx(9.99998)


def test_ledger_get_total_cost():
    """get_total_cost debe calcular coste total."""
    ledger = BudgetLedger()
    
    ledger.record_entry(
        case_id="CASE_001",
        phase="embed",
        provider="openai",
        model="text-embedding-3-small",
        input_tokens=1000,
        output_tokens=0,
        cost_usd=0.00002,
    )
    
    ledger.record_entry(
        case_id="CASE_001",
        phase="llm_explain",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=500,
        output_tokens=200,
        cost_usd=0.00019,
    )
    
    total = ledger.get_total_cost(case_id="CASE_001")
    
    assert total == pytest.approx(0.00021)


def test_ledger_filter_by_phase():
    """Ledger debe filtrar por phase."""
    ledger = BudgetLedger()
    
    ledger.record_entry(
        case_id="CASE_001",
        phase="embed",
        provider="openai",
        model="text-embedding-3-small",
        input_tokens=1000,
        output_tokens=0,
        cost_usd=0.00002,
    )
    
    ledger.record_entry(
        case_id="CASE_001",
        phase="llm_explain",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=500,
        output_tokens=200,
        cost_usd=0.00019,
    )
    
    embed_entries = ledger.get_entries(phase="embed")
    llm_entries = ledger.get_entries(phase="llm_explain")
    
    assert len(embed_entries) == 1
    assert len(llm_entries) == 1


# ============================
# TEST 3: BUDGET GATES
# ============================

def test_check_budget_or_fail_ok():
    """check_budget_or_fail debe retornar coste estimado si hay presupuesto."""
    ledger = BudgetLedger()
    ledger.initialize_budget("CASE_001", budget_usd=1.0)
    
    estimated_cost = check_budget_or_fail(
        case_id="CASE_001",
        phase="embed",
        model="text-embedding-3-small",
        estimated_input_tokens=1000,
        estimated_output_tokens=0,
        ledger=ledger,
    )
    
    assert estimated_cost == pytest.approx(0.00002)


def test_check_budget_or_fail_exceeds():
    """GATE: check_budget_or_fail debe lanzar BudgetExceededException si excede."""
    ledger = BudgetLedger()
    ledger.initialize_budget("CASE_001", budget_usd=0.0001)  # Presupuesto muy bajo
    
    with pytest.raises(BudgetExceededException) as exc_info:
        check_budget_or_fail(
            case_id="CASE_001",
            phase="llm_explain",
            model="gpt-4o-mini",
            estimated_input_tokens=10000,  # Alto coste
            estimated_output_tokens=5000,
            ledger=ledger,
        )
    
    exception = exc_info.value
    assert exception.case_id == "CASE_001"
    assert exception.phase == "llm_explain"
    assert exception.required_usd > exception.remaining_usd


def test_check_budget_prevents_llm_call():
    """INVARIANTE: Si presupuesto excedido → NO se llama al proveedor (mock)."""
    ledger = BudgetLedger()
    ledger.initialize_budget("CASE_001", budget_usd=0.0001)
    
    mock_llm_call = Mock()
    
    try:
        check_budget_or_fail(
            case_id="CASE_001",
            phase="llm_explain",
            model="gpt-4o-mini",
            estimated_input_tokens=10000,
            estimated_output_tokens=5000,
            ledger=ledger,
        )
        
        # Si no lanza excepción, llamar al LLM
        mock_llm_call()
        
    except BudgetExceededException:
        # Excepción lanzada → NO se llama al LLM
        pass
    
    # Verificar que NO se llamó
    assert mock_llm_call.call_count == 0


# ============================
# TEST 4: RECORD ACTUAL COST
# ============================

def test_record_actual_cost_with_pricing_info():
    """record_actual_cost debe registrar con pricing_version."""
    ledger = BudgetLedger()
    ledger.initialize_budget("CASE_001", budget_usd=10.0)
    
    record_actual_cost(
        case_id="CASE_001",
        phase="embed",
        provider="openai",
        model="text-embedding-3-small",
        input_tokens=1000,
        output_tokens=0,
        cost_usd=None,  # Se calcula desde pricing table
        trace_id="trace_001",
        ledger=ledger,
    )
    
    entries = ledger.get_entries(case_id="CASE_001")
    
    assert len(entries) == 1
    assert entries[0].pricing_version is not None
    assert entries[0].pricing_fingerprint is not None
    assert entries[0].trace_id == "trace_001"


def test_record_actual_cost_calculates_from_table():
    """record_actual_cost debe calcular coste si no se proporciona."""
    ledger = BudgetLedger()
    
    record_actual_cost(
        case_id="CASE_001",
        phase="embed",
        provider="openai",
        model="text-embedding-3-small",
        input_tokens=1000,
        output_tokens=0,
        cost_usd=None,
        ledger=ledger,
    )
    
    entries = ledger.get_entries(case_id="CASE_001")
    
    expected_cost = estimate_cost_usd("text-embedding-3-small", 1000, 0)
    assert entries[0].cost_usd == pytest.approx(expected_cost)


# ============================
# RESUMEN DE TESTS
# ============================
"""
COBERTURA:

1. ✅ CaseBudget invariante (spent + remaining = budget)
2. ✅ CaseBudget can_spend
3. ✅ Ledger inicializa presupuesto
4. ✅ Ledger auto-inicializa con DEFAULT
5. ✅ Ledger registra entrada y actualiza presupuesto
6. ✅ Ledger calcula total_cost
7. ✅ Ledger filtra por phase
8. ✅ check_budget_or_fail OK
9. ✅ check_budget_or_fail EXCEEDS → BudgetExceededException
10. ✅ Presupuesto excedido → NO se llama al proveedor (mock)
11. ✅ record_actual_cost con pricing_info
12. ✅ record_actual_cost calcula desde pricing table

TOTAL: 12 tests deterministas

INVARIANTES CERTIFICADOS:
- INVARIANTE 1: spent_usd + remaining_usd == budget_usd
- INVARIANTE 2: Si presupuesto excedido → BudgetExceededException
- INVARIANTE 3: BudgetExceededException detiene ejecución ANTES de llamar al proveedor
- INVARIANTE 4: Cada entrada del ledger tiene pricing_version y pricing_fingerprint
- INVARIANTE 5: Ledger calcula coste desde pricing table si no se proporciona
"""

