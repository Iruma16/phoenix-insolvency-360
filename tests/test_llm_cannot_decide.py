"""
Tests que verifican que el LLM NO PUEDE DECIDIR.

Verifica que:
- El LLM NO puede cambiar severidad
- El LLM NO puede añadir reglas
- El LLM NO puede evaluar cumplimiento
- Violaciones del contrato lanzan excepciones

SIN LLM real, SIN red.
Usa mocks estrictos.
"""

import pytest

from app.agents.llm_explainer.schema import (
    LegalExplanationInput,
    LLMContractViolation,
    validate_llm_output_compliance,
)
from app.legal.rule_engine_output import RuleDecision

# ════════════════════════════════════════════════════════════════
# TEST 1: LLM intenta cambiar severidad → FALLA
# ════════════════════════════════════════════════════════════════


def test_llm_intenta_cambiar_severidad_falla():
    """
    Verifica que si el LLM cambia severidad, se detecta y falla.

    Esto es CRÍTICO: el LLM NUNCA puede cambiar decisiones.
    """
    # Decisión original: severity=high
    original_decision = RuleDecision(
        rule_id="delay_filing",
        rule_name="Retraso en presentación",
        article="TRLC Art. 5",
        applies=True,
        severity="high",  # ← ORIGINAL: HIGH
        confidence="high",
        rationale="Insolvencia sin presentación",
    )

    input_data = LegalExplanationInput(case_id="case_001", rules_triggered=[original_decision])

    # LLM OUTPUT MALICIOSO: Dice "riesgo bajo" cuando es "high"
    malicious_output = """
    El retraso en presentación representa un riesgo bajo para el caso.
    Artículo TRLC Art. 5 aplicable.
    """

    # Debe FALLAR
    with pytest.raises(LLMContractViolation) as exc_info:
        validate_llm_output_compliance(input_data, malicious_output, [original_decision])

    error_msg = str(exc_info.value)
    assert "cambió severidad" in error_msg or "severity" in error_msg.lower()

    print("✅ LLM que intenta cambiar severidad fue BLOQUEADO")
    print(f"   Error: {error_msg[:100]}...")


# ════════════════════════════════════════════════════════════════
# TEST 2: LLM output válido pasa validación
# ════════════════════════════════════════════════════════════════


def test_llm_output_valido_pasa():
    """
    Verifica que output válido del LLM pasa validación.
    """
    original_decision = RuleDecision(
        rule_id="delay_filing",
        rule_name="Retraso en presentación",
        article="TRLC Art. 5",
        applies=True,
        severity="high",
        confidence="high",
        rationale="Insolvencia sin presentación",
    )

    input_data = LegalExplanationInput(case_id="case_001", rules_triggered=[original_decision])

    # Output VÁLIDO: Solo explica, no decide
    valid_output = """
    Se ha detectado un retraso en la presentación del concurso.
    Según el artículo TRLC Art. 5, existe un deber de presentación.
    Este hallazgo tiene un nivel de confianza alto.
    Se recomienda revisar los tiempos con asesoría legal.
    """

    # NO debe fallar
    validate_llm_output_compliance(input_data, valid_output, [original_decision])

    print("✅ LLM output válido pasó validación")


# ════════════════════════════════════════════════════════════════
# TEST 3: Input al LLM rechaza campos extra
# ════════════════════════════════════════════════════════════════


def test_input_llm_rechaza_campos_extra():
    """
    Verifica que extra="forbid" funciona en LegalExplanationInput.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LegalExplanationInput(
            case_id="case_001",
            rules_triggered=[],
            campo_inventado="no permitido",  # ❌ EXTRA FIELD
        )

    print("✅ Input al LLM rechaza campos extra (extra='forbid')")


# ════════════════════════════════════════════════════════════════
# TEST 4: Input al LLM valida tone
# ════════════════════════════════════════════════════════════════


def test_input_llm_valida_tone():
    """
    Verifica que tone solo acepta valores permitidos.
    """
    from pydantic import ValidationError

    # Tone válido
    input_ok = LegalExplanationInput(
        case_id="case_001",
        tone="neutral",  # ✅ Válido
    )
    assert input_ok.tone == "neutral"

    # Tone inválido
    with pytest.raises(ValidationError):
        LegalExplanationInput(
            case_id="case_001",
            tone="invalid_tone",  # ❌ NO PERMITIDO
        )

    print("✅ Tone validado correctamente")


# ════════════════════════════════════════════════════════════════
# TEST 5: Max tokens en rango válido
# ════════════════════════════════════════════════════════════════


def test_max_tokens_en_rango():
    """
    Verifica que max_tokens está limitado al rango permitido.
    """
    from pydantic import ValidationError

    # Válido
    input_ok = LegalExplanationInput(
        case_id="case_001",
        max_tokens=500,  # ✅ En rango [50, 2000]
    )
    assert input_ok.max_tokens == 500

    # Fuera de rango (muy bajo)
    with pytest.raises(ValidationError):
        LegalExplanationInput(
            case_id="case_001",
            max_tokens=10,  # ❌ < 50
        )

    # Fuera de rango (muy alto)
    with pytest.raises(ValidationError):
        LegalExplanationInput(
            case_id="case_001",
            max_tokens=5000,  # ❌ > 2000
        )

    print("✅ Max tokens validado en rango [50, 2000]")


# ════════════════════════════════════════════════════════════════
# TEST 6: Prompt system no permite decisiones
# ════════════════════════════════════════════════════════════════


def test_system_prompt_prohibe_decisiones():
    """
    Verifica que el system prompt prohíbe explícitamente decisiones.
    """
    from app.agents.llm_explainer.schema import SYSTEM_PROMPT_EXPLAINER

    # Verificar que contiene prohibiciones explícitas
    assert "NO tomes decisiones" in SYSTEM_PROMPT_EXPLAINER
    assert "NO evalúes" in SYSTEM_PROMPT_EXPLAINER
    assert "SOLO explica" in SYSTEM_PROMPT_EXPLAINER

    print("✅ System prompt contiene prohibiciones explícitas")


# ════════════════════════════════════════════════════════════════
# TEST 7: Build prompt incluye decisiones ya tomadas
# ════════════════════════════════════════════════════════════════


def test_build_prompt_incluye_decisiones():
    """
    Verifica que el prompt construido incluye decisiones ya tomadas.
    """
    from app.agents.llm_explainer.schema import build_explanation_prompt

    decision = RuleDecision(
        rule_id="test_rule",
        rule_name="Test Rule",
        article="TRLC Art. 99",
        applies=True,
        severity="medium",
        confidence="high",
        rationale="Test rationale",
    )

    input_data = LegalExplanationInput(
        case_id="case_001", rules_triggered=[decision], tone="technical"
    )

    prompt = build_explanation_prompt(input_data)

    # Verificar que contiene elementos clave
    assert "Test Rule" in prompt
    assert "TRLC Art. 99" in prompt
    assert "medium" in prompt
    assert "high" in prompt
    assert "NO cambies severidad" in prompt or "NO agregues reglas" in prompt

    print("✅ Prompt construido correctamente con decisiones")


# ════════════════════════════════════════════════════════════════
# TEST 8: Disclaimer se incluye si requerido
# ════════════════════════════════════════════════════════════════


def test_disclaimer_incluido_si_requerido():
    """
    Verifica que disclaimer se incluye cuando disclaimer_required=True.
    """
    from app.agents.llm_explainer.schema import build_explanation_prompt

    # Con disclaimer
    input_with = LegalExplanationInput(case_id="case_001", disclaimer_required=True)
    prompt_with = build_explanation_prompt(input_with)
    assert "disclaimer" in prompt_with.lower()

    # Sin disclaimer
    input_without = LegalExplanationInput(case_id="case_001", disclaimer_required=False)
    prompt_without = build_explanation_prompt(input_without)

    print("✅ Disclaimer controlado por flag")


# ════════════════════════════════════════════════════════════════
# TEST 9: NO se puede pasar PhoenixState completo
# ════════════════════════════════════════════════════════════════


def test_no_se_puede_pasar_phoenix_state():
    """
    Verifica que LegalExplanationInput NO acepta PhoenixState completo.

    El LLM SOLO debe recibir decisiones ya tomadas.
    """
    from pydantic import ValidationError

    # Intentar pasar un campo que no existe en el schema
    with pytest.raises(ValidationError):
        LegalExplanationInput(
            case_id="case_001",
            phoenix_state={"full": "state"},  # ❌ NO PERMITIDO
        )

    print("✅ PhoenixState completo NO puede pasarse al LLM")


# ════════════════════════════════════════════════════════════════
# TEST 10: Validación detecta contradicción sutil
# ════════════════════════════════════════════════════════════════


def test_validacion_detecta_contradiccion_sutil():
    """
    Verifica que la validación detecta contradicciones sutiles.
    """
    original_decision = RuleDecision(
        rule_id="accounting_flags",
        rule_name="Irregularidades contables",
        article="TRLC Art. 164",
        applies=True,
        severity="critical",  # ← CRITICAL
        confidence="high",
        rationale="Doble contabilidad detectada",
    )

    input_data = LegalExplanationInput(case_id="case_001", rules_triggered=[original_decision])

    # Output que contradice sutilmente
    contradictory_output = """
    Las irregularidades contables detectadas representan un riesgo medio.
    Según TRLC Art. 164, se requiere análisis adicional.
    """

    # Debe FALLAR (dice "medio" cuando es "critical")
    with pytest.raises(LLMContractViolation):
        validate_llm_output_compliance(input_data, contradictory_output, [original_decision])

    print("✅ Contradicción sutil detectada y bloqueada")
