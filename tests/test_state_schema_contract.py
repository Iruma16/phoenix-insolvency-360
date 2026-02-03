"""
Tests del contrato de estado (state_schema.py).

Verifica que el contrato se cumple estrictamente:
- Estado mínimo válido
- Rechazo de claves desconocidas
- Validación de campos requeridos
- Mensajes de error estructurados

SIN dependencias externas: LLM, red, DB, Chroma.
Rápidos y deterministas.
"""
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.graphs.state_schema import (
    CURRENT_STATE_SCHEMA_VERSION,
    AgentsOutput,
    CaseContext,
    Errors,
    Facts,
    Inputs,
    LegalRulesEvaluation,
    Metrics,
    PhoenixState,
    RagEvidence,
    Risks,
    Timeline,
)

# ════════════════════════════════════════════════════════════════
# TEST 1: Estado mínimo válido
# ════════════════════════════════════════════════════════════════


def test_state_minimo_valido():
    """
    Verifica que un estado mínimo con solo case_id es válido.

    Todos los demás campos tienen defaults razonables.
    """
    state = PhoenixState(case_id="test_case_001")

    assert state.case_id == "test_case_001"
    assert state.schema_version == CURRENT_STATE_SCHEMA_VERSION
    assert isinstance(state.created_at, datetime)
    assert isinstance(state.updated_at, datetime)

    # Verificar que submodelos tienen valores por defecto
    assert isinstance(state.case_context, CaseContext)
    assert isinstance(state.inputs, Inputs)
    assert isinstance(state.timeline, Timeline)
    assert isinstance(state.facts, Facts)
    assert isinstance(state.risks, Risks)
    assert isinstance(state.legal_rules, LegalRulesEvaluation)
    assert isinstance(state.rag_evidence, RagEvidence)
    assert isinstance(state.agents, AgentsOutput)
    assert isinstance(state.metrics, Metrics)
    assert isinstance(state.errors, Errors)

    print("✅ Estado mínimo válido creado correctamente")


# ════════════════════════════════════════════════════════════════
# TEST 2: Falla con clave desconocida
# ════════════════════════════════════════════════════════════════


def test_falla_clave_desconocida():
    """
    Verifica que extra="forbid" rechaza claves no definidas.

    Esto es CRÍTICO: evita que nodos añadan claves adhoc.
    """
    with pytest.raises(ValidationError) as exc_info:
        PhoenixState(case_id="test_case_002", clave_inventada="esto no debe permitirse")

    error = exc_info.value
    assert len(error.errors()) > 0

    first_error = error.errors()[0]
    assert "extra" in first_error["type"] or "unexpected" in first_error["msg"].lower()

    print(f"✅ Clave desconocida rechazada correctamente: {first_error['msg']}")


# ════════════════════════════════════════════════════════════════
# TEST 3: Falla con campo requerido faltante
# ════════════════════════════════════════════════════════════════


def test_falla_campo_requerido():
    """
    Verifica que campos obligatorios (case_id) son validados.
    """
    with pytest.raises(ValidationError) as exc_info:
        PhoenixState()  # Sin case_id

    error = exc_info.value
    assert len(error.errors()) > 0

    first_error = error.errors()[0]
    assert "case_id" in str(first_error["loc"])
    # En Pydantic v2, el tipo es "missing" y el mensaje es "Field required"
    assert "missing" in first_error["type"] or "required" in first_error["msg"].lower()

    print(f"✅ Campo requerido validado correctamente: {first_error['msg']}")


# ════════════════════════════════════════════════════════════════
# TEST 4: Error contiene stage y field
# ════════════════════════════════════════════════════════════════


def test_error_contiene_stage_y_field():
    """
    Verifica que los errores de validación contienen información estructurada.

    Esto es para legal-grade traceability.
    """
    from app.graphs.state_validation import validate_state

    # Estado inválido (clave extra)
    invalid_state = {"case_id": "test_case_003", "clave_no_permitida": "valor"}

    try:
        validate_state(invalid_state, stage="test_validation")
        pytest.fail("Debería haber lanzado ValueError")

    except ValueError as e:
        error_msg = str(e)

        # Verificar estructura del mensaje
        assert "[STATE CONTRACT VIOLATION]" in error_msg
        assert "stage=test_validation" in error_msg
        assert "field=" in error_msg
        assert "error=" in error_msg

        print("✅ Error estructurado correctamente:")
        print(f"   {error_msg}")


# ════════════════════════════════════════════════════════════════
# TEST 5: Validación de asignación (validate_assignment=True)
# ════════════════════════════════════════════════════════════════


def test_validate_assignment_detecta_mutaciones():
    """
    Verifica que validate_assignment=True detecta mutaciones inválidas.
    """
    state = PhoenixState(case_id="test_case_004")

    # Intentar mutar a valor inválido
    with pytest.raises(ValidationError):
        state.case_id = None  # case_id no puede ser None

    print("✅ Mutación inválida detectada correctamente")


# ════════════════════════════════════════════════════════════════
# TEST 6: Estructura de submodelos
# ════════════════════════════════════════════════════════════════


def test_submodelos_validos():
    """
    Verifica que los submodelos se pueden crear e integrar correctamente.
    """
    from app.graphs.state_schema import Document, Risk, TimelineEvent

    # Crear documento
    doc = Document(doc_id="doc_001", doc_type="balance_pyg", content="Contenido del documento")

    # Crear evento
    event = TimelineEvent(date="2024-01-15", description="Evento de prueba")

    # Crear riesgo
    risk = Risk(risk_type="delay_filing", severity="high", explanation="Explicación del riesgo")

    # Integrar en estado
    state = PhoenixState(
        case_id="test_case_005",
        inputs=Inputs(documents=[doc]),
        timeline=Timeline(events=[event]),
        facts=Facts(risks=[risk]),
    )

    assert len(state.inputs.documents) == 1
    assert len(state.timeline.events) == 1
    assert len(state.facts.risks) == 1

    print("✅ Submodelos integrados correctamente")


# ════════════════════════════════════════════════════════════════
# TEST 7: Schema version tracking
# ════════════════════════════════════════════════════════════════


def test_schema_version_tracking():
    """
    Verifica que cada estado conoce su versión de schema.
    """
    state = PhoenixState(case_id="test_case_006")

    assert state.schema_version == CURRENT_STATE_SCHEMA_VERSION
    assert state.schema_version == "1.0.0"

    print(f"✅ Schema version tracked: {state.schema_version}")


# ════════════════════════════════════════════════════════════════
# TEST 8: Timestamps automáticos
# ════════════════════════════════════════════════════════════════


def test_timestamps_automaticos():
    """
    Verifica que created_at y updated_at se generan automáticamente.
    """
    state = PhoenixState(case_id="test_case_007")

    assert isinstance(state.created_at, datetime)
    assert isinstance(state.updated_at, datetime)
    assert state.created_at <= state.updated_at

    print("✅ Timestamps generados automáticamente")


# ════════════════════════════════════════════════════════════════
# TEST 9: Serialización y deserialización
# ════════════════════════════════════════════════════════════════


def test_serializacion_valida():
    """
    Verifica que el estado se puede serializar y deserializar.
    """
    state = PhoenixState(case_id="test_case_008")

    # Serializar a dict
    state_dict = state.model_dump()
    assert isinstance(state_dict, dict)
    assert state_dict["case_id"] == "test_case_008"

    # Deserializar
    state_reconstructed = PhoenixState(**state_dict)
    assert state_reconstructed.case_id == "test_case_008"

    print("✅ Serialización/deserialización válida")


# ════════════════════════════════════════════════════════════════
# TEST 10: Reject None en campos str
# ════════════════════════════════════════════════════════════════


def test_reject_none_en_campos_string():
    """
    Verifica que campos str no opcionales rechazan None.
    """
    with pytest.raises(ValidationError):
        PhoenixState(case_id=None)

    print("✅ None rechazado en campos no opcionales")
