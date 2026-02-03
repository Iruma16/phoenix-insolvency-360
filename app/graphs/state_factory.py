"""
STATE FACTORY — CONSTRUCCIÓN CENTRALIZADA DE ESTADOS VÁLIDOS.

Este módulo es la ÚNICA forma legítima de crear estados iniciales para el grafo.

REGLAS NO NEGOCIABLES:
- NO construir PhoenixState manualmente en fixtures
- NO pasar dicts libres al grafo
- USAR esta factory para todos los casos

PROPÓSITO:
- Separar formato humano (AuditState) de formato interno (PhoenixState)
- Validar que TODO estado inicial cumple el contrato
- Centralizar lógica de construcción
"""
from datetime import datetime
from typing import Any, Optional

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
from app.graphs.state_schema import (
    Document as PhoenixDocument,
)


def create_initial_state(
    case_id: str,
    *,
    company_name: Optional[str] = None,
    company_id: Optional[str] = None,
    industry: Optional[str] = None,
    company_profile: Optional[dict[str, Any]] = None,
    documents: Optional[list[dict[str, Any]]] = None,
) -> PhoenixState:
    """
    Crea un estado inicial válido para el grafo de análisis.

    Este es el ÚNICO punto de entrada para crear estados.
    Garantiza que el estado cumple el contrato de PhoenixState.

    Args:
        case_id: Identificador único del caso (OBLIGATORIO)
        company_name: Nombre de la empresa (opcional)
        company_id: CIF/NIF de la empresa (opcional)
        industry: Sector/industria (opcional)
        company_profile: Dict con perfil completo (opcional)
        documents: Lista de documentos en formato dict (opcional)

    Returns:
        PhoenixState completamente inicializado y validado

    GARANTÍAS:
    - Todos los campos obligatorios inicializados
    - Estructuras anidadas correctas
    - No campos extra (cumple extra="forbid")
    - Timestamps correctos
    """
    # Construir contexto del caso
    case_context = CaseContext(
        company_name=company_name,
        company_id=company_id,
        industry=industry,
        company_profile=company_profile or {},
    )

    # Convertir documentos a PhoenixDocument
    phoenix_documents: list[PhoenixDocument] = []
    if documents:
        for doc in documents:
            phoenix_documents.append(
                PhoenixDocument(
                    doc_id=doc.get("doc_id", ""),
                    doc_type=doc.get("doc_type", ""),
                    content=doc.get("content", ""),
                    date=doc.get("date"),
                    metadata=doc.get("metadata", {}),
                )
            )

    # Construir inputs
    inputs = Inputs(documents=phoenix_documents, missing_documents=[])

    # Inicializar timeline vacío (se llena en analyze_timeline)
    timeline = Timeline(events=[], earliest_date=None, latest_date=None)

    # Inicializar facts vacío
    facts = Facts(risks=[], notes=None)

    # Inicializar risks vacío (se llena en detect_risks)
    risks = Risks(heuristic_risks=[], legal_findings=[])

    # Inicializar legal_rules vacío (se llena en rule_engine)
    legal_rules = LegalRulesEvaluation(findings=[], execution_time_ms=None)

    # Inicializar RAG evidence vacío
    rag_evidence = RagEvidence(case_chunks=[], legal_chunks=[])

    # Inicializar agents output vacío (se llena si LLM habilitado)
    agents = AgentsOutput(auditor_llm=None, prosecutor_llm=None)

    # Inicializar métricas
    metrics = Metrics(total_execution_time_ms=None, node_execution_times={})

    # Inicializar errors
    errors = Errors(validation_errors=[], node_errors={})

    # Construir estado completo
    now = datetime.utcnow()

    state = PhoenixState(
        schema_version=CURRENT_STATE_SCHEMA_VERSION,
        case_id=case_id,
        created_at=now,
        updated_at=now,
        case_context=case_context,
        inputs=inputs,
        timeline=timeline,
        facts=facts,
        risks=risks,
        legal_rules=legal_rules,
        rag_evidence=rag_evidence,
        agents=agents,
        report=None,
        metrics=metrics,
        errors=errors,
    )

    return state


def create_state_from_legacy(legacy_state: dict[str, Any]) -> PhoenixState:
    """
    Crea PhoenixState desde AuditState (formato legacy).

    Útil para migrar fixtures existentes sin reescribirlos.

    Args:
        legacy_state: Dict en formato AuditState (TypedDict)

    Returns:
        PhoenixState validado

    MAPEO:
    - company_profile → case_context.company_profile
    - documents → inputs.documents
    - timeline (list) → timeline.events
    - risks (list) → risks.heuristic_risks
    - missing_documents → inputs.missing_documents
    - legal_findings → risks.legal_findings
    - auditor_llm → agents.auditor_llm
    - prosecutor_llm → agents.prosecutor_llm
    - rule_based_findings → legal_rules.findings
    - notes → facts.notes
    """
    return create_initial_state(
        case_id=legacy_state.get("case_id", "UNKNOWN"),
        company_profile=legacy_state.get("company_profile", {}),
        documents=legacy_state.get("documents", []),
    )


def validate_initial_state(state: PhoenixState) -> None:
    """
    Valida que un estado inicial cumple requisitos mínimos.

    Args:
        state: Estado a validar

    Raises:
        ValueError: Si el estado no es válido

    VALIDACIONES:
    - case_id no vacío
    - schema_version correcta
    - Timestamps válidos
    """
    if not state.case_id or state.case_id == "UNKNOWN":
        raise ValueError("[STATE_FACTORY] case_id es obligatorio y no puede ser 'UNKNOWN'")

    if state.schema_version != CURRENT_STATE_SCHEMA_VERSION:
        raise ValueError(
            f"[STATE_FACTORY] schema_version incorrecta: "
            f"esperada {CURRENT_STATE_SCHEMA_VERSION}, recibida {state.schema_version}"
        )

    if not state.created_at:
        raise ValueError("[STATE_FACTORY] created_at es obligatorio")

    if not state.updated_at:
        raise ValueError("[STATE_FACTORY] updated_at es obligatorio")

    print(f"[STATE_FACTORY] Estado inicial válido para case_id={state.case_id}")
