"""
Tests del contrato del LLM Explainer.

Verifica que:
- Input con clave extra → falla
- Input válido → pasa
- Output structure es correcta
- Separación DECIDE vs EXPLICA se mantiene

SIN LLM real, SIN red.
Deterministas y rápidos.
"""
import pytest
from datetime import datetime

from app.legal.rule_engine_output import RuleDecision
from app.agents.llm_explainer.schema import (
    LegalExplanationInput,
    LegalExplanationOutput,
    SYSTEM_PROMPT_EXPLAINER,
    build_explanation_prompt
)


# ════════════════════════════════════════════════════════════════
# TEST 1: Input válido se construye correctamente
# ════════════════════════════════════════════════════════════════

def test_input_valido_construye():
    """
    Verifica que un input válido se construye sin errores.
    """
    decision = RuleDecision(
        rule_id="rule_001",
        rule_name="Test Rule",
        article="TRLC Art. 5",
        applies=True,
        severity="high",
        confidence="high",
        rationale="Test"
    )
    
    input_data = LegalExplanationInput(
        case_id="case_001",
        rules_triggered=[decision],
        risks_detected=["delay_filing"],
        missing_evidence=["balance"],
        tone="neutral",
        disclaimer_required=True
    )
    
    assert input_data.case_id == "case_001"
    assert len(input_data.rules_triggered) == 1
    assert input_data.tone == "neutral"
    assert input_data.disclaimer_required == True
    
    print("✅ Input válido construido correctamente")


# ════════════════════════════════════════════════════════════════
# TEST 2: Input con clave extra falla (extra="forbid")
# ════════════════════════════════════════════════════════════════

def test_input_con_clave_extra_falla():
    """
    Verifica que extra="forbid" rechaza claves no definidas.
    
    Esto es CRÍTICO para el contrato.
    """
    from pydantic import ValidationError
    
    with pytest.raises(ValidationError) as exc_info:
        LegalExplanationInput(
            case_id="case_001",
            rules_triggered=[],
            clave_no_permitida="valor"  # ❌ EXTRA KEY
        )
    
    error = exc_info.value
    assert len(error.errors()) > 0
    
    first_error = error.errors()[0]
    assert "extra" in first_error["type"] or "unexpected" in first_error["msg"].lower()
    
    print(f"✅ Clave extra rechazada: {first_error['msg']}")


# ════════════════════════════════════════════════════════════════
# TEST 3: Output structure valida
# ════════════════════════════════════════════════════════════════

def test_output_structure_valida():
    """
    Verifica que LegalExplanationOutput tiene la estructura correcta.
    """
    output = LegalExplanationOutput(
        case_id="case_001",
        explanation="Test explanation text",
        disclaimer="Legal disclaimer text",
        generated_at=datetime.utcnow().isoformat(),
        tokens_used=150
    )
    
    assert output.case_id == "case_001"
    assert output.explanation == "Test explanation text"
    assert output.disclaimer == "Legal disclaimer text"
    assert output.tokens_used == 150
    
    print("✅ Output structure validada")


# ════════════════════════════════════════════════════════════════
# TEST 4: System prompt contiene reglas explícitas
# ════════════════════════════════════════════════════════════════

def test_system_prompt_reglas_explicitas():
    """
    Verifica que el system prompt contiene reglas explícitas.
    """
    # Verificar prohibiciones
    assert "NO tomes decisiones" in SYSTEM_PROMPT_EXPLAINER
    assert "NO evalúes" in SYSTEM_PROMPT_EXPLAINER
    assert "NO cambies severidad" in SYSTEM_PROMPT_EXPLAINER
    assert "NO agregues reglas" in SYSTEM_PROMPT_EXPLAINER
    
    # Verificar obligaciones
    assert "SOLO explica" in SYSTEM_PROMPT_EXPLAINER
    assert "Cita artículos" in SYSTEM_PROMPT_EXPLAINER or "cita" in SYSTEM_PROMPT_EXPLAINER.lower()
    
    print("✅ System prompt contiene reglas explícitas")
    print(f"   Longitud: {len(SYSTEM_PROMPT_EXPLAINER)} caracteres")


# ════════════════════════════════════════════════════════════════
# TEST 5: Build prompt incluye todas las secciones
# ════════════════════════════════════════════════════════════════

def test_build_prompt_secciones_completas():
    """
    Verifica que el prompt construido tiene todas las secciones necesarias.
    """
    decision = RuleDecision(
        rule_id="delay_filing",
        rule_name="Retraso presentación",
        article="TRLC Art. 5",
        applies=True,
        severity="high",
        confidence="high",
        rationale="Insolvencia detectada sin presentación"
    )
    
    input_data = LegalExplanationInput(
        case_id="case_test",
        rules_triggered=[decision],
        risks_detected=["delay_filing", "doc_gap"],
        missing_evidence=["balance", "acta"],
        tone="technical",
        max_tokens=300
    )
    
    prompt = build_explanation_prompt(input_data)
    
    # Verificar secciones
    assert "Caso ID: case_test" in prompt
    assert "REGLAS APLICADAS" in prompt
    assert "RIESGOS DETECTADOS" in prompt
    assert "EVIDENCIA FALTANTE" in prompt
    assert "INSTRUCCIONES" in prompt
    
    # Verificar contenido
    assert "Retraso presentación" in prompt
    assert "TRLC Art. 5" in prompt
    assert "high" in prompt
    assert "delay_filing" in prompt
    assert "balance" in prompt
    
    print("✅ Prompt incluye todas las secciones")


# ════════════════════════════════════════════════════════════════
# TEST 6: Tone afecta instrucciones del prompt
# ════════════════════════════════════════════════════════════════

def test_tone_afecta_prompt():
    """
    Verifica que el tone se refleja en las instrucciones del prompt.
    """
    decision = RuleDecision(
        rule_id="test",
        rule_name="Test",
        article="Art. 1",
        applies=True,
        severity="low",
        confidence="medium",
        rationale="Test"
    )
    
    # Tone: technical
    input_technical = LegalExplanationInput(
        case_id="case_001",
        rules_triggered=[decision],
        tone="technical"
    )
    prompt_technical = build_explanation_prompt(input_technical)
    assert "technical" in prompt_technical
    
    # Tone: client_friendly
    input_friendly = LegalExplanationInput(
        case_id="case_001",
        rules_triggered=[decision],
        tone="client_friendly"
    )
    prompt_friendly = build_explanation_prompt(input_friendly)
    assert "client_friendly" in prompt_friendly
    
    print("✅ Tone se refleja en el prompt")


# ════════════════════════════════════════════════════════════════
# TEST 7: Disclaimer required se incluye en prompt
# ════════════════════════════════════════════════════════════════

def test_disclaimer_required_en_prompt():
    """
    Verifica que disclaimer_required aparece en las instrucciones.
    """
    input_with_disclaimer = LegalExplanationInput(
        case_id="case_001",
        disclaimer_required=True
    )
    
    prompt = build_explanation_prompt(input_with_disclaimer)
    assert "disclaimer" in prompt.lower()
    
    print("✅ Disclaimer required incluido en prompt")


# ════════════════════════════════════════════════════════════════
# TEST 8: Sin reglas triggered genera prompt correcto
# ════════════════════════════════════════════════════════════════

def test_sin_reglas_triggered():
    """
    Verifica que si no hay reglas triggered, el prompt lo indica.
    """
    input_no_rules = LegalExplanationInput(
        case_id="case_001",
        rules_triggered=[],  # ← Sin reglas
        risks_detected=[],
        missing_evidence=[]
    )
    
    prompt = build_explanation_prompt(input_no_rules)
    
    assert "Ninguna regla aplicó" in prompt or "Ninguna" in prompt
    assert "Ninguno" in prompt  # Para riesgos
    
    print("✅ Prompt correcto cuando no hay reglas")


# ════════════════════════════════════════════════════════════════
# TEST 9: Max tokens se limita correctamente
# ════════════════════════════════════════════════════════════════

def test_max_tokens_en_prompt():
    """
    Verifica que max_tokens aparece en las instrucciones del prompt.
    """
    input_data = LegalExplanationInput(
        case_id="case_001",
        max_tokens=250
    )
    
    prompt = build_explanation_prompt(input_data)
    assert "250" in prompt or "250 tokens" in prompt.lower()
    
    print("✅ Max tokens incluido en prompt")


# ════════════════════════════════════════════════════════════════
# TEST 10: Output no puede tener campos extra
# ════════════════════════════════════════════════════════════════

def test_output_no_campos_extra():
    """
    Verifica que LegalExplanationOutput rechaza campos extra.
    """
    from pydantic import ValidationError
    
    with pytest.raises(ValidationError):
        LegalExplanationOutput(
            case_id="case_001",
            explanation="Test",
            generated_at=datetime.utcnow().isoformat(),
            campo_extra="no permitido"  # ❌ EXTRA
        )
    
    print("✅ Output rechaza campos extra")

