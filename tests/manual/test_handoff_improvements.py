"""
Tests de regresión para mejoras del handoff: validación, fallback, contexto.

Mockea RAG, LLM y BD para evitar dependencias pesadas.
"""
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.agents.agent_1_auditor.runner import run_auditor
from app.agents.agent_1_auditor.schema import AuditorResult
from app.agents.agent_2_prosecutor.runner import run_prosecutor_from_auditor
from app.agents.agent_2_prosecutor.schema import ProsecutorResult
from app.agents.handoff import HandoffPayload, build_agent2_payload


def test_handoff_payload_validation_valid():
    """Test: Payload válido pasa la validación Pydantic."""
    payload_dict = {
        "case_id": "test-case-123",
        "question": "¿Hay riesgos legales?",
        "summary": "Resumen del análisis",
        "risks": ["Riesgo 1", "Riesgo 2"],
        "next_actions": ["Acción 1"],
        "auditor_fallback": False,
    }

    payload = HandoffPayload(**payload_dict)

    assert payload.case_id == "test-case-123"
    assert payload.question == "¿Hay riesgos legales?"
    assert payload.summary == "Resumen del análisis"
    assert len(payload.risks) == 2
    assert payload.auditor_fallback is False


def test_handoff_payload_validation_invalid_case_id():
    """Test: Payload con case_id vacío es rechazado."""
    payload_dict = {
        "case_id": "",  # Inválido
        "question": "¿Hay riesgos?",
        "summary": "Resumen",
        "risks": [],
        "next_actions": [],
    }

    with pytest.raises(ValidationError) as exc_info:
        HandoffPayload(**payload_dict)

    assert "case_id" in str(exc_info.value).lower() or "no puede estar vacío" in str(exc_info.value)


def test_handoff_payload_validation_missing_required():
    """Test: Payload faltante campos obligatorios es rechazado."""
    payload_dict = {
        "case_id": "test-case",
        # Falta question, summary, etc.
    }

    with pytest.raises(ValidationError):
        HandoffPayload(**payload_dict)


def test_auditor_fallback_propagation():
    """Test: El flag auditor_fallback se propaga correctamente en el handoff."""
    # Mock del resultado del Auditor
    auditor_result = AuditorResult(
        summary="Análisis con fallback",
        risks=["Falta de documentación"],
        next_actions=["Verificar documentos"],
    )

    # Construir payload con fallback=True
    payload = build_agent2_payload(
        auditor_result=auditor_result,
        case_id="test-case",
        question="Test question",
        auditor_fallback=True,  # Flag de fallback
    )

    assert payload["auditor_fallback"] is True
    assert payload["case_id"] == "test-case"
    assert payload["summary"] == "Análisis con fallback"

    # Validar con Pydantic
    validated = HandoffPayload(**payload)
    assert validated.auditor_fallback is True


def test_handoff_with_auditor_context():
    """Test: El payload incluye summary y risks del Auditor correctamente."""
    auditor_result = AuditorResult(
        summary="Resumen detallado del Auditor",
        risks=["Riesgo A", "Riesgo B", "Riesgo C"],
        next_actions=["Acción 1", "Acción 2"],
    )

    payload = build_agent2_payload(
        auditor_result=auditor_result,
        case_id="test-case",
        question="Pregunta de prueba",
        auditor_fallback=False,
    )

    assert payload["summary"] == "Resumen detallado del Auditor"
    assert len(payload["risks"]) == 3
    assert payload["risks"][0] == "Riesgo A"
    assert payload["auditor_fallback"] is False


def test_run_auditor_returns_fallback_flag():
    """Test: run_auditor retorna tupla (result, auditor_fallback)."""
    mock_db = MagicMock()

    with patch("app.agents.agent_1_auditor.runner.query_case_rag") as mock_rag:
        # Caso 1: Contexto vacío (fallback esperado)
        mock_rag.return_value = ""  # Contexto vacío

        result, auditor_fallback = run_auditor(
            case_id="test-case",
            question="Test question",
            db=mock_db,
        )

        assert isinstance(result, AuditorResult)
        assert auditor_fallback is True

        # Caso 2: Contexto con contenido (sin fallback)
        mock_rag.return_value = (
            "Este es un contexto largo con suficiente información para el análisis" * 10
        )

        result2, auditor_fallback2 = run_auditor(
            case_id="test-case",
            question="Test question",
            db=mock_db,
        )

        assert isinstance(result2, AuditorResult)
        assert auditor_fallback2 is False


def test_prosecutor_accepts_handoff_payload():
    """Test: El Prosecutor acepta el payload del handoff correctamente."""
    payload_dict = {
        "case_id": "test-case-123",
        "question": "Test question",
        "summary": "Resumen del Auditor",
        "risks": ["Riesgo 1"],
        "next_actions": ["Acción 1"],
        "auditor_fallback": False,
    }

    # Mock del ejecutar_analisis_prosecutor
    with patch("app.agents.agent_2_prosecutor.runner.ejecutar_analisis_prosecutor") as mock_exec:
        mock_result = ProsecutorResult(
            case_id="test-case-123",
            overall_risk_level="medio",
            accusations=[],
            critical_findings_count=0,
            summary_for_lawyer="Test summary",
            blocking_recommendation=False,
        )
        mock_exec.return_value = mock_result

        result = run_prosecutor_from_auditor(payload_dict)

        assert result.case_id == "test-case-123"
        # Verificar que se llamó con los parámetros correctos
        mock_exec.assert_called_once()
        call_kwargs = mock_exec.call_args.kwargs
        assert call_kwargs["case_id"] == "test-case-123"
        assert call_kwargs["auditor_summary"] == "Resumen del Auditor"
        assert call_kwargs["auditor_risks"] == ["Riesgo 1"]
        assert call_kwargs["auditor_fallback"] is False


def test_prosecutor_rejects_invalid_handoff_payload():
    """Test: El Prosecutor rechaza payload inválido (sin case_id)."""
    payload_dict = {
        # Falta case_id
        "question": "Test question",
        "summary": "Resumen",
        "risks": [],
        "next_actions": [],
    }

    with pytest.raises(ValueError) as exc_info:
        run_prosecutor_from_auditor(payload_dict)

    assert "case_id" in str(exc_info.value).lower()


def test_prosecutor_handles_auditor_fallback_flag():
    """Test: El Prosecutor recibe y maneja el flag auditor_fallback."""
    payload_dict = {
        "case_id": "test-case",
        "question": "Test question",
        "summary": "Resumen",
        "risks": ["Riesgo"],
        "next_actions": ["Acción"],
        "auditor_fallback": True,  # Flag de fallback activado
    }

    with patch("app.agents.agent_2_prosecutor.runner.ejecutar_analisis_prosecutor") as mock_exec:
        mock_result = ProsecutorResult(
            case_id="test-case",
            overall_risk_level="medio",
            accusations=[],
            critical_findings_count=0,
            summary_for_lawyer="Test",
            blocking_recommendation=False,
        )
        mock_exec.return_value = mock_result

        result = run_prosecutor_from_auditor(payload_dict)

        # Verificar que se pasó el flag
        call_kwargs = mock_exec.call_args.kwargs
        assert call_kwargs["auditor_fallback"] is True


if __name__ == "__main__":
    print("Ejecutando tests de regresión del handoff...")
    print("Para ejecutar con pytest: python -m pytest tests/manual/test_handoff_improvements.py -v")
