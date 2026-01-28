"""
CONTRATO DE ESTADO ÚNICO Y VERSIONADO (SINGLE SOURCE OF TRUTH).

Este archivo define el schema OFICIAL del estado de Phoenix Legal.
Ningún nodo ni agente puede definir su propio estado.

PRINCIPIOS NO NEGOCIABLES:
- HARD FAIL > BEST EFFORT (fallos explícitos, no warnings silenciosos)
- Versionado explícito obligatorio
- Legal-grade traceability
- extra="forbid" → NO permite claves no definidas
- validate_assignment=True → Valida mutaciones

REGLA CRÍTICA:
Si necesitas añadir un campo → modifica ESTE archivo + bump version.
NO añadas claves adhoc en nodos.
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ========================================
# VERSIÓN DEL SCHEMA (OBLIGATORIO)
# ========================================
CURRENT_STATE_SCHEMA_VERSION = "1.0.0"


# ========================================
# SUBMODELOS ESTRUCTURADOS
# ========================================


class CaseContext(BaseModel):
    """Contexto del caso y perfil de la empresa."""

    company_name: Optional[str] = None
    company_id: Optional[str] = None
    industry: Optional[str] = None
    company_profile: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Document(BaseModel):
    """Documento del expediente."""

    doc_id: str
    doc_type: str
    content: str
    date: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class TimelineEvent(BaseModel):
    """Evento temporal extraído de documentación."""

    date: str
    description: str
    source_doc_id: Optional[str] = None
    severity: Optional[str] = None

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Timeline(BaseModel):
    """Timeline completo del caso."""

    events: list[TimelineEvent] = Field(default_factory=list)
    earliest_date: Optional[str] = None
    latest_date: Optional[str] = None

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Inputs(BaseModel):
    """Inputs originales del caso."""

    documents: list[Document] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Risk(BaseModel):
    """Riesgo detectado por heurísticas."""

    risk_type: str
    severity: str  # low | medium | high | indeterminate
    explanation: str
    evidence: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Facts(BaseModel):
    """Hechos probados y extracción estructurada."""

    risks: list[Risk] = Field(default_factory=list)
    notes: Optional[str] = None

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class LegalFinding(BaseModel):
    """Finding legal (output de legal_hardening)."""

    finding_type: str
    severity: str
    weight: int
    explanation: str
    evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    mitigation: list[str] = Field(default_factory=list)
    legal_basis: list[Any] = Field(default_factory=list)  # Acepta str o dict
    risk_classification: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Risks(BaseModel):
    """Riesgos y findings legales."""

    heuristic_risks: list[Risk] = Field(default_factory=list)
    legal_findings: list[LegalFinding] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RuleBasedFinding(BaseModel):
    """Finding basado en reglas (Rule Engine)."""

    finding_type: str
    severity: str
    weight: int
    explanation: str
    legal_basis: list[dict[str, str]] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    mitigation: Optional[str] = None
    source: Optional[str] = None

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class LegalRulesEvaluation(BaseModel):
    """Evaluación del Rule Engine."""

    findings: list[RuleBasedFinding] = Field(default_factory=list)
    execution_time_ms: Optional[float] = None

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RagChunk(BaseModel):
    """Chunk de RAG recuperado."""

    chunk_id: str
    doc_id: str
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RagEvidence(BaseModel):
    """Evidencia recuperada por RAG."""

    case_chunks: list[RagChunk] = Field(default_factory=list)
    legal_chunks: list[RagChunk] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AuditorLLMOutput(BaseModel):
    """Output del agente Auditor LLM."""

    llm_summary: Optional[str] = None
    llm_reasoning: Optional[str] = None
    llm_confidence: Optional[str] = None
    llm_agent: Optional[str] = None
    llm_enabled: bool = False
    execution_time_ms: Optional[float] = None

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ProsecutorLLMOutput(BaseModel):
    """Output del agente Prosecutor LLM."""

    llm_legal_summary: Optional[str] = None
    llm_legal_reasoning: Optional[str] = None
    llm_recommendations: Optional[str] = None
    llm_agent: Optional[str] = None
    llm_enabled: bool = False
    execution_time_ms: Optional[float] = None

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AgentsOutput(BaseModel):
    """Outputs de agentes LLM (opcionales)."""

    auditor_llm: Optional[AuditorLLMOutput] = None
    prosecutor_llm: Optional[ProsecutorLLMOutput] = None

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Report(BaseModel):
    """Reporte final generado."""

    case_id: str
    overall_risk: str  # low | medium | high | indeterminate
    timeline_summary: Optional[str] = None
    risk_summary: list[dict[str, Any]] = Field(default_factory=list)
    legal_findings: list[dict[str, Any]] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    pdf_path: Optional[str] = None

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Metrics(BaseModel):
    """Métricas de ejecución."""

    total_execution_time_ms: Optional[float] = None
    node_execution_times: dict[str, float] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class StateError(BaseModel):
    """Error de validación de estado."""

    stage: str
    field: Optional[str] = None
    error: str
    timestamp: datetime

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Errors(BaseModel):
    """Errores acumulados durante ejecución."""

    validation_errors: list[StateError] = Field(default_factory=list)
    node_errors: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ========================================
# SCHEMA RAÍZ (SINGLE SOURCE OF TRUTH)
# ========================================


class PhoenixState(BaseModel):
    """
    Estado oficial de Phoenix Legal.

    REGLAS NO NEGOCIABLES:
    - Este es el ÚNICO schema válido.
    - extra="forbid" → Lanza excepción si se añade clave no definida.
    - validate_assignment=True → Valida mutaciones en tiempo real.
    - Todos los campos están documentados.

    CAMPOS OBLIGATORIOS:
    - schema_version: versión del contrato
    - case_id: identificador único del caso
    - created_at: timestamp de creación
    - updated_at: timestamp de última actualización

    SUBMODELOS:
    - Todos los submodelos están definidos aunque algunos campos sean Optional.
    - NO se permiten dicts libres fuera de submodelos explícitos.

    VERSIONADO:
    - Cambiar el schema implica bump explícito de CURRENT_STATE_SCHEMA_VERSION.
    - Cada ejecución conoce exactamente qué versión usa.
    """

    # ────────────────────────────────────────────────────────────
    # METADATA OBLIGATORIA
    # ────────────────────────────────────────────────────────────
    schema_version: str = Field(
        default=CURRENT_STATE_SCHEMA_VERSION, description="Versión del schema de estado"
    )

    case_id: str = Field(..., description="Identificador único del caso (OBLIGATORIO)")

    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp de creación del estado"
    )

    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp de última actualización"
    )

    # ────────────────────────────────────────────────────────────
    # CONTEXTO Y INPUTS
    # ────────────────────────────────────────────────────────────
    case_context: CaseContext = Field(
        default_factory=CaseContext, description="Contexto del caso y perfil de empresa"
    )

    inputs: Inputs = Field(default_factory=Inputs, description="Documentos y datos de entrada")

    # ────────────────────────────────────────────────────────────
    # ANÁLISIS TEMPORAL Y HECHOS
    # ────────────────────────────────────────────────────────────
    timeline: Timeline = Field(
        default_factory=Timeline, description="Timeline de eventos extraídos"
    )

    facts: Facts = Field(default_factory=Facts, description="Hechos probados y notas")

    # ────────────────────────────────────────────────────────────
    # RIESGOS Y FINDINGS LEGALES
    # ────────────────────────────────────────────────────────────
    risks: Risks = Field(
        default_factory=Risks, description="Riesgos heurísticos y findings legales"
    )

    legal_rules: LegalRulesEvaluation = Field(
        default_factory=LegalRulesEvaluation, description="Evaluación del Rule Engine"
    )

    # ────────────────────────────────────────────────────────────
    # EVIDENCIA RAG
    # ────────────────────────────────────────────────────────────
    rag_evidence: RagEvidence = Field(
        default_factory=RagEvidence, description="Chunks recuperados por RAG"
    )

    # ────────────────────────────────────────────────────────────
    # AGENTES LLM
    # ────────────────────────────────────────────────────────────
    agents: AgentsOutput = Field(
        default_factory=AgentsOutput, description="Outputs de agentes LLM opcionales"
    )

    # ────────────────────────────────────────────────────────────
    # REPORTE FINAL
    # ────────────────────────────────────────────────────────────
    report: Optional[Report] = Field(default=None, description="Reporte final generado")

    # ────────────────────────────────────────────────────────────
    # MÉTRICAS Y ERRORES
    # ────────────────────────────────────────────────────────────
    metrics: Metrics = Field(default_factory=Metrics, description="Métricas de ejecución")

    errors: Errors = Field(default_factory=Errors, description="Errores de validación y ejecución")

    # ────────────────────────────────────────────────────────────
    # CONFIGURACIÓN PYDANTIC (CRÍTICA)
    # ────────────────────────────────────────────────────────────
    model_config = ConfigDict(
        extra="forbid",  # ⚠️ CRÍTICO: NO permite claves no definidas
        validate_assignment=True,  # ⚠️ CRÍTICO: Valida mutaciones
        arbitrary_types_allowed=False,
        str_strip_whitespace=True,
    )
