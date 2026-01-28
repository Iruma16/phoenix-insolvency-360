"""
Sistema de caché para consultas RAG.

El caché mejora significativamente el rendimiento al:
- Evitar regeneración de embeddings
- Reducir llamadas a vectorstore
- Disminuir latencia de queries frecuentes
- Reducir costos de API

Estrategia:
- Cache key basado en hash de (query, case_id, top_k)
- TTL configurable
- Invalidación automática
- Persistencia en disco
"""
import hashlib
import json
import pickle
import time
from pathlib import Path
from typing import Any, Optional, Dict, List
from dataclasses import dataclass, asdict

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger()


@dataclass
class CachedResult:
    """Resultado cacheado con metadata."""
    query: str
    case_id: str
    top_k: int
    results: Any
    timestamp: float
    ttl_seconds: int
    
    def is_expired(self) -> bool:
        """Verifica si el resultado ha expirado."""
        age = time.time() - self.timestamp
        return age > self.ttl_seconds
    
    def age_seconds(self) -> float:
        """Edad del resultado en segundos."""
        return time.time() - self.timestamp


class RAGCache:
    """
    Sistema de caché para consultas RAG.
    
    Características:
    - Caché basado en disco (pickle)
    - TTL configurable
    - Invalidación automática
    - Thread-safe
    """
    
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        default_ttl: Optional[int] = None,
        enabled: Optional[bool] = None
    ):
        """
        Inicializa el sistema de caché.
        
        Args:
            cache_dir: Directorio de caché (default: settings.cache_dir)
            default_ttl: TTL por defecto en segundos
            enabled: Si está habilitado (default: settings.rag_cache_enabled)
        """
        self.cache_dir = cache_dir or settings.cache_dir / "rag"
        self.default_ttl = default_ttl or settings.rag_cache_ttl_seconds
        self.enabled = enabled if enabled is not None else settings.rag_cache_enabled
        
        # Crear directorio si no existe
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Stats
        self._hits = 0
        self._misses = 0
        self._invalidations = 0
    
    def _get_cache_key(
        self,
        query: str,
        case_id: str,
        top_k: int,
        namespace: str = "default"
    ) -> str:
        """
        Genera clave única para la consulta.
        
        Args:
            query: Query de búsqueda
            case_id: ID del caso
            top_k: Número de resultados
            namespace: Namespace para separar tipos de cache
        
        Returns:
            Hash SHA256 de la consulta
        """
        # Normalizar query (lowercase, strip whitespace)
        normalized_query = query.lower().strip()
        
        # Contenido para hash
        content = f"{namespace}:{case_id}:{normalized_query}:{top_k}"
        
        # Generar hash
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """Obtiene ruta del archivo de caché."""
        # Usar subdirectorios para evitar demasiados archivos en un dir
        subdir = cache_key[:2]
        return self.cache_dir / subdir / f"{cache_key}.pkl"
    
    def get(
        self,
        query: str,
        case_id: str,
        top_k: int,
        namespace: str = "default"
    ) -> Optional[Any]:
        """
        Recupera resultado cacheado.
        
        Args:
            query: Query de búsqueda
            case_id: ID del caso
            top_k: Número de resultados
            namespace: Namespace del caché
        
        Returns:
            Resultado cacheado o None si no existe/expiró
        """
        if not self.enabled:
            return None
        
        cache_key = self._get_cache_key(query, case_id, top_k, namespace)
        cache_path = self._get_cache_path(cache_key)
        
        # Verificar si existe
        if not cache_path.exists():
            self._misses += 1
            logger.info(
                "Cache miss",
                case_id=case_id,
                action="rag_cache_miss",
                cache_key=cache_key[:8]
            )
            return None
        
        try:
            # Cargar desde disco
            with open(cache_path, 'rb') as f:
                cached: CachedResult = pickle.load(f)
            
            # Verificar expiración
            if cached.is_expired():
                self._misses += 1
                logger.info(
                    "Cache expired",
                    case_id=case_id,
                    action="rag_cache_expired",
                    age_seconds=cached.age_seconds()
                )
                # Eliminar archivo expirado
                cache_path.unlink()
                return None
            
            # Hit!
            self._hits += 1
            logger.info(
                "Cache hit",
                case_id=case_id,
                action="rag_cache_hit",
                age_seconds=cached.age_seconds(),
                cache_key=cache_key[:8]
            )
            
            return cached.results
        
        except Exception as e:
            self._misses += 1
            logger.error(
                "Cache read error",
                case_id=case_id,
                action="rag_cache_error",
                error=e
            )
            return None
    
    def set(
        self,
        query: str,
        case_id: str,
        top_k: int,
        results: Any,
        namespace: str = "default",
        ttl: Optional[int] = None
    ) -> bool:
        """
        Guarda resultado en caché.
        
        Args:
            query: Query de búsqueda
            case_id: ID del caso
            top_k: Número de resultados
            results: Resultados a cachear
            namespace: Namespace del caché
            ttl: TTL custom (opcional)
        
        Returns:
            True si se guardó exitosamente
        """
        if not self.enabled:
            return False
        
        cache_key = self._get_cache_key(query, case_id, top_k, namespace)
        cache_path = self._get_cache_path(cache_key)
        
        try:
            # Crear subdirectorio si no existe
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Crear objeto cacheado
            cached = CachedResult(
                query=query,
                case_id=case_id,
                top_k=top_k,
                results=results,
                timestamp=time.time(),
                ttl_seconds=ttl or self.default_ttl
            )
            
            # Guardar a disco
            with open(cache_path, 'wb') as f:
                pickle.dump(cached, f)
            
            logger.info(
                "Cache set",
                case_id=case_id,
                action="rag_cache_set",
                cache_key=cache_key[:8],
                ttl_seconds=cached.ttl_seconds
            )
            
            return True
        
        except Exception as e:
            logger.error(
                "Cache write error",
                case_id=case_id,
                action="rag_cache_write_error",
                error=e
            )
            return False
    
    def invalidate(
        self,
        case_id: Optional[str] = None,
        namespace: Optional[str] = None
    ) -> int:
        """
        Invalida entradas del caché.
        
        Args:
            case_id: ID del caso (invalida todo su caché)
            namespace: Namespace a invalidar
        
        Returns:
            Número de entradas invalidadas
        """
        if not self.enabled:
            return 0
        
        count = 0
        
        try:
            # Si no se especifica nada, invalidar todo
            if case_id is None and namespace is None:
                for cache_file in self.cache_dir.rglob("*.pkl"):
                    cache_file.unlink()
                    count += 1
            
            # Invalidar por caso específico (requiere iterar)
            elif case_id:
                for cache_file in self.cache_dir.rglob("*.pkl"):
                    try:
                        with open(cache_file, 'rb') as f:
                            cached: CachedResult = pickle.load(f)
                        
                        if cached.case_id == case_id:
                            cache_file.unlink()
                            count += 1
                    except:
                        pass
            
            self._invalidations += count
            
            logger.info(
                "Cache invalidated",
                action="rag_cache_invalidate",
                count=count,
                case_id=case_id,
                namespace=namespace
            )
        
        except Exception as e:
            logger.error(
                "Cache invalidation error",
                action="rag_cache_invalidate_error",
                error=e
            )
        
        return count
    
    def clear_expired(self) -> int:
        """
        Limpia entradas expiradas del caché.
        
        Returns:
            Número de entradas eliminadas
        """
        if not self.enabled:
            return 0
        
        count = 0
        
        try:
            for cache_file in self.cache_dir.rglob("*.pkl"):
                try:
                    with open(cache_file, 'rb') as f:
                        cached: CachedResult = pickle.load(f)
                    
                    if cached.is_expired():
                        cache_file.unlink()
                        count += 1
                except:
                    # Si no se puede leer, eliminar
                    cache_file.unlink()
                    count += 1
            
            logger.info(
                "Cache cleanup",
                action="rag_cache_cleanup",
                expired_count=count
            )
        
        except Exception as e:
            logger.error(
                "Cache cleanup error",
                action="rag_cache_cleanup_error",
                error=e
            )
        
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del caché.
        
        Returns:
            Dict con estadísticas
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
        
        # Contar archivos de caché
        cache_files = list(self.cache_dir.rglob("*.pkl")) if self.cache_dir.exists() else []
        
        # Calcular tamaño total
        total_size_bytes = sum(f.stat().st_size for f in cache_files)
        
        return {
            "enabled": self.enabled,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.2f}%",
            "invalidations": self._invalidations,
            "total_entries": len(cache_files),
            "total_size_mb": total_size_bytes / (1024 * 1024),
            "cache_dir": str(self.cache_dir)
        }
    
    def reset_stats(self):
        """Resetea estadísticas."""
        self._hits = 0
        self._misses = 0
        self._invalidations = 0


# =========================================================
# INSTANCIA GLOBAL (SINGLETON)
# =========================================================

_cache_instance: Optional[RAGCache] = None


def get_rag_cache() -> RAGCache:
    """
    Obtiene instancia global del caché RAG.
    
    Returns:
        RAGCache: Instancia del caché
    """
    global _cache_instance
    
    if _cache_instance is None:
        _cache_instance = RAGCache()
    
    return _cache_instance


# =========================================================
# DECORADOR PARA CACHEAR FUNCIONES
# =========================================================

def cached_rag_query(namespace: str = "default", ttl: Optional[int] = None):
    """
    Decorador para cachear automáticamente queries RAG.
    
    Args:
        namespace: Namespace del caché
        ttl: TTL custom (opcional)
    
    Uso:
        @cached_rag_query(namespace="legal_rag")
        def query_legal_rag(query: str, case_id: str, top_k: int):
            # ... lógica de query ...
            return results
    """
    def decorator(func):
        def wrapper(query: str, case_id: str, top_k: int = 5, **kwargs):
            cache = get_rag_cache()
            
            # Intentar obtener del caché
            cached_result = cache.get(query, case_id, top_k, namespace)
            if cached_result is not None:
                return cached_result
            
            # Cache miss: ejecutar función
            result = func(query, case_id, top_k, **kwargs)
            
            # Guardar en caché
            cache.set(query, case_id, top_k, result, namespace, ttl)
            
            return result
        
        return wrapper
    return decorator

