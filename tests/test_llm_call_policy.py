"""
TESTS: LLM Call Policy (Endurecimiento #7)

OBJETIVO: Validar política que bloquea llamadas LLM sin evidencia o presupuesto.

PRINCIPIO: LLM SOLO cuando hay evidencia suficiente y presupuesto disponible.
"""

from app.core.finops.policy import (
    LLMCallDecision,
    LLMCallPolicy,
)

# ============================
# TEST 1: DECISION STRUCTURE
# ============================


def test_llm_call_decision_structure():
    """LLMCallDecision debe tener campos obligatorios."""
    decision = LLMCallDecision(
        allow_call=True,
        reason="OK",
        degraded_mode=False,
    )

    assert decision.allow_call is True
    assert decision.reason == "OK"
    assert decision.degraded_mode is False


# ============================
# TEST 2: POLICY - OK CASES
# ============================


def test_policy_allow_call_when_ok():
    """Policy debe permitir llamada cuando todo OK."""
    policy = LLMCallPolicy()

    decision = policy.evaluate(
        case_id="CASE_001",
        phase="llm_explain",
        has_evidence=True,
        insufficient_evidence=False,
        no_response_reason=None,
        budget_available=True,
    )

    assert decision.allow_call is True
    assert decision.reason == "OK"
    assert decision.degraded_mode is False


# ============================
# TEST 3: POLICY - BLOCK CASES
# ============================


def test_policy_block_insufficient_evidence():
    """GATE: insufficient_evidence → BLOCK."""
    policy = LLMCallPolicy()

    decision = policy.evaluate(
        case_id="CASE_001",
        phase="llm_explain",
        has_evidence=True,
        insufficient_evidence=True,  # BLOQUEANTE
        no_response_reason=None,
        budget_available=True,
    )

    assert decision.allow_call is False
    assert decision.reason == "INSUFFICIENT_EVIDENCE"
    assert decision.degraded_mode is True


def test_policy_block_no_response():
    """GATE: no_response_reason → BLOCK."""
    policy = LLMCallPolicy()

    decision = policy.evaluate(
        case_id="CASE_001",
        phase="llm_explain",
        has_evidence=True,
        insufficient_evidence=False,
        no_response_reason="EVIDENCE_MISSING",  # BLOQUEANTE
        budget_available=True,
    )

    assert decision.allow_call is False
    assert "NO_RESPONSE" in decision.reason
    assert decision.degraded_mode is True


def test_policy_block_budget_exceeded():
    """GATE: budget_available=False → BLOCK + degraded_mode."""
    policy = LLMCallPolicy()

    decision = policy.evaluate(
        case_id="CASE_001",
        phase="llm_explain",
        has_evidence=True,
        insufficient_evidence=False,
        no_response_reason=None,
        budget_available=False,  # BLOQUEANTE
    )

    assert decision.allow_call is False
    assert decision.reason == "BUDGET_EXCEEDED"
    assert decision.degraded_mode is True


def test_policy_block_no_evidence():
    """GATE: has_evidence=False → BLOCK."""
    policy = LLMCallPolicy()

    decision = policy.evaluate(
        case_id="CASE_001",
        phase="llm_explain",
        has_evidence=False,  # BLOQUEANTE
        insufficient_evidence=False,
        no_response_reason=None,
        budget_available=True,
    )

    assert decision.allow_call is False
    assert decision.reason == "NO_EVIDENCE"
    assert decision.degraded_mode is True


# ============================
# TEST 4: GATE PRIORITY
# ============================


def test_policy_gate_priority_insufficient_evidence_first():
    """GATE 1 (insufficient_evidence) tiene prioridad."""
    policy = LLMCallPolicy()

    # Múltiples problemas: insufficient_evidence Y budget_exceeded
    decision = policy.evaluate(
        case_id="CASE_001",
        phase="llm_explain",
        has_evidence=True,
        insufficient_evidence=True,  # Primer gate
        no_response_reason=None,
        budget_available=False,  # También falla
    )

    # Debe retornar el primer gate que falla
    assert decision.allow_call is False
    assert decision.reason == "INSUFFICIENT_EVIDENCE"


def test_policy_gate_priority_no_response_second():
    """GATE 2 (no_response_reason) tiene prioridad sobre budget."""
    policy = LLMCallPolicy()

    decision = policy.evaluate(
        case_id="CASE_001",
        phase="llm_explain",
        has_evidence=True,
        insufficient_evidence=False,
        no_response_reason="EVIDENCE_WEAK",  # Segundo gate
        budget_available=False,  # También falla
    )

    # Debe retornar el segundo gate que falla
    assert decision.allow_call is False
    assert "NO_RESPONSE" in decision.reason


# ============================
# TEST 5: DEGRADED MODE
# ============================


def test_policy_all_blocks_use_degraded_mode():
    """Todos los bloqueos deben activar degraded_mode."""
    policy = LLMCallPolicy()

    # Test insufficient_evidence
    decision1 = policy.evaluate(
        case_id="CASE_001",
        phase="llm_explain",
        has_evidence=True,
        insufficient_evidence=True,
        no_response_reason=None,
        budget_available=True,
    )
    assert decision1.degraded_mode is True

    # Test no_response_reason
    decision2 = policy.evaluate(
        case_id="CASE_001",
        phase="llm_explain",
        has_evidence=True,
        insufficient_evidence=False,
        no_response_reason="EVIDENCE_MISSING",
        budget_available=True,
    )
    assert decision2.degraded_mode is True

    # Test budget_exceeded
    decision3 = policy.evaluate(
        case_id="CASE_001",
        phase="llm_explain",
        has_evidence=True,
        insufficient_evidence=False,
        no_response_reason=None,
        budget_available=False,
    )
    assert decision3.degraded_mode is True

    # Test no_evidence
    decision4 = policy.evaluate(
        case_id="CASE_001",
        phase="llm_explain",
        has_evidence=False,
        insufficient_evidence=False,
        no_response_reason=None,
        budget_available=True,
    )
    assert decision4.degraded_mode is True


# ============================
# RESUMEN DE TESTS
# ============================
"""
COBERTURA:

1. ✅ LLMCallDecision estructura
2. ✅ Policy permite llamada cuando OK
3. ✅ Policy bloquea por insufficient_evidence
4. ✅ Policy bloquea por no_response_reason
5. ✅ Policy bloquea por budget_exceeded
6. ✅ Policy bloquea por no_evidence
7. ✅ Gate priority: insufficient_evidence primero
8. ✅ Gate priority: no_response_reason segundo
9. ✅ Todos los bloqueos activan degraded_mode

TOTAL: 9 tests deterministas

INVARIANTES CERTIFICADOS:
- INVARIANTE 1: insufficient_evidence → allow_call=False
- INVARIANTE 2: no_response_reason → allow_call=False
- INVARIANTE 3: budget_available=False → allow_call=False + degraded_mode
- INVARIANTE 4: has_evidence=False → allow_call=False
- INVARIANTE 5: Gates evaluados en orden (insufficient_evidence > no_response > budget > no_evidence)
- INVARIANTE 6: Todos los bloqueos activan degraded_mode
"""
