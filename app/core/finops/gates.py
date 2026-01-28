"""
Budget Gates: Corte duro BEFORE calling.

ENDURECIMIENTO #7: Verificación de presupuesto antes de ejecutar.

PRINCIPIO: NO se ejecuta si no hay presupuesto.
"""
from typing import Optional

from .budget import BudgetLedger, get_global_ledger
from .pricing import estimate_cost_usd, get_pricing_info
from .exceptions import BudgetExceededException


def check_budget_or_fail(
    case_id: str,
    phase: str,
    model: str,
    estimated_input_tokens: int,
    estimated_output_tokens: int = 0,
    ledger: Optional[BudgetLedger] = None,
) -> float:
    """
    Verifica presupuesto ANTES de ejecutar llamada.
    
    GATE DURO: Si presupuesto insuficiente → BudgetExceededException.
    
    Args:
        case_id: ID del caso
        phase: Fase de ejecución
        model: Modelo a usar
        estimated_input_tokens: Tokens estimados de entrada
        estimated_output_tokens: Tokens estimados de salida
        ledger: Ledger a usar (si None, usa global)
    
    Returns:
        Coste estimado en USD
    
    Raises:
        BudgetExceededException: Si presupuesto insuficiente
    """
    if ledger is None:
        ledger = get_global_ledger()
    
    # Estimar coste
    estimated_cost = estimate_cost_usd(
        model=model,
        input_tokens=estimated_input_tokens,
        output_tokens=estimated_output_tokens,
    )
    
    # Verificar presupuesto
    budget = ledger.get_budget(case_id)
    
    if not budget.can_spend(estimated_cost):
        raise BudgetExceededException(
            case_id=case_id,
            required_usd=estimated_cost,
            remaining_usd=budget.remaining_usd,
            phase=phase,
        )
    
    return estimated_cost


def record_actual_cost(
    case_id: str,
    phase: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: Optional[float] = None,
    trace_id: Optional[str] = None,
    ledger: Optional[BudgetLedger] = None,
):
    """
    Registra coste real después de ejecutar.
    
    Args:
        case_id: ID del caso
        phase: Fase de ejecución
        provider: Proveedor usado
        model: Modelo usado
        input_tokens: Tokens reales de entrada
        output_tokens: Tokens reales de salida
        cost_usd: Coste real (si None, calcula desde pricing table)
        trace_id: ID del trace
        ledger: Ledger a usar (si None, usa global)
    """
    if ledger is None:
        ledger = get_global_ledger()
    
    # Si no hay coste real, calcular desde pricing table
    if cost_usd is None:
        cost_usd = estimate_cost_usd(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    
    # Obtener pricing info
    pricing_info = get_pricing_info()
    
    # Registrar en ledger
    ledger.record_entry(
        case_id=case_id,
        phase=phase,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        trace_id=trace_id,
        pricing_version=pricing_info["pricing_version"],
        pricing_fingerprint=pricing_info["pricing_fingerprint"],
    )

