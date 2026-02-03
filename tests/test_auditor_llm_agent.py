"""
Tests para el Agente Auditor LLM.

Valida que el agente:
- Se inicializa correctamente
- Puede ejecutarse sin API key (modo deshabilitado)
- Puede ejecutarse con API key (modo habilitado)
- NO sobrescribe datos heurísticos
- Genera la estructura de salida esperada
"""
import os

import pytest

from app.agents_llm.auditor_llm import AuditorLLMAgent


def test_auditor_llm_initialization_without_api_key():
    """Test que el agente se inicializa sin API key (deshabilitado)."""
    print("\n[TEST] Inicialización Auditor LLM sin API key...")

    # Guardar API key original
    original_key = os.getenv("OPENAI_API_KEY")

    # Remover temporalmente
    if original_key:
        del os.environ["OPENAI_API_KEY"]

    agent = AuditorLLMAgent()

    assert agent.enabled is False, "El agente debería estar deshabilitado sin API key"
    assert agent.llm is None, "El LLM no debería inicializarse sin API key"

    print("   ✅ Agente inicializado correctamente sin API key (deshabilitado)")

    # Restaurar API key
    if original_key:
        os.environ["OPENAI_API_KEY"] = original_key


def test_auditor_llm_disabled_response():
    """Test que el agente devuelve respuesta correcta cuando está deshabilitado."""
    print("\n[TEST] Respuesta del Auditor LLM deshabilitado...")

    # Guardar y remover API key
    original_key = os.getenv("OPENAI_API_KEY")
    if original_key:
        del os.environ["OPENAI_API_KEY"]

    agent = AuditorLLMAgent()

    # Ejecutar análisis
    result = agent.analyze(case_id="test_case", documents=[], timeline=[], risks=[])

    # Verificar estructura
    assert "llm_summary" in result
    assert "llm_reasoning" in result
    assert "llm_confidence" in result
    assert "llm_agent" in result
    assert "llm_enabled" in result

    assert result["llm_enabled"] is False
    assert result["llm_agent"] == "auditor"
    assert result["llm_summary"] is None
    assert result["llm_reasoning"] is None
    assert result["llm_confidence"] is None

    print("   ✅ Respuesta deshabilitada correcta")

    # Restaurar API key
    if original_key:
        os.environ["OPENAI_API_KEY"] = original_key


def test_auditor_llm_with_empty_data():
    """Test que el agente maneja datos vacíos sin romper."""
    print("\n[TEST] Auditor LLM con datos vacíos...")

    agent = AuditorLLMAgent()

    # Ejecutar con datos vacíos
    result = agent.analyze(case_id="test_empty", documents=[], timeline=[], risks=[])

    # Verificar estructura (independiente de si está habilitado o no)
    assert "llm_agent" in result
    assert result["llm_agent"] == "auditor"
    assert "llm_enabled" in result

    print(f"   ✅ Agente maneja datos vacíos (enabled={result['llm_enabled']})")


def test_auditor_llm_with_synthetic_data():
    """Test que el agente procesa datos sintéticos correctamente."""
    print("\n[TEST] Auditor LLM con datos sintéticos...")

    agent = AuditorLLMAgent()

    # Datos sintéticos
    documents = [
        {"doc_id": "doc1", "doc_type": "balance", "filename": "balance_2024.pdf"},
        {"doc_id": "doc2", "doc_type": "acta", "filename": "acta_junta.pdf"},
    ]

    timeline = [
        {"date": "2024-01-15", "description": "Junta extraordinaria"},
        {"date": "2024-02-20", "description": "Presentación de balance"},
    ]

    risks = [
        {"risk_type": "delay_filing", "severity": "high"},
        {"risk_type": "document_inconsistency", "severity": "medium"},
    ]

    result = agent.analyze(
        case_id="test_synthetic", documents=documents, timeline=timeline, risks=risks
    )

    # Verificar estructura
    assert "llm_agent" in result
    assert result["llm_agent"] == "auditor"

    # Si está habilitado, verificar que hay contenido
    if result["llm_enabled"]:
        print("   ✅ Agente habilitado, verificando contenido...")
        assert result["llm_summary"] is not None
        assert result["llm_reasoning"] is not None
        assert result["llm_confidence"] is not None

        # Verificar que no son strings vacíos
        assert len(result["llm_summary"]) > 0
        assert len(result["llm_reasoning"]) > 0
        assert len(result["llm_confidence"]) > 0

        print(f"      - Summary: {result['llm_summary'][:80]}...")
        print(f"      - Confidence: {result['llm_confidence'][:50]}...")
    else:
        print("   ℹ️  Agente deshabilitado, no hay contenido LLM")

    print("   ✅ Datos sintéticos procesados correctamente")


def test_auditor_llm_does_not_overwrite_heuristics():
    """Test que el agente NO modifica los datos de entrada."""
    print("\n[TEST] Auditor LLM NO sobrescribe datos heurísticos...")

    agent = AuditorLLMAgent()

    # Datos originales
    original_documents = [{"doc_id": "doc1", "doc_type": "balance"}]
    original_timeline = [{"date": "2024-01-01", "description": "Evento"}]
    original_risks = [{"risk_type": "delay_filing", "severity": "high"}]

    # Copias para comparar
    import copy

    documents_copy = copy.deepcopy(original_documents)
    timeline_copy = copy.deepcopy(original_timeline)
    risks_copy = copy.deepcopy(original_risks)

    # Ejecutar análisis
    result = agent.analyze(
        case_id="test_no_overwrite",
        documents=original_documents,
        timeline=original_timeline,
        risks=original_risks,
    )

    # Verificar que los datos originales NO fueron modificados
    assert original_documents == documents_copy
    assert original_timeline == timeline_copy
    assert original_risks == risks_copy

    # Verificar que el resultado es independiente
    assert "llm_agent" in result
    assert result not in [original_documents, original_timeline, original_risks]

    print("   ✅ Datos heurísticos NO fueron modificados")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
