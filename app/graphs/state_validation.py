"""
VALIDACIÓN HARD DEL CONTRATO DE ESTADO.

Este módulo valida que el estado cumple el contrato definido en state_schema.py.

PRINCIPIOS:
- HARD FAIL > BEST EFFORT
- No warnings silenciosos → Excepciones explícitas
- Cada fallo indica: stage, campo, razón exacta
- Legal-grade traceability

REGLA CRÍTICA:
Si la validación falla → el sistema DEBE detenerse.
NO continuar con estado inválido.
"""
import sys
from datetime import datetime
from typing import Any, Union

from pydantic import ValidationError

from app.graphs.state_schema import CURRENT_STATE_SCHEMA_VERSION, PhoenixState

# ========================================
# VALIDACIÓN PRINCIPAL
# ========================================


def validate_state(state: Union[dict[str, Any], PhoenixState], *, stage: str) -> PhoenixState:
    """
    Valida que el estado cumple el contrato de PhoenixState.

    Args:
        state: Estado a validar (dict o PhoenixState)
        stage: Etapa de validación (formato: "pre:<node>" o "post:<node>")

    Returns:
        PhoenixState tipado y validado

    Raises:
        ValueError: Si el estado no cumple el contrato

    COMPORTAMIENTO:
    - Si state es dict → intenta construir PhoenixState
    - Si es PhoenixState → revalida (por si hubo mutaciones)
    - Si falla → lanza ValueError con mensaje estructurado

    EJEMPLO DE ERROR:
        [STATE CONTRACT VIOLATION] stage=post:detect_risks field=risks.severity error=Invalid severity value
    """
    # Log de validación
    print(f"[STATE_VALIDATION] stage={stage} schema_version={CURRENT_STATE_SCHEMA_VERSION}")

    try:
        # Caso 1: state es dict → construir PhoenixState
        if isinstance(state, dict):
            # Actualizar timestamp
            state_copy = state.copy()
            state_copy["updated_at"] = datetime.utcnow()

            validated_state = PhoenixState(**state_copy)

            print(f"[STATE_VALIDATION] stage={stage} result=VALID")
            return validated_state

        # Caso 2: state es PhoenixState → revalidar
        elif isinstance(state, PhoenixState):
            # Actualizar timestamp
            state.updated_at = datetime.utcnow()

            # Revalidar (importante por validate_assignment=True)
            state.model_validate(state.model_dump())

            print(f"[STATE_VALIDATION] stage={stage} result=VALID")
            return state

        else:
            raise ValueError(
                f"[STATE CONTRACT VIOLATION] stage={stage} "
                f"error=Estado debe ser dict o PhoenixState, recibido {type(state).__name__}"
            )

    except ValidationError as e:
        # Extraer información del primer error
        first_error = e.errors()[0]
        field_path = ".".join(str(loc) for loc in first_error["loc"])
        error_msg = first_error["msg"]
        error_type = first_error["type"]

        # Construir mensaje de error estructurado
        violation_msg = (
            f"[STATE CONTRACT VIOLATION] "
            f"stage={stage} "
            f"field={field_path} "
            f"error={error_msg} "
            f"type={error_type}"
        )

        # Loguear ERROR crítico
        print(violation_msg, file=sys.stderr)

        # Log adicional con todos los errores
        print(
            f"[STATE_VALIDATION] stage={stage} result=FAILED errors={len(e.errors())}",
            file=sys.stderr,
        )
        for err in e.errors():
            field = ".".join(str(loc) for loc in err["loc"])
            print(f"  - field={field} error={err['msg']}", file=sys.stderr)

        # Lanzar ValueError (NO custom silent error)
        raise ValueError(violation_msg) from e

    except Exception as e:
        # Error inesperado
        violation_msg = (
            f"[STATE CONTRACT VIOLATION] "
            f"stage={stage} "
            f"error=Validación falló inesperadamente: {str(e)}"
        )

        print(violation_msg, file=sys.stderr)
        raise ValueError(violation_msg) from e


# ========================================
# HELPERS DE MIGRACIÓN
# ========================================


def migrate_legacy_state_to_schema(legacy_state: dict[str, Any]) -> PhoenixState:
    """
    Migra un estado legacy (TypedDict) al nuevo schema.

    Este helper facilita la transición gradual.
    Eventualmente, todos los nodos usarán PhoenixState directamente.

    Args:
        legacy_state: Estado en formato TypedDict (state.py viejo)

    Returns:
        PhoenixState validado
    """
    # Mapear estructura legacy a nueva
    timeline_events = legacy_state.get("timeline", [])

    # Calcular earliest/latest dates del timeline
    earliest_date = None
    latest_date = None
    if timeline_events:
        dates = [e.get("date") for e in timeline_events if e.get("date")]
        if dates:
            earliest_date = min(dates)
            latest_date = max(dates)

    migrated = {
        "case_id": legacy_state.get("case_id", "UNKNOWN"),
        "case_context": {"company_profile": legacy_state.get("company_profile", {})},
        "inputs": {
            "documents": legacy_state.get("documents", []),
            "missing_documents": legacy_state.get("missing_documents", []),
        },
        "timeline": {
            "events": timeline_events,
            "earliest_date": earliest_date,
            "latest_date": latest_date,
        },
        "facts": {
            "heuristic_risks": legacy_state.get("risks", []),
            "legal_findings": legacy_state.get("legal_findings", []),
            "notes": legacy_state.get("notes"),
        },
        "risks": {
            "heuristic_risks": legacy_state.get("risks", []),
            "legal_findings": legacy_state.get("legal_findings", []),
            "detected": legacy_state.get("risks", []),
        },
        "legal_rules": {"findings": legacy_state.get("rule_based_findings", []) or []},
        "agents": {
            "auditor_llm": legacy_state.get("auditor_llm"),
            "prosecutor_llm": legacy_state.get("prosecutor_llm"),
        },
        "report": legacy_state.get("report"),
    }

    return PhoenixState(**migrated)


def extract_legacy_state_from_schema(phoenix_state: PhoenixState) -> dict[str, Any]:
    """
    Extrae formato legacy del PhoenixState (para compatibilidad temporal).

    Útil para nodos que aún no han migrado completamente.
    """
    return {
        "case_id": phoenix_state.case_id,
        "company_profile": phoenix_state.case_context.company_profile,
        "documents": [doc.model_dump() for doc in phoenix_state.inputs.documents],
        "timeline": [event.model_dump() for event in phoenix_state.timeline.events],
        "risks": [risk.model_dump() for risk in phoenix_state.risks.heuristic_risks],
        "missing_documents": phoenix_state.inputs.missing_documents,
        "legal_findings": [finding.model_dump() for finding in phoenix_state.risks.legal_findings],
        "auditor_llm": phoenix_state.agents.auditor_llm.model_dump()
        if phoenix_state.agents.auditor_llm
        else None,
        "prosecutor_llm": phoenix_state.agents.prosecutor_llm.model_dump()
        if phoenix_state.agents.prosecutor_llm
        else None,
        "rule_based_findings": [
            finding.model_dump() for finding in phoenix_state.legal_rules.findings
        ],
        "notes": phoenix_state.facts.notes,
        "report": phoenix_state.report.model_dump() if phoenix_state.report else None,
    }


# ========================================
# OBSERVABILIDAD
# ========================================


def log_state_snapshot(state: PhoenixState, stage: str) -> None:
    """
    Loguea snapshot del estado para observabilidad.

    Args:
        state: Estado actual
        stage: Etapa del graph
    """
    print(
        f"[STATE_SNAPSHOT] "
        f"stage={stage} "
        f"case_id={state.case_id} "
        f"schema_version={state.schema_version} "
        f"documents_count={len(state.inputs.documents)} "
        f"timeline_events={len(state.timeline.events)} "
        f"risks_count={len(state.risks.heuristic_risks)} "
        f"findings_count={len(state.risks.legal_findings)}"
    )
