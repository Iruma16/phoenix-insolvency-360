"""
Políticas de retención para Decision Records (HARDENING OPCIONAL).

⚠️ IMPORTANTE - CONFIGURACIÓN DE PRODUCCIÓN:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Backend actual: "in-memory"
Status: ✅ VÁLIDO para desarrollo y testing
        ⚠️  NO VÁLIDO para producción final

Razón:
- Los Decision Records se pierden al reiniciar el proceso.
- NO cumple requisitos de auditoría persistente.
- NO soporta alta disponibilidad ni disaster recovery.

Producción requiere:
- backend_type = "persistent" (PostgreSQL, MongoDB, S3, etc.)
- Implementación de PersistentRetentionBackend
- Infraestructura de respaldo y replicación

Este código deja el camino preparado sin implementar la persistencia aún.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Interfaz pluggable sin romper backend actual.
"""
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

# ============================
# CONFIGURACIÓN EXPLÍCITA
# ============================

# Backend de retención activo
# Valores: "in_memory" | "persistent"
# Default: "in_memory" (NO apto para producción final)
RETENTION_BACKEND = os.getenv("RETENTION_BACKEND", "in_memory")


@dataclass
class RetentionConfig:
    """Configuración de retención."""

    ttl_seconds: Optional[int] = None  # None = sin expiración
    backend_type: str = RETENTION_BACKEND  # Usa configuración global
    auto_cleanup: bool = False  # Limpieza automática de expirados


class RetentionBackend(ABC):
    """Interfaz abstracta para backends de retención."""

    @abstractmethod
    def store(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Almacena valor con TTL opcional."""
        pass

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Recupera valor si no ha expirado."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Borra valor."""
        pass

    @abstractmethod
    def delete_by_case_id(self, case_id: str) -> int:
        """Borra todos los records de un case_id. Retorna cantidad borrada."""
        pass

    @abstractmethod
    def cleanup_expired(self) -> int:
        """Limpia registros expirados. Retorna cantidad eliminada."""
        pass


class InMemoryRetentionBackend(RetentionBackend):
    """Backend en memoria con TTL (DEFAULT)."""

    def __init__(self):
        self._storage: dict[str, dict[str, Any]] = {}

    def store(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Almacena con TTL opcional."""
        expiration = None
        if ttl:
            expiration = datetime.utcnow() + timedelta(seconds=ttl)

        self._storage[key] = {
            "value": value,
            "expiration": expiration,
            "stored_at": datetime.utcnow(),
        }

    def get(self, key: str) -> Optional[Any]:
        """Recupera si no expiró."""
        entry = self._storage.get(key)
        if not entry:
            return None

        # Verificar expiración
        if entry["expiration"] and datetime.utcnow() > entry["expiration"]:
            del self._storage[key]
            return None

        return entry["value"]

    def delete(self, key: str) -> bool:
        """Borra valor."""
        if key in self._storage:
            del self._storage[key]
            return True
        return False

    def delete_by_case_id(self, case_id: str) -> int:
        """Borra todos los records de un case_id."""
        to_delete = []
        for key, entry in self._storage.items():
            value = entry.get("value")
            if hasattr(value, "case_id") and value.case_id == case_id:
                to_delete.append(key)

        for key in to_delete:
            del self._storage[key]

        return len(to_delete)

    def cleanup_expired(self) -> int:
        """Limpia expirados."""
        expired = []
        now = datetime.utcnow()

        for key, entry in self._storage.items():
            if entry["expiration"] and now > entry["expiration"]:
                expired.append(key)

        for key in expired:
            del self._storage[key]

        return len(expired)


class PersistentRetentionBackend(RetentionBackend):
    """
    Backend persistente (PLACEHOLDER para producción).

    NO implementado - usar BD real, Redis, S3, etc.
    """

    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string
        raise NotImplementedError(
            "Backend persistente requiere implementación específica "
            "(PostgreSQL, Redis, S3, etc.)"
        )

    def store(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        raise NotImplementedError()

    def get(self, key: str) -> Optional[Any]:
        raise NotImplementedError()

    def delete(self, key: str) -> bool:
        raise NotImplementedError()

    def delete_by_case_id(self, case_id: str) -> int:
        raise NotImplementedError()

    def cleanup_expired(self) -> int:
        raise NotImplementedError()


# Factory
def get_retention_backend(config: Optional[RetentionConfig] = None) -> RetentionBackend:
    """
    Factory para obtener backend de retención.

    Default: in-memory sin TTL (compatible con implementación actual).

    ⚠️ PRODUCCIÓN: Usar RETENTION_BACKEND=persistent con implementación real.
    """
    if config is None:
        config = RetentionConfig()

    backend_type = config.backend_type.lower()

    if backend_type == "in-memory" or backend_type == "in_memory":
        backend = InMemoryRetentionBackend()
        print(
            f"[CERT] RETENTION_BACKEND_SELECTED backend=in-memory ttl={config.ttl_seconds or 'none'}"
        )

        # ⚠️ WARNING para producción
        env = os.getenv("ENVIRONMENT", "dev")
        if env.lower() in ["production", "prod"]:
            print(
                "[WARNING] Backend in-memory NO apto para producción. Configurar RETENTION_BACKEND=persistent"
            )

        return backend

    elif backend_type == "persistent":
        # En producción, implementar con DB real
        print(
            f"[CERT] RETENTION_BACKEND_SELECTED backend=persistent ttl={config.ttl_seconds or 'none'}"
        )
        raise NotImplementedError(
            "Backend persistente requiere implementación específica:\n"
            "  - PostgreSQL: usar SQLAlchemy con tabla decision_records\n"
            "  - MongoDB: usar pymongo con colección decision_records\n"
            "  - S3: usar boto3 con bucket de auditoría\n"
            "  - Redis: usar redis-py con persistencia RDB/AOF"
        )

    else:
        raise ValueError(f"Backend desconocido: {backend_type}")
