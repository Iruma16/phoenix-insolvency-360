"""
TESTS: FinOps Entry Points (Endurecimiento #7 - CIERRE HARD)

OBJETIVO: Validar puntos únicos obligatorios para operaciones con coste.

PRINCIPIO: PROHIBIDO llamar proveedor fuera de entry points.
"""
import pytest
from unittest.mock import Mock

from app.core.finops.entry_points import (
    run_embeddings,
    run_retrieve,
    run_llm_call,
    verify_cost_coherence,
    verify_trace_coherence,
    FinOpsBypassError,
    EmbeddingsResult,
    RetrieveResult,
    LLMCallResult,
)
from app.core.finops.budget import BudgetLedger
from app.core.finops.exceptions import BudgetExceededException
from app.core.finops.rag_cache import RAGCacheManager
from app.core.finops.semantic_cache import SemanticCache
from app.core.finops.policy import LLMCallPolicy


# ============================
# TEST 1: EMBEDDINGS ENTRY POINT
# ============================

def test_run_embeddings_requires_budget():
    """GATE: run_embeddings sin presupuesto → BudgetExceededException."""
    ledger = BudgetLedger()
    ledger.initialize_budget("CASE_001", budget_usd=0.000001)  # Presupuesto ínfimo
    
    mock_provider = Mock(return_value=[[0.1, 0.2, 0.3]])
    
    # Texto muy largo para forzar coste alto
    long_text = "x" * 10000  # 10K caracteres = ~2.5K tokens
    
    with pytest.raises(BudgetExceededException):
        run_embeddings(
            texts=[long_text],
            model="text-embedding-3-small",
            case_id="CASE_001",
            provider_func=mock_provider,
            ledger=ledger,
        )
    
    # Verificar que NO se llamó al provider
    assert mock_provider.call_count == 0


def test_run_embeddings_with_budget():
    """run_embeddings con presupuesto OK ejecuta y registra coste."""
    ledger = BudgetLedger()
    ledger.initialize_budget("CASE_001", budget_usd=10.0)
    
    mock_provider = Mock(return_value=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    
    # Textos largos para generar coste real
    long_text = "test " * 500  # ~2500 caracteres = ~625 tokens
    
    result = run_embeddings(
        texts=[long_text, long_text],
        model="text-embedding-3-small",
        case_id="CASE_001",
        provider_func=mock_provider,
        trace_id="trace_001",
        ledger=ledger,
    )
    
    # Verificar resultado
    assert isinstance(result, EmbeddingsResult)
    assert len(result.embeddings) == 2
    assert result.cost_usd > 0
    assert result.cached is False
    assert result.trace_id == "trace_001"
    
    # Verificar provider llamado
    assert mock_provider.call_count == 1
    
    # Verificar ledger actualizado
    entries = ledger.get_entries(case_id="CASE_001")
    assert len(entries) == 1
    assert entries[0].phase == "embed"
    assert entries[0].trace_id == "trace_001"


# ============================
# TEST 2: RETRIEVE ENTRY POINT
# ============================

def test_run_retrieve_cache_miss():
    """Primera query → cache miss → ejecuta retriever."""
    cache_manager = RAGCacheManager()
    
    mock_retriever = Mock(return_value=(
        ["chunk1", "chunk2"],
        [0.9, 0.8],
        {"total_chunks": 2, "valid_chunks": 2}
    ))
    
    result = run_retrieve(
        case_id="CASE_001",
        query="test query",
        top_k=10,
        retriever_func=mock_retriever,
        cache_manager=cache_manager,
    )
    
    assert isinstance(result, RetrieveResult)
    assert result.cached is False
    assert result.cache_type is None
    assert len(result.chunk_ids) == 2
    assert mock_retriever.call_count == 1


def test_run_retrieve_cache_hit():
    """Segunda query → cache hit → NO ejecuta retriever."""
    cache_manager = RAGCacheManager()
    
    mock_retriever = Mock(return_value=(
        ["chunk1", "chunk2"],
        [0.9, 0.8],
        {"total_chunks": 2, "valid_chunks": 2}
    ))
    
    # Primera query
    run_retrieve(
        case_id="CASE_001",
        query="test query",
        top_k=10,
        retriever_func=mock_retriever,
        cache_manager=cache_manager,
    )
    
    # Segunda query (mismos parámetros)
    result = run_retrieve(
        case_id="CASE_001",
        query="test query",
        top_k=10,
        retriever_func=mock_retriever,
        cache_manager=cache_manager,
    )
    
    # Verificar cache hit
    assert result.cached is True
    assert result.cache_type in ["hot", "cold"]
    
    # Verificar que NO se llamó al retriever segunda vez
    assert mock_retriever.call_count == 1


# ============================
# TEST 3: LLM CALL ENTRY POINT
# ============================

def test_run_llm_call_blocked_by_policy():
    """GATE: Policy bloquea → NO se llama al LLM."""
    ledger = BudgetLedger()
    ledger.initialize_budget("CASE_001", budget_usd=10.0)
    
    policy = LLMCallPolicy()
    semantic_cache = SemanticCache()
    
    mock_llm = Mock(return_value=("Response", 100, 50))
    
    result = run_llm_call(
        case_id="CASE_001",
        phase="llm_explain",
        system_prompt="System",
        user_prompt="User",
        model="gpt-4o-mini",
        temperature=0.7,
        top_p=1.0,
        has_evidence=False,  # BLOQUEA
        insufficient_evidence=False,
        no_response_reason=None,
        llm_func=mock_llm,
        policy=policy,
        ledger=ledger,
        semantic_cache=semantic_cache,
    )
    
    # Verificar resultado bloqueado
    assert isinstance(result, LLMCallResult)
    assert result.response is None
    assert result.degraded_mode is True
    assert result.decision.allow_call is False
    
    # Verificar que NO se llamó al LLM
    assert mock_llm.call_count == 0


def test_run_llm_call_blocked_by_budget():
    """GATE: Presupuesto insuficiente → BudgetExceededException."""
    ledger = BudgetLedger()
    ledger.initialize_budget("CASE_001", budget_usd=0.000001)  # Presupuesto ínfimo
    
    policy = LLMCallPolicy()
    semantic_cache = SemanticCache()
    
    mock_llm = Mock(return_value=("Response", 100, 50))
    
    # Prompt muy largo para forzar coste alto
    long_prompt = "x" * 10000  # ~2.5K tokens
    
    with pytest.raises(BudgetExceededException):
        run_llm_call(
            case_id="CASE_001",
            phase="llm_explain",
            system_prompt="System",
            user_prompt=long_prompt,
            model="gpt-4o-mini",
            temperature=0.7,
            top_p=1.0,
            has_evidence=True,
            insufficient_evidence=False,
            no_response_reason=None,
            llm_func=mock_llm,
            policy=policy,
            ledger=ledger,
            semantic_cache=semantic_cache,
        )
    
    # Verificar que NO se llamó al LLM
    assert mock_llm.call_count == 0


def test_run_llm_call_semantic_cache_hit():
    """Semantic cache hit → NO se llama al LLM."""
    ledger = BudgetLedger()
    ledger.initialize_budget("CASE_001", budget_usd=10.0)
    
    policy = LLMCallPolicy()
    semantic_cache = SemanticCache()
    
    mock_llm = Mock(return_value=("Response", 100, 50))
    
    # Primera llamada
    result1 = run_llm_call(
        case_id="CASE_001",
        phase="llm_explain",
        system_prompt="System",
        user_prompt="Test prompt",
        model="gpt-4o-mini",
        temperature=0.7,
        top_p=1.0,
        has_evidence=True,
        insufficient_evidence=False,
        no_response_reason=None,
        llm_func=mock_llm,
        trace_id="trace_001",
        policy=policy,
        ledger=ledger,
        semantic_cache=semantic_cache,
    )
    
    # Segunda llamada (mismos parámetros)
    result2 = run_llm_call(
        case_id="CASE_001",
        phase="llm_explain",
        system_prompt="System",
        user_prompt="Test prompt",
        model="gpt-4o-mini",
        temperature=0.7,
        top_p=1.0,
        has_evidence=True,
        insufficient_evidence=False,
        no_response_reason=None,
        llm_func=mock_llm,
        trace_id="trace_002",
        policy=policy,
        ledger=ledger,
        semantic_cache=semantic_cache,
    )
    
    # Verificar primera llamada OK
    assert result1.cached is False
    assert result1.cost_usd > 0
    
    # Verificar segunda llamada cache hit
    assert result2.cached is True
    assert result2.cost_usd == 0.0  # Cache → sin coste
    
    # Verificar que LLM solo se llamó una vez
    assert mock_llm.call_count == 1


def test_run_llm_call_records_cost():
    """LLM call siempre registra coste en ledger."""
    ledger = BudgetLedger()
    ledger.initialize_budget("CASE_001", budget_usd=10.0)
    
    policy = LLMCallPolicy()
    semantic_cache = SemanticCache()
    
    mock_llm = Mock(return_value=("Response", 100, 50))
    
    result = run_llm_call(
        case_id="CASE_001",
        phase="llm_explain",
        system_prompt="System",
        user_prompt="Test",
        model="gpt-4o-mini",
        temperature=0.7,
        top_p=1.0,
        has_evidence=True,
        insufficient_evidence=False,
        no_response_reason=None,
        llm_func=mock_llm,
        trace_id="trace_001",
        policy=policy,
        ledger=ledger,
        semantic_cache=semantic_cache,
    )
    
    # Verificar ledger
    entries = ledger.get_entries(case_id="CASE_001")
    assert len(entries) == 1
    assert entries[0].phase == "llm_explain"
    assert entries[0].input_tokens == 100
    assert entries[0].output_tokens == 50
    assert entries[0].trace_id == "trace_001"
    assert entries[0].cost_usd > 0


# ============================
# TEST 4: COHERENCE GATES
# ============================

def test_verify_cost_coherence_ok():
    """verify_cost_coherence OK si hay entrada en ledger."""
    ledger = BudgetLedger()
    ledger.record_entry(
        case_id="CASE_001",
        phase="embed",
        provider="openai",
        model="text-embedding-3-small",
        input_tokens=100,
        output_tokens=0,
        cost_usd=0.00002,
    )
    
    # No debe lanzar excepción
    assert verify_cost_coherence(cost_usd=0.00002, case_id="CASE_001", ledger=ledger)


def test_verify_cost_coherence_fails_without_ledger_entry():
    """GATE: cost_usd > 0 sin BudgetEntry → FinOpsBypassError."""
    ledger = BudgetLedger()
    
    with pytest.raises(FinOpsBypassError, match="FINOPS_BYPASS"):
        verify_cost_coherence(cost_usd=1.0, case_id="CASE_001", ledger=ledger)


def test_verify_trace_coherence_ok():
    """verify_trace_coherence OK si todas las entradas tienen trace_id."""
    ledger = BudgetLedger()
    ledger.record_entry(
        case_id="CASE_001",
        phase="embed",
        provider="openai",
        model="text-embedding-3-small",
        input_tokens=100,
        output_tokens=0,
        cost_usd=0.00002,
        trace_id="trace_001",
    )
    
    # No debe lanzar excepción
    assert verify_trace_coherence(ledger=ledger)


def test_verify_trace_coherence_fails_without_trace_id():
    """GATE: Ledger sin trace_id → FinOpsBypassError."""
    ledger = BudgetLedger()
    ledger.record_entry(
        case_id="CASE_001",
        phase="embed",
        provider="openai",
        model="text-embedding-3-small",
        input_tokens=100,
        output_tokens=0,
        cost_usd=0.00002,
        trace_id=None,  # SIN trace_id
    )
    
    with pytest.raises(FinOpsBypassError, match="sin trace_id"):
        verify_trace_coherence(ledger=ledger)


# ============================
# RESUMEN DE TESTS
# ============================
"""
COBERTURA:

1. ✅ run_embeddings requiere presupuesto
2. ✅ run_embeddings con presupuesto OK
3. ✅ run_retrieve cache miss
4. ✅ run_retrieve cache hit
5. ✅ run_llm_call bloqueado por policy
6. ✅ run_llm_call bloqueado por budget
7. ✅ run_llm_call semantic cache hit
8. ✅ run_llm_call registra coste
9. ✅ verify_cost_coherence OK
10. ✅ verify_cost_coherence falla sin ledger entry
11. ✅ verify_trace_coherence OK
12. ✅ verify_trace_coherence falla sin trace_id

TOTAL: 12 tests deterministas

INVARIANTES CERTIFICADOS:
- INVARIANTE 1: run_embeddings sin presupuesto → BudgetExceededException + NO llama provider
- INVARIANTE 2: run_retrieve cache hit → NO ejecuta retriever
- INVARIANTE 3: run_llm_call policy bloquea → NO llama LLM + degraded_mode
- INVARIANTE 4: run_llm_call budget insuficiente → BudgetExceededException + NO llama LLM
- INVARIANTE 5: run_llm_call cache hit → NO llama LLM + cost_usd=0
- INVARIANTE 6: run_llm_call SIEMPRE registra coste en ledger
- INVARIANTE 7: cost_usd > 0 sin BudgetEntry → FinOpsBypassError
- INVARIANTE 8: Ledger sin trace_id → FinOpsBypassError
"""

