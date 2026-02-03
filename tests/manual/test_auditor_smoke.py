"""
Smoke test ligero para el Agente Auditor.
No requiere base de datos ni RAG.
"""
import json
from unittest.mock import MagicMock, patch

from app.agents.agent_1_auditor.runner import run_auditor


def test_auditor_smoke():
    """Test básico que verifica que el auditor funciona."""
    print("🧪 Ejecutando smoke test del Auditor...")

    test_text = "Este es un documento de prueba para validar el funcionamiento del agente auditor."

    mock_db = MagicMock()

    with patch("app.agents.agent_1_auditor.runner.query_case_rag") as mock_rag:
        mock_rag.return_value = "Contexto simulado para el test"

        result, auditor_fallback = run_auditor(case_id="test-case", question=test_text, db=mock_db)

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

    print("✅ Estructura del resultado correcta")
    print("✅ Smoke test completado")


if __name__ == "__main__":
    test_auditor_smoke()
