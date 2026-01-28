"""
Budget Management y Ledger.

ENDURECIMIENTO #7: Control de presupuesto y registro de gastos.

PRINCIPIO: Presupuesto HARD. Si se excede, ejecución se detiene.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import os


# ============================
# BUDGET CONFIGURATION
# ============================

DEFAULT_CASE_BUDGET_USD = float(os.getenv("DEFAULT_CASE_BUDGET_USD", "10.0"))


# ============================
# STRUCTURES
# ============================

@dataclass
class BudgetEntry:
    """
    Entrada individual en el ledger de gastos.
    
    TRAZABILIDAD: Cada entrada registra pricing_version.
    """
    case_id: str
    phase: str  # ingest, chunk, embed, retrieve, llm_explain
    provider: str  # openai, local, mock
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    trace_id: Optional[str] = None
    pricing_version: Optional[str] = None
    pricing_fingerprint: Optional[str] = None
    timestamp: Optional[str] = None  # ISO format, NO usado en lógica
    
    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "phase": self.phase,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "trace_id": self.trace_id,
            "pricing_version": self.pricing_version,
            "pricing_fingerprint": self.pricing_fingerprint,
            "timestamp": self.timestamp,
        }


@dataclass
class CaseBudget:
    """
    Presupuesto para un case_id.
    
    INVARIANTE: spent_usd + remaining_usd == budget_usd (con margen de error float).
    """
    case_id: str
    budget_usd: float
    spent_usd: float = 0.0
    
    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.budget_usd - self.spent_usd)
    
    def can_spend(self, amount_usd: float) -> bool:
        """Verifica si hay presupuesto disponible."""
        return self.remaining_usd >= amount_usd
    
    def record_spend(self, amount_usd: float):
        """Registra un gasto."""
        self.spent_usd += amount_usd


# ============================
# BUDGET LEDGER (IN-MEMORY)
# ============================

class BudgetLedger:
    """
    Ledger de gastos por case_id.
    
    ENDURECIMIENTO #7: Opera en memoria para tests, puede persistir opcionalmente.
    """
    
    def __init__(self):
        self._ledger: List[BudgetEntry] = []
        self._budgets: Dict[str, CaseBudget] = {}
    
    def initialize_budget(
        self,
        case_id: str,
        budget_usd: Optional[float] = None,
    ):
        """
        Inicializa presupuesto para un caso.
        
        Args:
            case_id: ID del caso
            budget_usd: Presupuesto en USD (si None, usa DEFAULT_CASE_BUDGET_USD)
        """
        if case_id not in self._budgets:
            self._budgets[case_id] = CaseBudget(
                case_id=case_id,
                budget_usd=budget_usd or DEFAULT_CASE_BUDGET_USD,
            )
    
    def get_budget(self, case_id: str) -> CaseBudget:
        """Obtiene presupuesto de un caso."""
        if case_id not in self._budgets:
            self.initialize_budget(case_id)
        return self._budgets[case_id]
    
    def record_entry(
        self,
        case_id: str,
        phase: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        trace_id: Optional[str] = None,
        pricing_version: Optional[str] = None,
        pricing_fingerprint: Optional[str] = None,
    ):
        """
        Registra una entrada en el ledger y actualiza presupuesto.
        
        Args:
            case_id: ID del caso
            phase: Fase de ejecución
            provider: Proveedor (openai, local, mock)
            model: Modelo usado
            input_tokens: Tokens de entrada
            output_tokens: Tokens de salida
            cost_usd: Coste en USD
            trace_id: ID del trace (si existe)
            pricing_version: Versión de pricing usada
            pricing_fingerprint: Fingerprint de pricing
        """
        # Crear entrada
        entry = BudgetEntry(
            case_id=case_id,
            phase=phase,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            trace_id=trace_id,
            pricing_version=pricing_version,
            pricing_fingerprint=pricing_fingerprint,
            timestamp=datetime.utcnow().isoformat(),
        )
        
        self._ledger.append(entry)
        
        # Actualizar presupuesto
        budget = self.get_budget(case_id)
        budget.record_spend(cost_usd)
    
    def get_entries(
        self,
        case_id: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> List[BudgetEntry]:
        """
        Obtiene entradas del ledger filtradas.
        
        Args:
            case_id: Filtrar por caso (opcional)
            phase: Filtrar por fase (opcional)
        
        Returns:
            Lista de entradas
        """
        entries = self._ledger
        
        if case_id:
            entries = [e for e in entries if e.case_id == case_id]
        
        if phase:
            entries = [e for e in entries if e.phase == phase]
        
        return entries
    
    def get_total_cost(
        self,
        case_id: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> float:
        """
        Calcula coste total filtrado.
        
        Args:
            case_id: Filtrar por caso (opcional)
            phase: Filtrar por fase (opcional)
        
        Returns:
            Coste total en USD
        """
        entries = self.get_entries(case_id=case_id, phase=phase)
        return sum(e.cost_usd for e in entries)
    
    def clear(self):
        """Limpia el ledger (para tests)."""
        self._ledger.clear()
        self._budgets.clear()


# ============================
# SINGLETON GLOBAL (opcional)
# ============================

_global_ledger: Optional[BudgetLedger] = None


def get_global_ledger() -> BudgetLedger:
    """Obtiene el ledger global (singleton)."""
    global _global_ledger
    if _global_ledger is None:
        _global_ledger = BudgetLedger()
    return _global_ledger


def reset_global_ledger():
    """Resetea el ledger global (para tests)."""
    global _global_ledger
    _global_ledger = BudgetLedger()

