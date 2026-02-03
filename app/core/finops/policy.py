"""
LLM Call Policy: Control programático de llamadas LLM.

ENDURECIMIENTO #7: Bloqueovoid llamadas LLM cuando no tiene sentido.

PRINCIPIO: LLM SOLO cuando hay evidencia suficiente y presupuesto disponible.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMCallDecision:
    """
    Decisión sobre si ejecutar llamada LLM.

    GATE: Si allow_call = False, NO se ejecuta LLM.
    """

    allow_call: bool
    reason: str
    degraded_mode: bool = False  # Si True, usar modo degradado (sin LLM)


class LLMCallPolicy:
    """
    Política que decide si se permite llamada LLM.

    ENDURECIMIENTO #7: Bloques programáticos antes de llamar.
    """

    def evaluate(
        self,
        case_id: str,
        phase: str,
        has_evidence: bool,
        insufficient_evidence: bool,
        no_response_reason: Optional[str],
        budget_available: bool,
    ) -> LLMCallDecision:
        """
        Evalúa si se permite llamada LLM.

        GATES:
        1. Si insufficient_evidence → BLOCK
        2. Si no_response_reason presente → BLOCK
        3. Si budget_available = False → BLOCK + degraded_mode
        4. Si not has_evidence → BLOCK

        Args:
            case_id: ID del caso
            phase: Fase de ejecución
            has_evidence: Hay evidencia disponible
            insufficient_evidence: Evidencia insuficiente
            no_response_reason: Razón de NO_RESPONSE (si aplica)
            budget_available: Presupuesto disponible

        Returns:
            LLMCallDecision
        """
        # GATE 1: Insufficient evidence
        if insufficient_evidence:
            return LLMCallDecision(
                allow_call=False,
                reason="INSUFFICIENT_EVIDENCE",
                degraded_mode=True,
            )

        # GATE 2: NO_RESPONSE reason
        if no_response_reason:
            return LLMCallDecision(
                allow_call=False,
                reason=f"NO_RESPONSE: {no_response_reason}",
                degraded_mode=True,
            )

        # GATE 3: Budget exceeded
        if not budget_available:
            return LLMCallDecision(
                allow_call=False,
                reason="BUDGET_EXCEEDED",
                degraded_mode=True,
            )

        # GATE 4: No evidence
        if not has_evidence:
            return LLMCallDecision(
                allow_call=False,
                reason="NO_EVIDENCE",
                degraded_mode=True,
            )

        # OK: Permitir llamada
        return LLMCallDecision(
            allow_call=True,
            reason="OK",
            degraded_mode=False,
        )


# ============================
# SINGLETON
# ============================

_global_policy: Optional[LLMCallPolicy] = None


def get_global_llm_policy() -> LLMCallPolicy:
    """Obtiene la policy global."""
    global _global_policy
    if _global_policy is None:
        _global_policy = LLMCallPolicy()
    return _global_policy
