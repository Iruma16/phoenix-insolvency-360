"""
AUDIT TRACE: Tracing estructurado con replay determinista.

ENDURECIMIENTO #6: Captura completa de ejecución para demostrar reproducibilidad.

PRINCIPIO: Cualquier ejecución DEBE ser reproducible sin LLM ni vectorstore.
"""
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .schema import AcusacionBloqueada, AcusacionProbatoria, ProsecutorResult

# ============================
# GATE CHECK (INVARIANTES)
# ============================


@dataclass(frozen=True)
class GateCheck:
    """
    Registro de verificación de un gate/invariante.

    Inmutable para garantizar trazabilidad.
    """

    gate_id: str
    passed: bool
    reason: Optional[str] = None


# ============================
# SNAPSHOTS
# ============================


@dataclass(frozen=True)
class BudgetSnapshot:
    """
    Snapshot del presupuesto en el momento de ejecución.

    ENDURECIMIENTO #7 (CIERRE HARD): Trazabilidad financiera completa.
    """

    case_id: str
    initial_budget_usd: float
    spent_usd: float
    remaining_usd: float
    pricing_version: str
    pricing_fingerprint: str


@dataclass(frozen=True)
class LLMCallDecisionSnapshot:
    """
    Snapshot de la decisión de policy LLM.

    ENDURECIMIENTO #7: Trazabilidad de por qué se bloqueó o permitió LLM.
    """

    allow_call: bool
    reason: str
    degraded_mode: bool


@dataclass(frozen=True)
class RAGSnapshot:
    """
    Snapshot del estado del RAG en el momento de ejecución.

    ENDURECIMIENTO #4: Captura RetrievalEvidence para replay.
    """

    case_id: str
    question: str
    total_chunks: int
    valid_chunks: int
    min_similarity: float
    avg_similarity: float
    retrieval_version: str
    no_response_reason: Optional[str] = None
    chunks_data: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ProsecutorSnapshot:
    """
    Snapshot del resultado del Prosecutor.

    ENDURECIMIENTO #5: Captura acusaciones completas Y bloqueadas.
    """

    case_id: str
    total_acusaciones: int
    total_bloqueadas: int
    acusaciones_data: list[dict[str, Any]] = field(default_factory=list)
    bloqueadas_data: list[dict[str, Any]] = field(default_factory=list)
    solicitud_evidencia: Optional[dict[str, Any]] = None


# ============================
# AUDIT TRACE (ESTRUCTURA PRINCIPAL)
# ============================


@dataclass(frozen=True)
class AuditTrace:
    """
    Captura completa y verificable de una ejecución del Prosecutor.

    PROPIEDADES:
    - Serializable (JSON)
    - Inmutable (frozen dataclass)
    - Hashable (determinista)

    GARANTÍA: Permite REPLAY sin LLM ni vectorstore.

    ENDURECIMIENTO #7 (CIERRE HARD): Incluye finops snapshot.
    """

    trace_id: str
    pipeline_version: str
    manifest_snapshot: dict[str, Any]
    config_snapshot: dict[str, Any]

    # INPUTS
    case_id: str
    rules_evaluated: list[str]

    # RAG STATE
    rag_snapshots: list[RAGSnapshot]

    # PROSECUTOR STATE
    prosecutor_snapshot: ProsecutorSnapshot

    # OUTPUTS
    result_hash: str
    decision_state: str  # "COMPLETE" | "PARTIAL" | "BLOCKED"

    # INVARIANTS
    invariants_checked: list[GateCheck]

    # FINOPS (ENDURECIMIENTO #7)
    budget_snapshot: Optional[BudgetSnapshot] = None
    llm_call_decisions: list[LLMCallDecisionSnapshot] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict para persistencia."""
        return asdict(self)

    def to_json(self) -> str:
        """Serializa a JSON determinista."""
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    def compute_hash(self) -> str:
        """
        Calcula hash determinista del trace.

        GARANTÍA: Dos traces idénticos producen el mismo hash.
        """
        serialized = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditTrace":
        """Deserializa desde dict."""
        # Reconstruct frozen dataclasses
        rag_snapshots = [RAGSnapshot(**snap) for snap in data.get("rag_snapshots", [])]

        prosecutor_snapshot = ProsecutorSnapshot(**data["prosecutor_snapshot"])

        invariants_checked = [GateCheck(**inv) for inv in data.get("invariants_checked", [])]

        # Reconstruct finops snapshots
        budget_snapshot = None
        if data.get("budget_snapshot"):
            budget_snapshot = BudgetSnapshot(**data["budget_snapshot"])

        llm_call_decisions = [
            LLMCallDecisionSnapshot(**dec) for dec in data.get("llm_call_decisions", [])
        ]

        return cls(
            trace_id=data["trace_id"],
            pipeline_version=data["pipeline_version"],
            manifest_snapshot=data["manifest_snapshot"],
            config_snapshot=data["config_snapshot"],
            case_id=data["case_id"],
            rules_evaluated=data["rules_evaluated"],
            rag_snapshots=rag_snapshots,
            prosecutor_snapshot=prosecutor_snapshot,
            result_hash=data["result_hash"],
            decision_state=data["decision_state"],
            invariants_checked=invariants_checked,
            budget_snapshot=budget_snapshot,
            llm_call_decisions=llm_call_decisions,
        )


# ============================
# REPLAY DETERMINISTA
# ============================


class ReplayViolationError(Exception):
    """Excepción cuando el replay intenta operaciones prohibidas."""

    pass


def replay_prosecutor(trace: AuditTrace) -> ProsecutorResult:
    """
    REPLAY DETERMINISTA: Reproduce ejecución sin LLM ni vectorstore.

    GARANTÍAS:
    - NO llama a LLM
    - NO recalcula embeddings
    - NO accede a vectorstore
    - Resultado idéntico al original

    GATES:
    - Si falta snapshot crítico → FAIL
    - Si hash difiere → FAIL

    Args:
        trace: AuditTrace capturado en ejecución original

    Returns:
        ProsecutorResult reproducido desde snapshots

    Raises:
        ReplayViolationError: Si faltan datos críticos
    """
    # GATE: Verificar snapshots críticos
    if not trace.prosecutor_snapshot:
        raise ReplayViolationError("Falta prosecutor_snapshot crítico")

    if not trace.rag_snapshots:
        raise ReplayViolationError("Falta rag_snapshots crítico")

    # RECONSTRUIR ProsecutorResult desde snapshot
    snapshot = trace.prosecutor_snapshot

    # Reconstruir acusaciones completas
    acusaciones = []
    for acc_data in snapshot.acusaciones_data:
        # Usar from_dict o constructor directo
        acusaciones.append(AcusacionProbatoria(**acc_data))

    # Reconstruir acusaciones bloqueadas
    bloqueadas = []
    for bloc_data in snapshot.bloqueadas_data:
        bloqueadas.append(AcusacionBloqueada(**bloc_data))

    # Reconstruir resultado
    result = ProsecutorResult(
        case_id=snapshot.case_id,
        acusaciones=acusaciones,
        acusaciones_bloqueadas=bloqueadas,
        solicitud_evidencia=snapshot.solicitud_evidencia,
        total_acusaciones=snapshot.total_acusaciones,
        total_bloqueadas=snapshot.total_bloqueadas,
    )

    return result


def compute_result_hash(result: ProsecutorResult) -> str:
    """
    Calcula hash determinista del ProsecutorResult.

    GARANTÍA: Dos resultados idénticos producen el mismo hash.
    """
    # Serializar a dict ordenado
    result_dict = result.model_dump()
    serialized = json.dumps(result_dict, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def verify_replay(trace: AuditTrace, replayed_result: ProsecutorResult) -> bool:
    """
    Verifica que el replay produjo el resultado esperado.

    INVARIANTES:
    - result_hash debe coincidir
    - total_acusaciones debe coincidir
    - total_bloqueadas debe coincidir
    - pricing_fingerprint debe coincidir (ENDURECIMIENTO #7)

    Returns:
        True si el replay es idéntico al original
    """
    replayed_hash = compute_result_hash(replayed_result)

    if replayed_hash != trace.result_hash:
        return False

    if replayed_result.total_acusaciones != trace.prosecutor_snapshot.total_acusaciones:
        return False

    if replayed_result.total_bloqueadas != trace.prosecutor_snapshot.total_bloqueadas:
        return False

    # ENDURECIMIENTO #7: Verificar pricing_fingerprint
    if trace.budget_snapshot:
        # Si hay budget snapshot, verificar que pricing no cambió
        from app.core.finops.pricing import pricing_fingerprint

        current_fingerprint = pricing_fingerprint()

        if current_fingerprint != trace.budget_snapshot.pricing_fingerprint:
            # Pricing cambió desde que se capturó el trace
            return False

    return True
