"""
Semantic Cache para prompts equivalentes.

ENDURECIMIENTO #7: Cache de respuestas LLM por prompt canonicalizado.

PRINCIPIO: Prompts equivalentes → misma respuesta cached.
"""
import hashlib
import json
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict


# ============================
# PROMPT CANONICALIZATION
# ============================

def canonicalize_prompt(prompt: str) -> str:
    """
    Canonicaliza un prompt para cache.
    
    GARANTÍA: Prompts equivalentes → misma clave.
    
    Args:
        prompt: Prompt original
    
    Returns:
        Prompt canonicalizado
    """
    # Strip whitespace
    canonical = prompt.strip()
    
    # Normalizar espacios múltiples
    canonical = " ".join(canonical.split())
    
    # Lowercase (opcional, depende del caso de uso)
    # canonical = canonical.lower()
    
    return canonical


def compute_semantic_cache_key(
    system_prompt: Optional[str],
    user_prompt: str,
    tool_spec: Optional[Dict[str, Any]],
    model: str,
    temperature: float,
    top_p: float,
    seed: Optional[int] = None,
    policy_hash: Optional[str] = None,
) -> str:
    """
    Calcula clave determinista para semantic cache.
    
    GARANTÍA: Mismos parámetros → misma clave.
    
    Args:
        system_prompt: System prompt (opcional)
        user_prompt: User prompt
        tool_spec: Especificación de tools (opcional)
        model: Modelo
        temperature: Temperature
        top_p: Top-p
        seed: Seed (opcional)
        policy_hash: Hash de la policy (disclaimer version, etc.)
    
    Returns:
        Hash SHA256
    """
    # Canonicalizar prompts
    system_canonical = canonicalize_prompt(system_prompt) if system_prompt else ""
    user_canonical = canonicalize_prompt(user_prompt)
    
    # Hash de system prompt
    system_hash = hashlib.sha256(system_canonical.encode()).hexdigest()
    
    # Hash de user prompt
    user_hash = hashlib.sha256(user_canonical.encode()).hexdigest()
    
    # Hash de tool spec (si existe)
    tool_hash = ""
    if tool_spec:
        tool_serialized = json.dumps(tool_spec, sort_keys=True)
        tool_hash = hashlib.sha256(tool_serialized.encode()).hexdigest()
    
    # Construir clave
    data = {
        "system_hash": system_hash,
        "user_hash": user_hash,
        "tool_hash": tool_hash,
        "model": model,
        "temperature": temperature,
        "top_p": top_p,
        "seed": seed,
        "policy_hash": policy_hash or "",
    }
    
    serialized = json.dumps(data, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


# ============================
# CACHE ENTRY
# ============================

@dataclass
class SemanticCacheEntry:
    """
    Entrada de semantic cache.
    
    Almacena respuesta completa del LLM.
    """
    key: str
    response: str
    input_tokens: int
    output_tokens: int
    model: str
    timestamp: float
    ttl_seconds: int = 3600  # 1 hora por defecto
    
    def is_expired(self) -> bool:
        """Verifica si la entrada ha expirado."""
        return (time.time() - self.timestamp) > self.ttl_seconds
    
    def to_dict(self) -> dict:
        return asdict(self)


# ============================
# SEMANTIC CACHE
# ============================

class SemanticCache:
    """
    Cache de respuestas LLM por prompt canonicalizado.
    
    ENDURECIMIENTO #7: Reduce costes reutilizando respuestas.
    """
    
    def __init__(self, max_size: int = 500):
        self._cache: Dict[str, SemanticCacheEntry] = {}
        self._max_size = max_size
        self._access_order: list[str] = []
        
        # Métricas
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[SemanticCacheEntry]:
        """Obtiene entrada del cache."""
        if key not in self._cache:
            self.misses += 1
            return None
        
        entry = self._cache[key]
        
        # Verificar TTL
        if entry.is_expired():
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
            self.misses += 1
            return None
        
        # Actualizar LRU
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)
        
        self.hits += 1
        return entry
    
    def put(self, entry: SemanticCacheEntry):
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
        self.hits = 0
        self.misses = 0
    
    def size(self) -> int:
        """Retorna tamaño actual del cache."""
        return len(self._cache)
    
    def get_hit_rate(self) -> float:
        """Calcula hit rate."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


# ============================
# SINGLETON
# ============================

_global_semantic_cache: Optional[SemanticCache] = None


def get_global_semantic_cache() -> SemanticCache:
    """Obtiene el semantic cache global."""
    global _global_semantic_cache
    if _global_semantic_cache is None:
        _global_semantic_cache = SemanticCache()
    return _global_semantic_cache


def reset_global_semantic_cache():
    """Resetea el semantic cache global (para tests)."""
    global _global_semantic_cache
    _global_semantic_cache = SemanticCache()

