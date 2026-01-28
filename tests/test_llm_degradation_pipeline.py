"""
Tests del pipeline completo con degradación de LLM.

Verifica que:
- Pipeline completo funciona sin LLM
- Pipeline con timeout genera output válido
- Sistema NUNCA falla por LLM
- Reporte SIEMPRE se genera

SIN LLM real, SIN red.
Tests end-to-end con mocks.
"""
import pytest
from unittest.mock import patch, Mock

from app.services.llm_executor import execute_llm, generate_degraded_explanation
from app.legal.rule_engine_output import (
    RuleDecision,
    RuleEngineResult,
    RuleEngineResultBuilder
)


# ════════════════════════════════════════════════════════════════
# TEST 1: Pipeline sin LLM genera output válido
# ════════════════════════════════════════════════════════════════

@patch('app.services.llm_executor.is_llm_enabled', return_value=False)
def test_pipeline_sin_llm_output_valido(mock_enabled):
    """
    Verifica que el pipeline completo funciona sin LLM.
    
    Este es el test MÁS CRÍTICO: el sistema DEBE funcionar sin LLM.
    """
    # ════════════════════════════════════════════════════════════════
    # PASO 1: Rule Engine evalúa (SIN LLM)
    # ════════════════════════════════════════════════════════════════
    builder = RuleEngineResultBuilder(case_id="test_case_001", rulebook_version="1.0")
    
    builder.add_rule_decision(RuleDecision(
        rule_id="delay_filing",
        rule_name="Retraso en presentación",
        article="TRLC Art. 5",
        applies=True,
        severity="high",
        confidence="high",
        evidence_required=["informe_tesoreria"],
        evidence_found=["informe_tesoreria"],
        rationale="Insolvencia detectada sin presentación de concurso"
    ))
    
    builder.add_flag("has_critical_findings", True)
    builder.add_flag("requires_legal_review", True)
    
    rule_result = builder.build()
    
    # Verificar que Rule Engine funciona
    assert len(rule_result.triggered_rules) == 1
    assert rule_result.summary_flags["has_critical_findings"] == True
    
    # ════════════════════════════════════════════════════════════════
    # PASO 2: Intentar LLM (está deshabilitado)
    # ════════════════════════════════════════════════════════════════
    llm_result = execute_llm(
        task_name="prosecutor_analysis",
        prompt_system="Analyze",
        prompt_user="Case data"
    )
    
    assert llm_result.degraded == True
    assert llm_result.error_type == "disabled"
    
    # ════════════════════════════════════════════════════════════════
    # PASO 3: Generar explicación degradada
    # ════════════════════════════════════════════════════════════════
    explanation = generate_degraded_explanation(
        task_name="prosecutor_analysis",
        rule_engine_result=rule_result,
        reason="LLM disabled"
    )
    
    # Verificar que explicación se generó
    assert len(explanation) > 100
    assert "Retraso en presentación" in explanation
    assert "TRLC Art. 5" in explanation
    
    # ════════════════════════════════════════════════════════════════
    # PASO 4: Construir output final (SIEMPRE válido)
    # ════════════════════════════════════════════════════════════════
    final_output = {
        "case_id": "test_case_001",
        "rule_engine_result": rule_result,
        "llm_explanation": explanation,
        "llm_used": False,
        "llm_degraded": True,
        "overall_risk": "high",
        "triggered_rules_count": len(rule_result.triggered_rules)
    }
    
    # Verificar output final
    assert final_output["case_id"] == "test_case_001"
    assert final_output["llm_used"] == False
    assert final_output["llm_degraded"] == True
    assert final_output["overall_risk"] == "high"
    assert final_output["triggered_rules_count"] == 1
    assert len(final_output["llm_explanation"]) > 0
    
    print("✅ Pipeline completo sin LLM → OUTPUT VÁLIDO")
    print(f"   Reglas triggered: {final_output['triggered_rules_count']}")
    print(f"   Explicación generada: {len(explanation)} chars")


# ════════════════════════════════════════════════════════════════
# TEST 2: Pipeline con timeout LLM → output válido
# ════════════════════════════════════════════════════════════════

@patch('app.services.llm_executor.is_llm_enabled', return_value=True)
@patch('app.services.llm_executor._call_llm_api')
def test_pipeline_con_timeout_output_valido(mock_call, mock_enabled):
    """
    Verifica que si LLM timeout, el sistema sigue y genera output válido.
    """
    # LLM siempre timeout
    mock_call.side_effect = TimeoutError("LLM timeout")
    
    # ════════════════════════════════════════════════════════════════
    # PASO 1: Rule Engine (funciona siempre)
    # ════════════════════════════════════════════════════════════════
    builder = RuleEngineResultBuilder(case_id="test_case_002")
    builder.add_rule_decision(RuleDecision(
        rule_id="accounting_irregularities",
        rule_name="Irregularidades contables",
        article="TRLC Art. 164",
        applies=True,
        severity="critical",
        confidence="high",
        rationale="Doble contabilidad detectada"
    ))
    rule_result = builder.build()
    
    # ════════════════════════════════════════════════════════════════
    # PASO 2: LLM intenta pero falla
    # ════════════════════════════════════════════════════════════════
    llm_result = execute_llm(
        task_name="auditor_analysis",
        prompt_system="Analyze",
        prompt_user="Case",
        max_retries=1,  # Reducido para test rápido
        timeout_seconds=5
    )
    
    assert llm_result.success == False
    assert llm_result.degraded == True
    assert llm_result.error_type == "timeout"
    
    # ════════════════════════════════════════════════════════════════
    # PASO 3: Degradación automática
    # ════════════════════════════════════════════════════════════════
    explanation = generate_degraded_explanation(
        task_name="auditor_analysis",
        rule_engine_result=rule_result,
        reason=f"LLM timeout after {llm_result.retries_used} retries"
    )
    
    # ════════════════════════════════════════════════════════════════
    # PASO 4: Output final válido
    # ════════════════════════════════════════════════════════════════
    final_output = {
        "case_id": "test_case_002",
        "rule_engine_result": rule_result,
        "llm_explanation": explanation,
        "llm_used": False,
        "llm_degraded": True,
        "llm_error": llm_result.error_message,
        "overall_risk": "critical"
    }
    
    assert final_output["llm_degraded"] == True
    assert final_output["overall_risk"] == "critical"
    assert len(final_output["llm_explanation"]) > 0
    
    print("✅ Pipeline con LLM timeout → OUTPUT VÁLIDO")
    print(f"   LLM timeout detectado y degradado")


# ════════════════════════════════════════════════════════════════
# TEST 3: Sistema NUNCA falla por LLM
# ════════════════════════════════════════════════════════════════

@patch('app.services.llm_executor.is_llm_enabled', return_value=True)
@patch('app.services.llm_executor._call_llm_api')
def test_sistema_nunca_falla_por_llm(mock_call, mock_enabled):
    """
    Verifica que NO SE LANZA EXCEPCIÓN por errores de LLM.
    
    El sistema DEBE ser FAIL SAFE, no FAIL FAST.
    """
    # Simular error catastrófico del LLM
    mock_call.side_effect = Exception("Critical LLM failure!")
    
    # Rule Engine funciona
    builder = RuleEngineResultBuilder(case_id="test_case_003")
    builder.add_rule_decision(RuleDecision(
        rule_id="test_rule",
        rule_name="Test",
        article="Test Art.",
        applies=True,
        severity="medium",
        confidence="medium",
        rationale="Test"
    ))
    rule_result = builder.build()
    
    # LLM falla pero NO lanza excepción
    try:
        llm_result = execute_llm(
            task_name="test_never_fail",
            prompt_system="System",
            prompt_user="User",
            max_retries=0  # Sin retry para test rápido
        )
        
        # Si llegamos aquí, NO se lanzó excepción (CORRECTO)
        assert llm_result.success == False
        assert llm_result.degraded == True
        
        # Sistema continúa y genera output
        explanation = generate_degraded_explanation(
            task_name="test_never_fail",
            rule_engine_result=rule_result,
            reason=llm_result.error_message
        )
        
        final_output = {
            "rule_engine_result": rule_result,
            "llm_explanation": explanation,
            "llm_degraded": True
        }
        
        assert len(final_output["llm_explanation"]) > 0
        
        print("✅ Sistema NO falló por LLM (FAIL SAFE)")
    
    except Exception as e:
        pytest.fail(f"Sistema lanzó excepción por LLM: {e}")


# ════════════════════════════════════════════════════════════════
# TEST 4: Reporte SIEMPRE se genera
# ════════════════════════════════════════════════════════════════

@patch('app.services.llm_executor.is_llm_enabled', return_value=False)
def test_reporte_siempre_se_genera(mock_enabled):
    """
    Verifica que el reporte SIEMPRE se genera, incluso sin LLM.
    """
    # Rule Engine con múltiples reglas
    builder = RuleEngineResultBuilder(case_id="test_case_004")
    
    builder.add_rule_decision(RuleDecision(
        rule_id="rule_1",
        rule_name="Rule 1",
        article="Art. 1",
        applies=True,
        severity="high",
        confidence="high",
        rationale="Reason 1"
    ))
    
    builder.add_rule_decision(RuleDecision(
        rule_id="rule_2",
        rule_name="Rule 2",
        article="Art. 2",
        applies=False,
        severity="low",
        confidence="low",
        rationale="Reason 2"
    ))
    
    builder.add_flag("all_tests_passed", True)
    
    rule_result = builder.build()
    
    # LLM intenta (deshabilitado)
    llm_result = execute_llm(
        task_name="generate_report",
        prompt_system="System",
        prompt_user="User"
    )
    
    # Generar reporte (sin LLM)
    explanation = generate_degraded_explanation(
        task_name="generate_report",
        rule_engine_result=rule_result,
        reason="LLM disabled"
    )
    
    # Construir reporte final
    report = {
        "case_id": "test_case_004",
        "triggered_rules": [r.rule_name for r in rule_result.triggered_rules],
        "discarded_rules": [r.rule_name for r in rule_result.discarded_rules],
        "overall_risk": "high",
        "explanation": explanation,
        "llm_used": not llm_result.degraded,
        "summary_flags": rule_result.summary_flags,
        "generated_at": rule_result.evaluated_at.isoformat()
    }
    
    # Verificar reporte completo
    assert report["case_id"] == "test_case_004"
    assert len(report["triggered_rules"]) == 1
    assert len(report["discarded_rules"]) == 1
    assert report["overall_risk"] == "high"
    assert len(report["explanation"]) > 0
    assert report["llm_used"] == False
    assert "all_tests_passed" in report["summary_flags"]
    
    print("✅ Reporte SIEMPRE se genera")
    print(f"   Triggered: {len(report['triggered_rules'])}")
    print(f"   Discarded: {len(report['discarded_rules'])}")
    print(f"   Flags: {len(report['summary_flags'])}")


# ════════════════════════════════════════════════════════════════
# TEST 5: Degradación parcial (primary falla, fallback éxito)
# ════════════════════════════════════════════════════════════════

@patch('app.services.llm_executor.is_llm_enabled', return_value=True)
@patch('app.services.llm_executor._call_llm_api')
def test_degradacion_parcial(mock_call, mock_enabled):
    """
    Verifica que si primary falla pero fallback éxito, NO es degradación.
    """
    # Primary falla, fallback éxito
    mock_call.side_effect = [
        TimeoutError("Primary timeout"),
        TimeoutError("Primary retry timeout"),
        TimeoutError("Primary final timeout"),
        "Fallback model success"
    ]
    
    builder = RuleEngineResultBuilder(case_id="test_case_005")
    builder.add_rule_decision(RuleDecision(
        rule_id="test",
        rule_name="Test",
        article="Test",
        applies=True,
        severity="low",
        confidence="medium",
        rationale="Test"
    ))
    rule_result = builder.build()
    
    llm_result = execute_llm(
        task_name="test_partial_degradation",
        prompt_system="System",
        prompt_user="User",
        primary_model="gpt-4",
        fallback_model="gpt-3.5-turbo",
        max_retries=2
    )
    
    # Fallback rescató → NO degradación
    assert llm_result.success == True
    assert llm_result.degraded == False
    assert llm_result.model_used == "gpt-3.5-turbo"
    # Verificar que el output incluye el texto original + disclaimer
    assert "Fallback model success" in llm_result.output_text
    assert "IMPORTANTE" in llm_result.output_text  # Disclaimer añadido automáticamente
    
    # Usar output del LLM (NO degradación)
    final_output = {
        "rule_engine_result": rule_result,
        "llm_explanation": llm_result.output_text,
        "llm_used": True,
        "llm_degraded": False,
        "model_used": llm_result.model_used
    }
    
    assert final_output["llm_used"] == True
    assert final_output["llm_degraded"] == False
    assert final_output["model_used"] == "gpt-3.5-turbo"
    # Verificar que el disclaimer está presente en el output final
    assert "IMPORTANTE" in final_output["llm_explanation"]
    
    print("✅ Degradación parcial manejada (fallback rescató con disclaimer automático)")

