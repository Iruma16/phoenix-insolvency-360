"""
Tests del LLM Executor con gestión de errores.

Verifica que:
- LLM deshabilitado → degradación inmediata
- Retry funciona para errores transitorios
- Primary falla → fallback funciona
- Todo falla → degradación controlada

SIN LLM real, SIN red.
Mocks estrictos.
"""
from unittest.mock import patch

from app.legal.rule_engine_output import RuleDecision, RuleEngineResultBuilder
from app.services.llm_executor import LLMExecutionResult, execute_llm, generate_degraded_explanation

# ════════════════════════════════════════════════════════════════
# TEST 1: LLM deshabilitado → degradación inmediata
# ════════════════════════════════════════════════════════════════


@patch("app.services.llm_executor.is_llm_enabled", return_value=False)
def test_llm_disabled(mock_enabled):
    """
    Verifica que cuando LLM_ENABLED=false, se activa degradación inmediata.
    """
    result = execute_llm(
        task_name="test_task",
        prompt_system="System",
        prompt_user="User",
        max_retries=2,
        timeout_seconds=10,
    )

    assert result.success == False
    assert result.degraded == True
    assert result.error_type == "disabled"
    assert result.output_text is None
    assert result.retries_used == 0
    assert result.model_used is None

    print("✅ LLM deshabilitado → degradación inmediata")


# ════════════════════════════════════════════════════════════════
# TEST 2: Retry luego éxito
# ════════════════════════════════════════════════════════════════


@patch("app.services.llm_executor.is_llm_enabled", return_value=True)
@patch("app.services.llm_executor._call_llm_api")
def test_retry_then_success(mock_call, mock_enabled):
    """
    Verifica que retry funciona: falla 1 vez, luego éxito.
    """
    # Primer intento: falla con timeout
    # Segundo intento: éxito
    mock_call.side_effect = [TimeoutError("Timeout on first attempt"), "Success output from LLM"]

    result = execute_llm(
        task_name="test_retry",
        prompt_system="System",
        prompt_user="User",
        primary_model="gpt-4",
        max_retries=2,
        timeout_seconds=10,
    )

    assert result.success == True
    assert result.degraded == False
    # Verificar que el output incluye el texto original + disclaimer
    assert "Success output from LLM" in result.output_text
    assert "IMPORTANTE" in result.output_text  # Disclaimer añadido automáticamente
    assert result.retries_used >= 0
    assert result.model_used == "gpt-4"
    assert result.error_type is None

    # Verificar que se llamó 2 veces
    assert mock_call.call_count == 2

    print("✅ Retry funcionó: fallo → éxito (con disclaimer automático)")


# ════════════════════════════════════════════════════════════════
# TEST 3: Primary falla → fallback éxito
# ════════════════════════════════════════════════════════════════


@patch("app.services.llm_executor.is_llm_enabled", return_value=True)
@patch("app.services.llm_executor._call_llm_api")
def test_primary_fail_fallback_success(mock_call, mock_enabled):
    """
    Verifica que si primary falla completamente, fallback lo rescata.
    """
    # Simulamos 3 intentos con primary (max_retries=2)
    # Luego fallback tiene éxito
    mock_call.side_effect = [
        TimeoutError("Primary attempt 1"),
        TimeoutError("Primary attempt 2"),
        TimeoutError("Primary attempt 3"),
        "Fallback model success",  # ← Fallback rescata
    ]

    result = execute_llm(
        task_name="test_fallback",
        prompt_system="System",
        prompt_user="User",
        primary_model="gpt-4",
        fallback_model="gpt-3.5-turbo",
        max_retries=2,
        timeout_seconds=10,
    )

    assert result.success == True
    assert result.degraded == False
    # Verificar que el output incluye el texto original + disclaimer
    assert "Fallback model success" in result.output_text
    assert "IMPORTANTE" in result.output_text  # Disclaimer añadido automáticamente
    assert result.model_used == "gpt-3.5-turbo"

    print("✅ Primary falló → fallback rescató (con disclaimer automático)")


# ════════════════════════════════════════════════════════════════
# TEST 4: Todo falla → degradación
# ════════════════════════════════════════════════════════════════


@patch("app.services.llm_executor.is_llm_enabled", return_value=True)
@patch("app.services.llm_executor._call_llm_api")
def test_all_fail_degrades(mock_call, mock_enabled):
    """
    Verifica que si TODO falla (primary + fallback), se activa degradación.
    """
    # Todos los intentos fallan
    mock_call.side_effect = TimeoutError("All attempts timeout")

    result = execute_llm(
        task_name="test_all_fail",
        prompt_system="System",
        prompt_user="User",
        primary_model="gpt-4",
        fallback_model="gpt-3.5-turbo",
        max_retries=2,
        timeout_seconds=10,
    )

    assert result.success == False
    assert result.degraded == True
    assert result.error_type == "timeout"
    assert result.output_text is None
    assert result.model_used is None
    assert "All models failed" in result.error_message

    print("✅ Todo falló → degradación controlada")


# ════════════════════════════════════════════════════════════════
# TEST 5: API error NO reintentar
# ════════════════════════════════════════════════════════════════


@patch("app.services.llm_executor.is_llm_enabled", return_value=True)
@patch("app.services.llm_executor._call_llm_api")
def test_api_error_no_retry(mock_call, mock_enabled):
    """
    Verifica que errores de API (4xx) NO se reintentan.
    """
    # Error de API (no transitorio)
    mock_call.side_effect = Exception("Invalid API key")

    result = execute_llm(
        task_name="test_api_error",
        prompt_system="System",
        prompt_user="User",
        primary_model="gpt-4",
        max_retries=2,
        timeout_seconds=10,
    )

    # Solo se intentó 1 vez (no retry)
    assert mock_call.call_count <= 2  # Primary 1 intento + fallback 1 intento

    print("✅ API error NO reintentó innecesariamente")


# ════════════════════════════════════════════════════════════════
# TEST 6: Latency tracking
# ════════════════════════════════════════════════════════════════


@patch("app.services.llm_executor.is_llm_enabled", return_value=True)
@patch("app.services.llm_executor._call_llm_api")
def test_latency_tracking(mock_call, mock_enabled):
    """
    Verifica que se trackea latency correctamente.
    """
    mock_call.return_value = "Success"

    result = execute_llm(task_name="test_latency", prompt_system="System", prompt_user="User")

    assert result.latency_ms is not None
    assert result.latency_ms >= 0

    print(f"✅ Latency tracked: {result.latency_ms:.2f}ms")


# ════════════════════════════════════════════════════════════════
# TEST 7: Task name logging
# ════════════════════════════════════════════════════════════════


@patch("app.services.llm_executor.is_llm_enabled", return_value=True)
@patch("app.services.llm_executor._call_llm_api")
def test_task_name_logged(mock_call, mock_enabled):
    """
    Verifica que task_name se registra en el resultado.
    """
    mock_call.return_value = "Success"

    result = execute_llm(
        task_name="prosecutor_analysis", prompt_system="System", prompt_user="User"
    )

    assert result.task_name == "prosecutor_analysis"

    print("✅ Task name registrado correctamente")


# ════════════════════════════════════════════════════════════════
# TEST 8: Degraded explanation generation
# ════════════════════════════════════════════════════════════════


def test_generate_degraded_explanation():
    """
    Verifica que se puede generar explicación sin LLM.
    """
    # Crear RuleEngineResult mock
    builder = RuleEngineResultBuilder(case_id="test_case")
    builder.add_rule_decision(
        RuleDecision(
            rule_id="delay_filing",
            rule_name="Retraso en presentación",
            article="TRLC Art. 5",
            applies=True,
            severity="high",
            confidence="high",
            rationale="Test rationale",
        )
    )
    builder.add_flag("critical_findings", True)
    result = builder.build()

    # Generar explicación degradada
    explanation = generate_degraded_explanation(
        task_name="test_task", rule_engine_result=result, reason="LLM timeout"
    )

    # Verificar contenido
    assert "SIN MODELO DE LENGUAJE" in explanation
    assert "LLM timeout" in explanation
    assert "Retraso en presentación" in explanation
    assert "TRLC Art. 5" in explanation
    assert "high" in explanation.lower()
    assert "IMPORTANTE" in explanation

    print("✅ Explicación degradada generada correctamente")
    print(f"   Longitud: {len(explanation)} caracteres")


# ════════════════════════════════════════════════════════════════
# TEST 9: Sin reglas triggered
# ════════════════════════════════════════════════════════════════


def test_degraded_explanation_no_rules():
    """
    Verifica explicación degradada cuando no hay reglas triggered.
    """
    builder = RuleEngineResultBuilder(case_id="test_case")
    result = builder.build()  # Sin reglas

    explanation = generate_degraded_explanation(
        task_name="test_task", rule_engine_result=result, reason="LLM disabled"
    )

    assert "Ninguna regla aplicó" in explanation
    assert "SIN MODELO DE LENGUAJE" in explanation

    print("✅ Explicación degradada sin reglas funcionó")


# ════════════════════════════════════════════════════════════════
# TEST 10: Result structure validation
# ════════════════════════════════════════════════════════════════


def test_result_structure():
    """
    Verifica que LLMExecutionResult tiene todos los campos necesarios.
    """
    from datetime import datetime

    result = LLMExecutionResult(
        success=True,
        output_text="Test output",
        error_type=None,
        error_message=None,
        retries_used=1,
        model_used="gpt-4",
        degraded=False,
        latency_ms=150.5,
        task_name="test_task",
    )

    assert result.success == True
    assert result.output_text == "Test output"
    assert result.retries_used == 1
    assert result.model_used == "gpt-4"
    assert result.degraded == False
    assert result.task_name == "test_task"
    assert isinstance(result.executed_at, datetime)

    print("✅ Result structure válida")
