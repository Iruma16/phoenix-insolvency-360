"""
Smoke test ligero para el Agente Auditor con RAG.

Mock del RAG para evitar dependencias de vectorstore/BD.
"""
import pytest
from unittest.mock import patch, MagicMock

from app.agents.agent_1_auditor.runner import run_auditor
from app.agents.agent_1_auditor.schema import AuditorResult
import json


def test_auditor_with_mocked_rag():
    """Test básico que verifica que el auditor funciona con RAG mockeado."""
    print("🧪 Ejecutando smoke test del Auditor con RAG...")
    
    # Mock de la sesión de BD
    mock_db = MagicMock()
    
    # Mock del service RAG para devolver contexto simulado
    with patch('app.agents.agent_1_auditor.runner.query_case_rag') as mock_rag:
        mock_rag.return_value = "Este es un contexto simulado recuperado del RAG. Contiene información sobre documentos del caso."
        
        # Ejecutar auditor
        result, auditor_fallback = run_auditor(
            case_id="test-case-123",
            question="¿Qué documentos existen en el caso?",
            db=mock_db,
        )
        
        # Verificar que es una instancia de AuditorResult
        assert isinstance(result, AuditorResult)
        assert isinstance(auditor_fallback, bool)
        
        # Verificar que es serializable
        result_dict = result.dict()
        json_str = json.dumps(result_dict)
        
        print("✅ Resultado serializable a JSON")
        print(f"📊 Resultado: {json_str}")
        
        # Verificar estructura
        assert "summary" in result_dict
        assert "risks" in result_dict
        assert "next_actions" in result_dict
        assert isinstance(result_dict["risks"], list)
        assert isinstance(result_dict["next_actions"], list)
        
        # Verificar que se llamó al RAG
        mock_rag.assert_called_once()
        call_args = mock_rag.call_args
        assert call_args.kwargs["case_id"] == "test-case-123"
        assert call_args.kwargs["query"] == "¿Qué documentos existen en el caso?"
        
        print("✅ Estructura del resultado correcta")
        print("✅ RAG fue llamado correctamente")
        print("✅ Smoke test completado")


def test_auditor_with_empty_context():
    """Test que verifica comportamiento cuando no hay contexto."""
    print("🧪 Ejecutando test con contexto vacío...")
    
    mock_db = MagicMock()
    
    with patch('app.agents.agent_1_auditor.runner.query_case_rag') as mock_rag:
        mock_rag.return_value = ""  # Contexto vacío
        
        result, auditor_fallback = run_auditor(
            case_id="test-case-456",
            question="¿Qué hay en el caso?",
            db=mock_db,
        )
        
        # Verificar que detectó fallback
        assert auditor_fallback is True
        
        result_dict = result.dict()
        
        # Verificar que maneja correctamente contexto vacío
        assert "summary" in result_dict
        assert "risks" in result_dict
        assert "next_actions" in result_dict
        
        # Debe indicar que no hay contexto
        assert "no se pudo recuperar" in result_dict["summary"].lower() or \
               "insuficiente" in result_dict["summary"].lower()
        
        print("✅ Manejo correcto de contexto vacío")
        print(f"✅ Fallback detectado correctamente: {auditor_fallback}")
        print("✅ Test completado")


if __name__ == "__main__":
    # Ejecutar sin pytest si se llama directamente
    try:
        test_auditor_with_mocked_rag()
        print("\n" + "="*60 + "\n")
        test_auditor_with_empty_context()
    except ImportError as e:
        print(f"⚠️  Error de importación (puede necesitar pytest): {e}")
        print("Ejecuta con: python -m pytest tests/manual/test_auditor_with_rag.py -v")

