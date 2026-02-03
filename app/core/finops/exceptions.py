"""
FinOps Exceptions.

ENDURECIMIENTO #7: Excepciones específicas para control de presupuesto.
"""


class BudgetExceededException(Exception):
    """
    Excepción cuando se excede el presupuesto disponible.

    GATE DURO: Esta excepción detiene ejecución ANTES de llamar al proveedor.
    """

    def __init__(
        self,
        case_id: str,
        required_usd: float,
        remaining_usd: float,
        phase: str,
    ):
        self.case_id = case_id
        self.required_usd = required_usd
        self.remaining_usd = remaining_usd
        self.phase = phase

        message = (
            f"BUDGET_EXCEEDED: case_id={case_id} phase={phase} "
            f"required={required_usd:.6f} remaining={remaining_usd:.6f}"
        )
        super().__init__(message)


class PricingTableError(Exception):
    """Excepción cuando hay problema con la tabla de precios."""

    pass
