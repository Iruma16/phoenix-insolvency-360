"""
Tests para el Agente Prosecutor LLM.

Valida que el agente:
- Se inicializa correctamente
- Puede ejecutarse sin API key (modo deshabilitado)
- Puede ejecutarse con API key (modo habilitado)
- NO sobrescribe datos heurísticos
- Genera la estructura de salida esperada
"""
import pytest
import os

from app.agents_llm.prosecutor_llm import ProsecutorLLMAgent


def test_prosecutor_llm_initialization_without_api_key():
    """Test que el agente se inicializa sin API key (deshabilitado)."""
    print("\n[TEST] Inicialización Prosecutor LLM sin API key...")
    
    # Guardar API key original
    original_key = os.getenv("OPENAI_API_KEY")
    
    # Remover temporalmente
    if original_key:
        del os.environ["OPENAI_API_KEY"]
    
    agent = ProsecutorLLMAgent()
    
    assert agent.enabled is False
    assert agent.llm is None
    
    print("   ✅ Agente inicializado correctamente sin API key (deshabilitado)")
    
    # Restaurar
    if original_key:
        os.environ["OPENAI_API_KEY"] = original_key


def test_prosecutor_llm_disabled_response():
    """Test que el agente devuelve respuesta correcta cuando está deshabilitado."""
    print("\n[TEST] Respuesta del Prosecutor LLM deshabilitado...")
    
    original_key = os.getenv("OPENAI_API_KEY")
    if original_key:
        del os.environ["OPENAI_API_KEY"]
    
    agent = ProsecutorLLMAgent()
    
    result = agent.analyze(
        case_id="test_case",
        risks=[],
        legal_findings=[]
    )
    
    # Verificar estructura
    assert "llm_legal_summary" in result
    assert "llm_legal_reasoning" in result
    assert "llm_recommendations" in result
    assert "llm_agent" in result
    assert "llm_enabled" in result
    
    assert result["llm_enabled"] is False
    assert result["llm_agent"] == "prosecutor"
    assert result["llm_legal_summary"] is None
    assert result["llm_legal_reasoning"] is None
    assert result["llm_recommendations"] is None
    
    print("   ✅ Respuesta deshabilitada correcta")
    
    if original_key:
        os.environ["OPENAI_API_KEY"] = original_key


def test_prosecutor_llm_with_synthetic_data():
    """Test que el agente procesa datos sintéticos correctamente."""
    print("\n[TEST] Prosecutor LLM con datos sintéticos...")
    
    agent = ProsecutorLLMAgent()
    
    # Datos sintéticos
    risks = [
        {"risk_type": "delay_filing", "severity": "high", "explanation": "Retraso en solicitud"},
        {"risk_type": "accounting_red_flags", "severity": "medium", "explanation": "Irregularidades"}
    ]
    
    legal_findings = [
        {
            "finding_type": "delay_filing",
            "severity": "high",
            "legal_basis": [
                {"law": "TRLC", "article": "5", "description": "Deber de solicitud"},
                {"law": "TRLC", "article": "164", "description": "Calificación culpable"}
            ]
        }
    ]
    
    result = agent.analyze(
        case_id="test_synthetic",
        risks=risks,
        legal_findings=legal_findings
    )
    
    # Verificar estructura
    assert "llm_agent" in result
    assert result["llm_agent"] == "prosecutor"
    
    # Si está habilitado, verificar contenido
    if result["llm_enabled"]:
        print("   ✅ Agente habilitado, verificando contenido...")
        assert result["llm_legal_summary"] is not None
        assert result["llm_legal_reasoning"] is not None
        assert result["llm_recommendations"] is not None
        
        assert len(result["llm_legal_summary"]) > 0
        assert len(result["llm_legal_reasoning"]) > 0
        assert len(result["llm_recommendations"]) > 0
        
        print(f"      - Summary: {result['llm_legal_summary'][:80]}...")
        print(f"      - Recommendations: {result['llm_recommendations'][:80]}...")
    else:
        print("   ℹ️  Agente deshabilitado, no hay contenido LLM")
    
    print("   ✅ Datos sintéticos procesados correctamente")


def test_prosecutor_llm_does_not_overwrite_heuristics():
    """Test que el agente NO modifica los datos de entrada."""
    print("\n[TEST] Prosecutor LLM NO sobrescribe datos heurísticos...")
    
    agent = ProsecutorLLMAgent()
    
    original_risks = [{"risk_type": "delay_filing", "severity": "high"}]
    original_findings = [{"finding_type": "delay_filing", "severity": "high"}]
    
    import copy
    risks_copy = copy.deepcopy(original_risks)
    findings_copy = copy.deepcopy(original_findings)
    
    result = agent.analyze(
        case_id="test_no_overwrite",
        risks=original_risks,
        legal_findings=original_findings
    )
    
    # Verificar que los datos NO fueron modificados
    assert original_risks == risks_copy
    assert original_findings == findings_copy
    
    # Verificar que el resultado es independiente
    assert "llm_agent" in result
    
    print("   ✅ Datos heurísticos NO fueron modificados")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

