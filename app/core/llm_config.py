"""
Configuración global de LLM y feature flags.

Este módulo centraliza la configuración de LLM para:
- Habilitar/deshabilitar LLM globalmente
- Configurar modelos primary/fallback
- Configurar timeouts y retries

REGLA CRÍTICA:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Si LLM_ENABLED=false → El sistema sigue funcionando sin LLM.
Rule Engine + degradación controlada aseguran output válido SIEMPRE.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
from typing import Optional

# ========================================
# FEATURE FLAG GLOBAL
# ========================================

LLM_ENABLED: bool = os.getenv("LLM_ENABLED", "true").lower() in ("true", "1", "yes")

# ========================================
# MODELOS
# ========================================

PRIMARY_MODEL: str = os.getenv("PRIMARY_MODEL", "gpt-4")
FALLBACK_MODEL: str = os.getenv("FALLBACK_MODEL", "gpt-3.5-turbo")

# ========================================
# TIMEOUTS Y RETRIES
# ========================================

DEFAULT_TIMEOUT_SECONDS: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "15"))
DEFAULT_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "2"))

# ========================================
# API KEY
# ========================================

OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")

# Determinar si LLM está realmente disponible
LLM_AVAILABLE: bool = LLM_ENABLED and OPENAI_API_KEY is not None


# ========================================
# HELPERS
# ========================================


def is_llm_enabled() -> bool:
    """
    Verifica si el LLM está habilitado y disponible.

    Returns:
        True si LLM_ENABLED=true Y existe API key
        False en caso contrario
    """
    return LLM_AVAILABLE


def get_llm_config() -> dict:
    """
    Retorna configuración actual de LLM.

    Útil para logging y debugging.
    """
    return {
        "llm_enabled": LLM_ENABLED,
        "llm_available": LLM_AVAILABLE,
        "primary_model": PRIMARY_MODEL if LLM_AVAILABLE else None,
        "fallback_model": FALLBACK_MODEL if LLM_AVAILABLE else None,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "max_retries": DEFAULT_MAX_RETRIES,
        "has_api_key": OPENAI_API_KEY is not None,
    }


# ========================================
# STARTUP LOGGING
# ========================================


def log_llm_config() -> None:
    """Loguea configuración de LLM al inicio."""
    config = get_llm_config()

    if LLM_AVAILABLE:
        print(
            f"[LLM_CONFIG] LLM enabled: primary={config['primary_model']}, "
            f"fallback={config['fallback_model']}, timeout={config['timeout_seconds']}s"
        )
    else:
        reason = "No API key" if not OPENAI_API_KEY else "Feature disabled"
        print(f"[LLM_CONFIG] LLM disabled: reason={reason}")
        print("[LLM_CONFIG] System will operate with Rule Engine only (degraded mode)")
