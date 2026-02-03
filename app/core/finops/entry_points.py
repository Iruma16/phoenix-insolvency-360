"""
FinOps Entry Points: Puntos únicos obligatorios para operaciones con coste.

ENDURECIMIENTO #7 (CIERRE HARD): Convertir FinOps en LEY TÉCNICA.

PRINCIPIO: PROHIBIDO llamar proveedor fuera de estos entry points.

FASE 1 (ENDURECIMIENTO 3.0): Guards añadidos para enforcement del contrato.
"""
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.core.exceptions import FinOpsBypassError

from .budget import BudgetLedger, get_global_ledger
from .gates import check_budget_or_fail, record_actual_cost
from .policy import LLMCallDecision, LLMCallPolicy, get_global_llm_policy
from .rag_cache import RAGCacheEntry, RAGCacheManager, compute_rag_cache_key, get_global_rag_cache
from .semantic_cache import (
    SemanticCache,
    SemanticCacheEntry,
    compute_semantic_cache_key,
    get_global_semantic_cache,
)

# ============================
# EMBEDDINGS ENTRY POINT
# ============================


@dataclass
class EmbeddingsResult:
    """Resultado de run_embeddings."""

    embeddings: list[list[float]]
    input_tokens: int
    cost_usd: float
    cached: bool
    trace_id: Optional[str] = None


def run_embeddings(
    texts: list[str],
    model: str,
    case_id: str,
    provider_func: Callable[[list[str], str], list[list[float]]],
    trace_id: Optional[str] = None,
    ledger: Optional[BudgetLedger] = None,
) -> EmbeddingsResult:
    """
    SINGLE ENTRY POINT para embeddings.

    ORDEN OBLIGATORIO:
    1. Budget gate
    2. Proveedor (si pasa gate)
    3. Record cost

    PROHIBIDO llamar provider_func directamente fuera de este punto.

    FASE 1 GUARD: Valida que provider_func no es None.

    Args:
        texts: Textos a embedder
        model: Modelo de embeddings
        case_id: ID del caso
        provider_func: Función del proveedor (ej. openai.embeddings.create)
        trace_id: ID del trace (opcional)
        ledger: Ledger (si None, usa global)

    Returns:
        EmbeddingsResult con embeddings y coste

    Raises:
        BudgetExceededException: Si presupuesto insuficiente
        FinOpsBypassError: Si provider_func es None
    """
    # FASE 1 GUARD: Validar provider_func
    if provider_func is None:
        raise FinOpsBypassError(
            operation="run_embeddings", reason="provider_func no puede ser None"
        )

    if ledger is None:
        ledger = get_global_ledger()

    # Estimar tokens (aproximación: 1 token ~ 4 caracteres)
    total_chars = sum(len(text) for text in texts)
    estimated_tokens = max(1, total_chars // 4)

    # GATE 1: Budget
    check_budget_or_fail(
        case_id=case_id,
        phase="embed",
        model=model,
        estimated_input_tokens=estimated_tokens,
        estimated_output_tokens=0,
        ledger=ledger,
    )

    # EJECUTAR: Proveedor
    embeddings = provider_func(texts, model)

    # REGISTRAR: Coste actual
    record_actual_cost(
        case_id=case_id,
        phase="embed",
        provider="openai",  # TODO: detectar provider desde model
        model=model,
        input_tokens=estimated_tokens,
        output_tokens=0,
        cost_usd=None,  # Se calcula desde pricing table
        trace_id=trace_id,
        ledger=ledger,
    )

    # Obtener coste registrado
    entries = ledger.get_entries(case_id=case_id, phase="embed")
    last_cost = entries[-1].cost_usd if entries else 0.0

    return EmbeddingsResult(
        embeddings=embeddings,
        input_tokens=estimated_tokens,
        cost_usd=last_cost,
        cached=False,
        trace_id=trace_id,
    )


# ============================
# RETRIEVE ENTRY POINT
# ============================


@dataclass
class RetrieveResult:
    """Resultado de run_retrieve."""

    chunk_ids: list[str]
    scores: list[float]
    evidence_snapshot: dict[str, Any]
    cached: bool
    cache_type: Optional[str] = None  # "hot", "cold", None


def run_retrieve(
    case_id: str,
    query: str,
    top_k: int,
    retriever_func: Callable[[str, str, int], tuple],
    filters: Optional[dict[str, Any]] = None,
    retriever_version: str = "1.0.0",
    vectorstore_manifest_hash: Optional[str] = None,
    cache_manager: Optional[RAGCacheManager] = None,
) -> RetrieveResult:
    """
    SINGLE ENTRY POINT para retrieve.

    ORDEN OBLIGATORIO:
    1. Cache (hot → cold)
    2. Retriever (si miss)
    3. Cache write

    FASE 1 GUARD: Valida que retriever_func no es None.

    Args:
        case_id: ID del caso
        query: Query de búsqueda
        top_k: Número de resultados
        retriever_func: Función de retrieval (retorna (chunk_ids, scores, evidence))
        filters: Filtros opcionales
        retriever_version: Versión del retriever
        vectorstore_manifest_hash: Hash del manifest
        cache_manager: Cache manager (si None, usa global)

    Returns:
        RetrieveResult con chunks y metadata de cache

    Raises:
        FinOpsBypassError: Si retriever_func es None
    """
    # FASE 1 GUARD: Validar retriever_func
    if retriever_func is None:
        raise FinOpsBypassError(operation="run_retrieve", reason="retriever_func no puede ser None")

    if cache_manager is None:
        cache_manager = get_global_rag_cache()

    # Calcular cache key
    cache_key = compute_rag_cache_key(
        case_id=case_id,
        query=query,
        top_k=top_k,
        filters=filters,
        retriever_version=retriever_version,
        vectorstore_manifest_hash=vectorstore_manifest_hash,
    )

    # INTENTAR: Cache
    cached_entry = cache_manager.get(cache_key)

    if cached_entry:
        # Cache hit
        cache_type = "hot" if cache_manager.hot_hits > 0 else "cold"

        return RetrieveResult(
            chunk_ids=cached_entry.chunk_ids,
            scores=cached_entry.scores,
            evidence_snapshot=cached_entry.evidence_snapshot,
            cached=True,
            cache_type=cache_type,
        )

    # Cache miss: EJECUTAR retriever
    chunk_ids, scores, evidence_snapshot = retriever_func(case_id, query, top_k)

    # ESCRIBIR: Cache
    import time

    cache_entry = RAGCacheEntry(
        key=cache_key,
        chunk_ids=chunk_ids,
        scores=scores,
        evidence_snapshot=evidence_snapshot,
        timestamp=time.time(),
    )
    cache_manager.put(cache_entry)

    return RetrieveResult(
        chunk_ids=chunk_ids,
        scores=scores,
        evidence_snapshot=evidence_snapshot,
        cached=False,
        cache_type=None,
    )


# ============================
# LLM CALL ENTRY POINT
# ============================


@dataclass
class LLMCallResult:
    """Resultado de run_llm_call."""

    response: Optional[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cached: bool
    degraded_mode: bool
    decision: LLMCallDecision
    trace_id: Optional[str] = None


def run_llm_call(
    case_id: str,
    phase: str,
    system_prompt: Optional[str],
    user_prompt: str,
    model: str,
    temperature: float,
    top_p: float,
    has_evidence: bool,
    insufficient_evidence: bool,
    no_response_reason: Optional[str],
    llm_func: Callable[[str, str, str, float, float], tuple],
    tool_spec: Optional[dict[str, Any]] = None,
    seed: Optional[int] = None,
    policy_hash: Optional[str] = None,
    trace_id: Optional[str] = None,
    policy: Optional[LLMCallPolicy] = None,
    ledger: Optional[BudgetLedger] = None,
    semantic_cache: Optional[SemanticCache] = None,
) -> LLMCallResult:
    """
    SINGLE ENTRY POINT para LLM calls.

    ORDEN OBLIGATORIO:
    1. Policy evaluation
    2. Budget gate (si policy permite)
    3. Semantic cache (si policy permite)
    4. LLM call (si cache miss)
    5. Record cost

    PROHIBIDO llamar llm_func directamente fuera de este punto.

    FASE 1 GUARD: Valida que llm_func no es None y policy + budget pasan.

    Args:
        case_id: ID del caso
        phase: Fase de ejecución
        system_prompt: System prompt
        user_prompt: User prompt
        model: Modelo LLM
        temperature: Temperature
        top_p: Top-p
        has_evidence: Hay evidencia
        insufficient_evidence: Evidencia insuficiente
        no_response_reason: Razón de NO_RESPONSE
        llm_func: Función LLM (retorna (response, input_tokens, output_tokens))
        tool_spec: Especificación de tools
        seed: Seed (opcional)
        policy_hash: Hash de policy
        trace_id: ID del trace
        policy: Policy (si None, usa global)
        ledger: Ledger (si None, usa global)
        semantic_cache: Semantic cache (si None, usa global)

    Returns:
        LLMCallResult con respuesta y metadata

    Raises:
        BudgetExceededException: Si presupuesto insuficiente
        FinOpsBypassError: Si llm_func es None
    """
    # FASE 1 GUARD: Validar llm_func
    if llm_func is None:
        raise FinOpsBypassError(operation="run_llm_call", reason="llm_func no puede ser None")

    if policy is None:
        policy = get_global_llm_policy()

    if ledger is None:
        ledger = get_global_ledger()

    if semantic_cache is None:
        semantic_cache = get_global_semantic_cache()

    # GATE 1: Policy
    budget = ledger.get_budget(case_id)
    decision = policy.evaluate(
        case_id=case_id,
        phase=phase,
        has_evidence=has_evidence,
        insufficient_evidence=insufficient_evidence,
        no_response_reason=no_response_reason,
        budget_available=budget.remaining_usd > 0,
    )

    if not decision.allow_call:
        # BLOQUEADO por policy
        return LLMCallResult(
            response=None,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            cached=False,
            degraded_mode=decision.degraded_mode,
            decision=decision,
            trace_id=trace_id,
        )

    # GATE 2: Budget (estimación conservadora)
    estimated_input = len(user_prompt) // 4  # Aproximación
    estimated_output = estimated_input // 2  # Conservador

    check_budget_or_fail(
        case_id=case_id,
        phase=phase,
        model=model,
        estimated_input_tokens=estimated_input,
        estimated_output_tokens=estimated_output,
        ledger=ledger,
    )

    # GATE 3: Semantic cache
    cache_key = compute_semantic_cache_key(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_spec=tool_spec,
        model=model,
        temperature=temperature,
        top_p=top_p,
        seed=seed,
        policy_hash=policy_hash,
    )

    cached_entry = semantic_cache.get(cache_key)

    if cached_entry:
        # Cache hit: NO llamar LLM
        return LLMCallResult(
            response=cached_entry.response,
            input_tokens=cached_entry.input_tokens,
            output_tokens=cached_entry.output_tokens,
            cost_usd=0.0,  # Cache hit → sin coste
            cached=True,
            degraded_mode=False,
            decision=decision,
            trace_id=trace_id,
        )

    # Cache miss: EJECUTAR LLM
    response, input_tokens, output_tokens = llm_func(
        system_prompt, user_prompt, model, temperature, top_p
    )

    # REGISTRAR: Coste
    record_actual_cost(
        case_id=case_id,
        phase=phase,
        provider="openai",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=None,
        trace_id=trace_id,
        ledger=ledger,
    )

    # Obtener coste registrado
    entries = ledger.get_entries(case_id=case_id)
    last_cost = entries[-1].cost_usd if entries else 0.0

    # ESCRIBIR: Semantic cache
    import time

    cache_entry = SemanticCacheEntry(
        key=cache_key,
        response=response,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        timestamp=time.time(),
    )
    semantic_cache.put(cache_entry)

    return LLMCallResult(
        response=response,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=last_cost,
        cached=False,
        degraded_mode=False,
        decision=decision,
        trace_id=trace_id,
    )


# ============================
# COHERENCE GATES
# ============================


def verify_cost_coherence(
    cost_usd: float,
    case_id: str,
    ledger: Optional[BudgetLedger] = None,
) -> bool:
    """
    GATE FINAL: Verifica coherencia de coste vs ledger.

    INVARIANTE: Si cost_usd > 0 → DEBE existir BudgetEntry.

    Args:
        cost_usd: Coste reportado
        case_id: ID del caso
        ledger: Ledger (si None, usa global)

    Returns:
        True si coherente

    Raises:
        FinOpsBypassError: Si hay incoherencia
    """
    if ledger is None:
        ledger = get_global_ledger()

    if cost_usd > 0:
        entries = ledger.get_entries(case_id=case_id)

        if not entries:
            raise FinOpsBypassError(
                operation="cost_reporting",
                reason=f"cost_usd={cost_usd} pero ledger vacío para case_id={case_id}",
            )

    return True


def verify_trace_coherence(
    ledger: Optional[BudgetLedger] = None,
) -> bool:
    """
    GATE FINAL: Verifica que todas las entradas tengan trace_id.

    INVARIANTE: Ledger registra gasto → DEBE tener trace_id.

    Args:
        ledger: Ledger (si None, usa global)

    Returns:
        True si coherente

    Raises:
        FinOpsBypassError: Si hay entradas sin trace_id
    """
    if ledger is None:
        ledger = get_global_ledger()

    entries_without_trace = [e for e in ledger.get_entries() if e.trace_id is None]

    if entries_without_trace:
        raise FinOpsBypassError(
            operation="ledger_integrity",
            reason=f"{len(entries_without_trace)} entradas sin trace_id",
        )

    return True
