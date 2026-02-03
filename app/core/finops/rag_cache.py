"""
RAG Cache (Hot + Cold).

ENDURECIMIENTO #7: Cache de retrieval para reducir costes de embeddings.

PRINCIPIO: Cache hit → NO se ejecuta retrieval ni embeddings.
"""
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

# ============================
# CACHE KEY
# ============================


def compute_rag_cache_key(
    case_id: str,
    query: str,
    top_k: int,
    filters: Optional[dict[str, Any]] = None,
    retriever_version: str = "1.0.0",
    vectorstore_manifest_hash: Optional[str] = None,
) -> str:
    """
    Calcula clave determinista para cache RAG.

    GARANTÍA: Mismos parámetros → misma clave.

    Args:
        case_id: ID del caso
        query: Query de búsqueda (normalizado)
        top_k: Número de resultados
        filters: Filtros aplicados
        retriever_version: Versión del retriever
        vectorstore_manifest_hash: Hash del manifest del vectorstore

    Returns:
        Hash SHA256 de los parámetros
    """
    # Normalizar query: strip + normalizar espacios + lowercase
    query_normalized = " ".join(query.strip().lower().split())

    # Construir estructura determinista
    data = {
        "case_id": case_id,
        "query": query_normalized,
        "top_k": top_k,
        "filters": filters or {},
        "retriever_version": retriever_version,
        "vectorstore_manifest_hash": vectorstore_manifest_hash or "",
    }

    serialized = json.dumps(data, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


# ============================
# CACHE ENTRY
# ============================


@dataclass
class RAGCacheEntry:
    """
    Entrada de cache RAG.

    NO almacena texto completo (riesgo PII), solo chunk_ids + scores.
    """

    key: str
    chunk_ids: list[str]
    scores: list[float]
    evidence_snapshot: dict[str, Any]  # total_chunks, valid_chunks, avg_similarity
    timestamp: float
    ttl_seconds: int = 3600  # 1 hora por defecto

    def is_expired(self) -> bool:
        """Verifica si la entrada ha expirado."""
        return (time.time() - self.timestamp) > self.ttl_seconds

    def to_dict(self) -> dict:
        return asdict(self)


# ============================
# HOT CACHE (IN-MEMORY LRU)
# ============================


class RAGHotCache:
    """
    Cache en memoria con LRU.

    PRINCIPIO: Evict cuando se excede max_size.
    """

    def __init__(self, max_size: int = 100):
        self._cache: dict[str, RAGCacheEntry] = {}
        self._max_size = max_size
        self._access_order: list[str] = []

    def get(self, key: str) -> Optional[RAGCacheEntry]:
        """Obtiene entrada del cache."""
        if key not in self._cache:
            return None

        entry = self._cache[key]

        # Verificar TTL
        if entry.is_expired():
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
            return None

        # Actualizar LRU
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

        return entry

    def put(self, entry: RAGCacheEntry):
        """Almacena entrada en cache."""
        # Evict si excede tamaño
        while len(self._cache) >= self._max_size:
            if self._access_order:
                oldest_key = self._access_order.pop(0)
                if oldest_key in self._cache:
                    del self._cache[oldest_key]

        self._cache[entry.key] = entry
        self._access_order.append(entry.key)

    def clear(self):
        """Limpia el cache."""
        self._cache.clear()
        self._access_order.clear()

    def size(self) -> int:
        """Retorna tamaño actual del cache."""
        return len(self._cache)


# ============================
# COLD CACHE (DISCO)
# ============================


class RAGColdCache:
    """
    Cache en disco (simulado con dict para tests).

    En producción, usar DB o filesystem con TTL.
    """

    def __init__(self):
        self._storage: dict[str, RAGCacheEntry] = {}

    def get(self, key: str) -> Optional[RAGCacheEntry]:
        """Obtiene entrada del cache en disco."""
        if key not in self._storage:
            return None

        entry = self._storage[key]

        # Verificar TTL
        if entry.is_expired():
            del self._storage[key]
            return None

        return entry

    def put(self, entry: RAGCacheEntry):
        """Almacena entrada en cache en disco."""
        self._storage[entry.key] = entry

    def clear(self):
        """Limpia el cache."""
        self._storage.clear()

    def size(self) -> int:
        """Retorna tamaño actual del cache."""
        return len(self._storage)


# ============================
# RAG CACHE MANAGER
# ============================


class RAGCacheManager:
    """
    Manager que coordina hot + cold cache.

    ENDURECIMIENTO #7: Primero intenta hot, luego cold, finalmente miss.
    """

    def __init__(
        self,
        hot_cache: Optional[RAGHotCache] = None,
        cold_cache: Optional[RAGColdCache] = None,
    ):
        self.hot_cache = hot_cache or RAGHotCache()
        self.cold_cache = cold_cache or RAGColdCache()

        # Métricas
        self.hot_hits = 0
        self.cold_hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[RAGCacheEntry]:
        """
        Obtiene entrada de cache (hot → cold → miss).

        Returns:
            RAGCacheEntry si hay hit, None si miss
        """
        # Intentar hot cache
        entry = self.hot_cache.get(key)
        if entry:
            self.hot_hits += 1
            return entry

        # Intentar cold cache
        entry = self.cold_cache.get(key)
        if entry:
            self.cold_hits += 1
            # Promover a hot cache
            self.hot_cache.put(entry)
            return entry

        # Miss
        self.misses += 1
        return None

    def put(self, entry: RAGCacheEntry):
        """Almacena entrada en hot y cold cache."""
        self.hot_cache.put(entry)
        self.cold_cache.put(entry)

    def clear(self):
        """Limpia ambos caches."""
        self.hot_cache.clear()
        self.cold_cache.clear()
        self.hot_hits = 0
        self.cold_hits = 0
        self.misses = 0

    def get_hit_rate_hot(self) -> float:
        """Calcula hit rate del hot cache."""
        total = self.hot_hits + self.cold_hits + self.misses
        if total == 0:
            return 0.0
        return self.hot_hits / total

    def get_hit_rate_cold(self) -> float:
        """Calcula hit rate del cold cache."""
        total = self.hot_hits + self.cold_hits + self.misses
        if total == 0:
            return 0.0
        return self.cold_hits / total

    def get_miss_rate(self) -> float:
        """Calcula miss rate."""
        total = self.hot_hits + self.cold_hits + self.misses
        if total == 0:
            return 0.0
        return self.misses / total


# ============================
# SINGLETON
# ============================

_global_rag_cache: Optional[RAGCacheManager] = None


def get_global_rag_cache() -> RAGCacheManager:
    """Obtiene el cache manager global."""
    global _global_rag_cache
    if _global_rag_cache is None:
        _global_rag_cache = RAGCacheManager()
    return _global_rag_cache


def reset_global_rag_cache():
    """Resetea el cache manager global (para tests)."""
    global _global_rag_cache
    _global_rag_cache = RAGCacheManager()
