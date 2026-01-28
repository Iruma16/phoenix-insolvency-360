"""
TESTS: RAG Cache Hot/Cold (Endurecimiento #7)

OBJETIVO: Validar cache de retrieval para reducir costes.

PRINCIPIO: Cache hit → NO se ejecuta retrieval ni embeddings.
"""
import time

import pytest

from app.core.finops.rag_cache import (
    RAGCacheEntry,
    RAGCacheManager,
    RAGColdCache,
    RAGHotCache,
    compute_rag_cache_key,
)

# ============================
# TEST 1: CACHE KEY
# ============================


def test_compute_rag_cache_key_deterministic():
    """INVARIANTE: Mismos parámetros → misma clave."""
    key1 = compute_rag_cache_key(
        case_id="CASE_001",
        query="test query",
        top_k=10,
        filters=None,
        retriever_version="1.0.0",
    )

    key2 = compute_rag_cache_key(
        case_id="CASE_001",
        query="test query",
        top_k=10,
        filters=None,
        retriever_version="1.0.0",
    )

    assert key1 == key2
    assert len(key1) == 64  # SHA256


def test_compute_rag_cache_key_normalizes_query():
    """Query normalizado: whitespace eliminado."""
    key1 = compute_rag_cache_key(
        case_id="CASE_001",
        query="  test   query  ",
        top_k=10,
    )

    key2 = compute_rag_cache_key(
        case_id="CASE_001",
        query="test query",
        top_k=10,
    )

    assert key1 == key2


def test_compute_rag_cache_key_different_params():
    """Parámetros diferentes → claves diferentes."""
    key1 = compute_rag_cache_key(
        case_id="CASE_001",
        query="test query",
        top_k=10,
    )

    key2 = compute_rag_cache_key(
        case_id="CASE_001",
        query="test query",
        top_k=20,  # Diferente
    )

    assert key1 != key2


# ============================
# TEST 2: CACHE ENTRY
# ============================


def test_cache_entry_is_expired():
    """Cache entry debe detectar expiración."""
    entry = RAGCacheEntry(
        key="key_001",
        chunk_ids=["c1", "c2"],
        scores=[0.9, 0.8],
        evidence_snapshot={"total_chunks": 2, "valid_chunks": 2},
        timestamp=time.time() - 7200,  # 2 horas atrás
        ttl_seconds=3600,  # 1 hora
    )

    assert entry.is_expired() is True


def test_cache_entry_not_expired():
    """Cache entry reciente no está expirado."""
    entry = RAGCacheEntry(
        key="key_001",
        chunk_ids=["c1", "c2"],
        scores=[0.9, 0.8],
        evidence_snapshot={"total_chunks": 2, "valid_chunks": 2},
        timestamp=time.time(),
        ttl_seconds=3600,
    )

    assert entry.is_expired() is False


# ============================
# TEST 3: HOT CACHE
# ============================


def test_hot_cache_miss():
    """Primera consulta → miss."""
    cache = RAGHotCache()

    entry = cache.get("key_001")

    assert entry is None


def test_hot_cache_hit():
    """Segunda consulta → hit."""
    cache = RAGHotCache()

    entry = RAGCacheEntry(
        key="key_001",
        chunk_ids=["c1", "c2"],
        scores=[0.9, 0.8],
        evidence_snapshot={},
        timestamp=time.time(),
    )

    cache.put(entry)

    retrieved = cache.get("key_001")

    assert retrieved is not None
    assert retrieved.key == "key_001"
    assert retrieved.chunk_ids == ["c1", "c2"]


def test_hot_cache_lru_eviction():
    """Hot cache debe evict cuando excede max_size."""
    cache = RAGHotCache(max_size=2)

    entry1 = RAGCacheEntry(
        key="key_001",
        chunk_ids=["c1"],
        scores=[0.9],
        evidence_snapshot={},
        timestamp=time.time(),
    )

    entry2 = RAGCacheEntry(
        key="key_002",
        chunk_ids=["c2"],
        scores=[0.8],
        evidence_snapshot={},
        timestamp=time.time(),
    )

    entry3 = RAGCacheEntry(
        key="key_003",
        chunk_ids=["c3"],
        scores=[0.7],
        evidence_snapshot={},
        timestamp=time.time(),
    )

    cache.put(entry1)
    cache.put(entry2)
    cache.put(entry3)  # Debe evict key_001

    assert cache.get("key_001") is None
    assert cache.get("key_002") is not None
    assert cache.get("key_003") is not None


# ============================
# TEST 4: COLD CACHE
# ============================


def test_cold_cache_miss():
    """Primera consulta → miss."""
    cache = RAGColdCache()

    entry = cache.get("key_001")

    assert entry is None


def test_cold_cache_hit():
    """Segunda consulta → hit."""
    cache = RAGColdCache()

    entry = RAGCacheEntry(
        key="key_001",
        chunk_ids=["c1", "c2"],
        scores=[0.9, 0.8],
        evidence_snapshot={},
        timestamp=time.time(),
    )

    cache.put(entry)

    retrieved = cache.get("key_001")

    assert retrieved is not None
    assert retrieved.key == "key_001"


# ============================
# TEST 5: CACHE MANAGER
# ============================


def test_cache_manager_first_query_miss():
    """Primera query → miss."""
    manager = RAGCacheManager()

    entry = manager.get("key_001")

    assert entry is None
    assert manager.misses == 1


def test_cache_manager_second_query_hit_hot():
    """Segunda query → hot hit."""
    manager = RAGCacheManager()

    entry = RAGCacheEntry(
        key="key_001",
        chunk_ids=["c1", "c2"],
        scores=[0.9, 0.8],
        evidence_snapshot={},
        timestamp=time.time(),
    )

    manager.put(entry)

    # Primera consulta después de put → hot hit
    retrieved = manager.get("key_001")

    assert retrieved is not None
    assert manager.hot_hits == 1
    assert manager.misses == 0


def test_cache_manager_cold_promotion():
    """Cold hit → promoción a hot cache."""
    hot_cache = RAGHotCache()
    cold_cache = RAGColdCache()
    manager = RAGCacheManager(hot_cache=hot_cache, cold_cache=cold_cache)

    # Almacenar en cold solamente
    entry = RAGCacheEntry(
        key="key_001",
        chunk_ids=["c1"],
        scores=[0.9],
        evidence_snapshot={},
        timestamp=time.time(),
    )
    cold_cache.put(entry)

    # Primera consulta → cold hit + promoción a hot
    retrieved = manager.get("key_001")

    assert retrieved is not None
    assert manager.cold_hits == 1

    # Segunda consulta → hot hit
    retrieved2 = manager.get("key_001")

    assert retrieved2 is not None
    assert manager.hot_hits == 1


def test_cache_manager_hit_rates():
    """Cache manager debe calcular hit rates."""
    manager = RAGCacheManager()

    # 2 misses
    manager.get("key_001")
    manager.get("key_002")

    # 1 put + 1 hot hit
    entry = RAGCacheEntry(
        key="key_003",
        chunk_ids=["c1"],
        scores=[0.9],
        evidence_snapshot={},
        timestamp=time.time(),
    )
    manager.put(entry)
    manager.get("key_003")

    # Total: 2 misses, 1 hot hit
    assert manager.hot_hits == 1
    assert manager.misses == 2
    assert manager.get_hit_rate_hot() == pytest.approx(1 / 3)
    assert manager.get_miss_rate() == pytest.approx(2 / 3)


# ============================
# RESUMEN DE TESTS
# ============================
"""
COBERTURA:

1. ✅ compute_rag_cache_key determinista
2. ✅ Query normalizado
3. ✅ Parámetros diferentes → claves diferentes
4. ✅ Cache entry detecta expiración
5. ✅ Hot cache miss + hit
6. ✅ Hot cache LRU eviction
7. ✅ Cold cache miss + hit
8. ✅ Cache manager primera query miss
9. ✅ Cache manager segunda query hot hit
10. ✅ Cold hit → promoción a hot
11. ✅ Cache manager calcula hit rates

TOTAL: 13 tests deterministas

INVARIANTES CERTIFICADOS:
- INVARIANTE 1: Mismos parámetros → misma clave cache
- INVARIANTE 2: Cache entry detecta expiración por TTL
- INVARIANTE 3: Hot cache evict LRU cuando excede max_size
- INVARIANTE 4: Cold hit → promoción a hot cache
- INVARIANTE 5: Cache manager calcula hit rates correctamente
"""
