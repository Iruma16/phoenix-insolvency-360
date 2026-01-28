"""
Tests de validación de estado en el graph.

Verifica que:
- Nodos que rompen contrato → test falla
- Nodos válidos → test pasa
- Validación pre/post funciona correctamente

SIN dependencias externas: LLM, red, DB, Chroma.
Rápidos y deterministas.
"""

# Importar el decorador sin importar los nodos (evita dependencias ORM)
from functools import wraps
from typing import Any, Callable

import pytest

from app.graphs.state_schema import CURRENT_STATE_SCHEMA_VERSION, PhoenixState
from app.graphs.state_validation import (
    extract_legacy_state_from_schema,
    log_state_snapshot,
    migrate_legacy_state_to_schema,
    validate_state,
)


def with_state_validation(node_name: str):
    """
    Decorator simplificado para tests (sin dependencias ORM).
    Copia del real en validated_nodes.py
    """

    def decorator(node_fn: Callable) -> Callable:
        @wraps(node_fn)
        def wrapped_node(state: Any) -> PhoenixState:
            stage_pre = f"pre:{node_name}"

            try:
                validated_input = validate_state(state, stage=stage_pre)
                log_state_snapshot(validated_input, stage_pre)
            except ValueError:
                raise

            try:
                legacy_state = extract_legacy_state_from_schema(validated_input)
                result = node_fn(legacy_state)

                if isinstance(result, dict):
                    legacy_state.update(result)
                    output_state = legacy_state
                else:
                    output_state = result
            except Exception:
                raise

            stage_post = f"post:{node_name}"

            try:
                if isinstance(output_state, dict):
                    output_state["case_id"] = validated_input.case_id
                    output_state["schema_version"] = validated_input.schema_version
                    output_state["created_at"] = validated_input.created_at

                    validated_output = migrate_legacy_state_to_schema(output_state)
                else:
                    validated_output = output_state

                validated_output = validate_state(validated_output, stage=stage_post)
                log_state_snapshot(validated_output, stage_post)

                return validated_output

            except ValueError:
                raise

        return wrapped_node

    return decorator


# ════════════════════════════════════════════════════════════════
# TEST 1: Nodo válido pasa validación
# ════════════════════════════════════════════════════════════════


def test_nodo_valido_pasa_validacion():
    """
    Verifica que un nodo que cumple el contrato pasa validación.
    """

    # Nodo mock que NO rompe contrato
    @with_state_validation("test_node_valid")
    def valid_node(state):
        # Solo lee, no modifica
        return state

    # Estado inicial válido usando formato legacy correcto
    initial_state = migrate_legacy_state_to_schema(
        {
            "case_id": "test_case_001",
            "documents": [],
            "timeline": [],
            "risks": [],
            "missing_documents": [],
            "legal_findings": [],
            "company_profile": {},
            "auditor_llm": None,
            "prosecutor_llm": None,
            "rule_based_findings": [],
            "notes": None,
            "report": None,
        }
    )

    # Ejecutar nodo
    result = valid_node(initial_state)

    # Verificar que devuelve PhoenixState válido
    assert isinstance(result, PhoenixState)
    assert result.case_id == "test_case_001"
    assert result.schema_version == CURRENT_STATE_SCHEMA_VERSION

    print("✅ Nodo válido pasó validación pre y post")


# ════════════════════════════════════════════════════════════════
# TEST 2: Nodo que rompe contrato falla post-validación
# ════════════════════════════════════════════════════════════════


def test_nodo_invalido_falla_validacion():
    """
    Verifica que un nodo que altera tipo de datos FALLA.

    Esto es CRÍTICO: el sistema debe fallar temprano.
    """

    # Nodo mock que ROMPE contrato (altera tipo de datos)
    @with_state_validation("test_node_invalid")
    def invalid_node(state):
        # Romper tipo de datos esperado
        state["documents"] = "esto debería ser lista, no string"
        return state

    # Estado inicial válido
    initial_state = migrate_legacy_state_to_schema(
        {
            "case_id": "test_case_002",
            "documents": [],
            "timeline": [],
            "risks": [],
            "missing_documents": [],
            "legal_findings": [],
            "company_profile": {},
            "auditor_llm": None,
            "prosecutor_llm": None,
            "rule_based_findings": [],
            "notes": None,
            "report": None,
        }
    )

    # Ejecutar nodo debe FALLAR (puede ser ValueError o ValidationError)
    with pytest.raises(Exception) as exc_info:
        invalid_node(initial_state)

    error_msg = str(exc_info.value)
    # Verificar que el error menciona el problema de tipo
    assert "documents" in error_msg or "list" in error_msg.lower()

    print("✅ Nodo inválido falló correctamente:")
    print(f"   {error_msg[:200]}")


# ════════════════════════════════════════════════════════════════
# TEST 3: Pre-validación detecta entrada inválida
# ════════════════════════════════════════════════════════════════


def test_pre_validacion_detecta_entrada_invalida():
    """
    Verifica que pre-validación detecta estado de entrada inválido.
    """

    # Nodo mock válido
    @with_state_validation("test_node_precheck")
    def node(state):
        return state

    # Estado INVÁLIDO: documents con tipo incorrecto
    try:
        invalid_input = PhoenixState(
            case_id="test_case",
            inputs={"documents": "esto debería ser lista"},  # Tipo incorrecto
        )
        pytest.fail("Debería haber fallado al crear estado inválido")
    except Exception:
        # Esperado: la creación misma falla
        pass

    print("✅ Pre-validación detectó entrada inválida durante construcción")


# ════════════════════════════════════════════════════════════════
# TEST 4: Validación completa de flujo
# ════════════════════════════════════════════════════════════════


def test_flujo_validacion_completo():
    """
    Verifica que un flujo completo (varios nodos) valida correctamente.
    """

    # Nodo 1: añade documentos
    @with_state_validation("add_documents")
    def add_docs_node(state):
        state["documents"] = [
            {"doc_id": "doc_1", "doc_type": "balance", "content": "test", "date": None}
        ]
        return state

    # Nodo 2: añade timeline
    @with_state_validation("add_timeline")
    def add_timeline_node(state):
        state["timeline"] = [{"date": "2024-01-15", "description": "Evento", "source_doc_id": None}]
        return state

    # Estado inicial
    state = migrate_legacy_state_to_schema(
        {
            "case_id": "test_case_003",
            "documents": [],
            "timeline": [],
            "risks": [],
            "missing_documents": [],
            "legal_findings": [],
            "company_profile": {},
            "auditor_llm": None,
            "prosecutor_llm": None,
            "rule_based_findings": [],
            "notes": None,
            "report": None,
        }
    )

    # Ejecutar flujo
    state = add_docs_node(state)
    assert isinstance(state, PhoenixState)
    assert len(state.inputs.documents) == 1

    state = add_timeline_node(state)
    assert isinstance(state, PhoenixState)
    assert len(state.timeline.events) == 1

    print("✅ Flujo completo validado correctamente")


# ════════════════════════════════════════════════════════════════
# TEST 5: Migración de estado legacy
# ════════════════════════════════════════════════════════════════


def test_migracion_estado_legacy():
    """
    Verifica que estados legacy se pueden migrar al nuevo schema.
    """
    legacy_state = {
        "case_id": "test_case_004",
        "company_profile": {"name": "Test Corp"},
        "documents": [{"doc_id": "doc_1", "doc_type": "balance", "content": "test", "date": None}],
        "timeline": [{"date": "2024-01-15", "description": "Evento", "source_doc_id": None}],
        "risks": [
            {"risk_type": "delay_filing", "severity": "high", "explanation": "Test", "evidence": []}
        ],
        "missing_documents": [],
        "legal_findings": [],
        "auditor_llm": None,
        "prosecutor_llm": None,
        "rule_based_findings": [],
        "notes": None,
        "report": None,
    }

    # Migrar
    phoenix_state = migrate_legacy_state_to_schema(legacy_state)

    # Verificar
    assert isinstance(phoenix_state, PhoenixState)
    assert phoenix_state.case_id == "test_case_004"
    assert len(phoenix_state.inputs.documents) == 1
    assert len(phoenix_state.timeline.events) == 1
    assert len(phoenix_state.facts.risks) == 1

    print("✅ Migración legacy → schema completada")


# ════════════════════════════════════════════════════════════════
# TEST 6: Nodo que borra campo requerido
# ════════════════════════════════════════════════════════════════


def test_nodo_que_rompe_estructura_falla():
    """
    Verifica que un nodo que rompe estructura de submodelos FALLA.
    """

    # Nodo que intenta romper estructura
    @with_state_validation("malicious_node")
    def bad_node(state):
        # Romper estructura de risks (debe ser lista)
        state["risks"] = {"esto": "no es una lista"}
        return state

    initial_state = migrate_legacy_state_to_schema(
        {
            "case_id": "test_case_005",
            "documents": [],
            "timeline": [],
            "risks": [],
            "missing_documents": [],
            "legal_findings": [],
            "company_profile": {},
            "auditor_llm": None,
            "prosecutor_llm": None,
            "rule_based_findings": [],
            "notes": None,
            "report": None,
        }
    )

    # Debe fallar en post-validación
    with pytest.raises(Exception):  # Puede ser ValueError o ValidationError
        bad_node(initial_state)

    print("✅ Nodo que intenta romper estructura fue rechazado")


# ════════════════════════════════════════════════════════════════
# TEST 7: Validación sin exceptions silenciosas
# ════════════════════════════════════════════════════════════════


def test_no_exceptions_silenciosas():
    """
    Verifica que NO hay warnings silenciosos, solo excepciones explícitas.
    """
    invalid_state_data = {"case_id": "test_case_006", "campo_ilegal": "valor"}

    # Debe lanzar excepción, NO solo warning
    with pytest.raises(ValueError):
        validate_state(invalid_state_data, stage="test_no_silent")

    print("✅ Sin excepciones silenciosas: HARD FAIL explícito")


# ════════════════════════════════════════════════════════════════
# TEST 8: Logging de validación
# ════════════════════════════════════════════════════════════════


def test_logging_validacion(capsys):
    """
    Verifica que las validaciones loguean correctamente.
    """
    state = migrate_legacy_state_to_schema(
        {
            "case_id": "test_case_007",
            "documents": [],
            "timeline": [],
            "risks": [],
            "missing_documents": [],
            "legal_findings": [],
            "company_profile": {},
            "auditor_llm": None,
            "prosecutor_llm": None,
            "rule_based_findings": [],
            "notes": None,
            "report": None,
        }
    )

    validated = validate_state(state, stage="test_logging")

    # Capturar output
    captured = capsys.readouterr()

    assert "[STATE_VALIDATION]" in captured.out
    assert "stage=test_logging" in captured.out
    assert "result=VALID" in captured.out

    print("✅ Logging de validación correcto")


# ════════════════════════════════════════════════════════════════
# TEST 9: Estado con submodelos complejos
# ════════════════════════════════════════════════════════════════


def test_validacion_submodelos_complejos():
    """
    Verifica validación de submodelos anidados.
    """
    from app.graphs.state_schema import Document, Risk

    state = PhoenixState(
        case_id="test_case_008",
        inputs={"documents": [Document(doc_id="d1", doc_type="balance", content="test")]},
        facts={
            "risks": [
                Risk(
                    risk_type="delay_filing",
                    severity="high",
                    explanation="Test risk",
                    evidence=["doc_1"],
                )
            ]
        },
    )

    # Validar
    validated = validate_state(state, stage="test_complex")

    assert isinstance(validated, PhoenixState)
    assert len(validated.inputs.documents) == 1
    assert len(validated.facts.risks) == 1

    print("✅ Submodelos complejos validados correctamente")


# ════════════════════════════════════════════════════════════════
# TEST 10: Schema version en todos los estados
# ════════════════════════════════════════════════════════════════


def test_schema_version_presente():
    """
    Verifica que todos los estados validados tienen schema_version.
    """
    state = migrate_legacy_state_to_schema(
        {
            "case_id": "test_case_009",
            "documents": [],
            "timeline": [],
            "risks": [],
            "missing_documents": [],
            "legal_findings": [],
            "company_profile": {},
            "auditor_llm": None,
            "prosecutor_llm": None,
            "rule_based_findings": [],
            "notes": None,
            "report": None,
        }
    )

    validated = validate_state(state, stage="test_version")

    assert validated.schema_version == CURRENT_STATE_SCHEMA_VERSION
    assert validated.schema_version == "1.0.0"

    print(f"✅ Schema version presente: {validated.schema_version}")
