"""
Sistema de telemetría y observabilidad para Phoenix Legal.

Incluye:
- Métricas Prometheus
- Tracing (preparado para OpenTelemetry)
- Monitoreo de costos LLM
- Performance tracking
"""
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Optional

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger()


# =========================================================
# REGISTRO DE MÉTRICAS
# =========================================================

# Usar registro global o custom según configuración
if settings.metrics_enabled:
    registry = CollectorRegistry(auto_describe=True)
else:
    registry = None


# =========================================================
# MÉTRICAS DE ANÁLISIS
# =========================================================

analysis_total = Counter(
    "phoenix_analysis_total",
    "Total de análisis ejecutados",
    ["case_type", "status"],
    registry=registry,
)

analysis_duration = Histogram(
    "phoenix_analysis_duration_seconds",
    "Duración del análisis por etapa",
    ["stage"],
    registry=registry,
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120, 300],
)

analysis_findings = Histogram(
    "phoenix_analysis_findings",
    "Número de findings por análisis",
    ["severity"],
    registry=registry,
    buckets=[0, 1, 2, 3, 5, 10, 20, 50],
)


# =========================================================
# MÉTRICAS DE LLM
# =========================================================

llm_requests_total = Counter(
    "phoenix_llm_requests_total",
    "Total de requests a LLM",
    ["model", "agent", "status"],
    registry=registry,
)

llm_tokens_total = Counter(
    "phoenix_llm_tokens_total",
    "Total de tokens consumidos",
    ["model", "token_type"],  # token_type: prompt, completion
    registry=registry,
)

llm_cost_usd = Counter(
    "phoenix_llm_cost_usd_total", "Costo acumulado en USD", ["model"], registry=registry
)

llm_duration = Histogram(
    "phoenix_llm_duration_seconds",
    "Duración de llamadas LLM",
    ["model", "agent"],
    registry=registry,
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)

llm_fallback_total = Counter(
    "phoenix_llm_fallback_total",
    "Total de fallbacks a modo degradado",
    ["agent", "reason"],
    registry=registry,
)


# =========================================================
# MÉTRICAS DE RAG
# =========================================================

rag_queries_total = Counter(
    "phoenix_rag_queries_total", "Total de queries RAG", ["namespace", "status"], registry=registry
)

rag_cache_operations = Counter(
    "phoenix_rag_cache_operations_total",
    "Operaciones de caché RAG",
    ["operation", "status"],  # operation: hit, miss, set, invalidate
    registry=registry,
)

rag_query_duration = Histogram(
    "phoenix_rag_query_duration_seconds",
    "Duración de queries RAG",
    ["namespace"],
    registry=registry,
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5],
)

rag_similarity_score = Histogram(
    "phoenix_rag_similarity_score",
    "Scores de similitud de resultados RAG",
    ["namespace"],
    registry=registry,
    buckets=[0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0],
)


# =========================================================
# MÉTRICAS DE API
# =========================================================

api_requests_total = Counter(
    "phoenix_api_requests_total",
    "Total de requests HTTP",
    ["method", "endpoint", "status_code"],
    registry=registry,
)

api_request_duration = Histogram(
    "phoenix_api_request_duration_seconds",
    "Duración de requests HTTP",
    ["method", "endpoint"],
    registry=registry,
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
)


# =========================================================
# MÉTRICAS DE BASE DE DATOS
# =========================================================

db_connections_active = Gauge(
    "phoenix_db_connections_active", "Conexiones activas de base de datos", registry=registry
)

db_query_duration = Histogram(
    "phoenix_db_query_duration_seconds",
    "Duración de queries de BD",
    ["operation"],
    registry=registry,
    buckets=[0.001, 0.01, 0.05, 0.1, 0.5, 1, 5],
)


# =========================================================
# MÉTRICAS DEL SISTEMA
# =========================================================

app_info = Info("phoenix_app", "Información de la aplicación", registry=registry)

# Inicializar info
if settings.metrics_enabled:
    app_info.info(
        {
            "version": settings.app_version,
            "environment": settings.environment,
            "llm_enabled": str(settings.llm_available),
        }
    )


# =========================================================
# CONTEXT MANAGERS PARA TRACKING
# =========================================================


@contextmanager
def track_analysis(stage: str):
    """
    Context manager para trackear duración de análisis.

    Uso:
        with track_analysis("auditor"):
            result = run_auditor(case_id)
    """
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        if settings.metrics_enabled:
            analysis_duration.labels(stage=stage).observe(duration)
        logger.info(
            f"Analysis stage completed: {stage}",
            action="analysis_stage_complete",
            stage=stage,
            duration_seconds=duration,
        )


@contextmanager
def track_llm_call(model: str, agent: str):
    """
    Context manager para trackear llamadas LLM.

    Uso:
        with track_llm_call("gpt-4", "auditor"):
            response = llm.invoke(prompt)
    """
    start_time = time.time()
    status = "success"

    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.time() - start_time

        if settings.metrics_enabled:
            llm_requests_total.labels(model=model, agent=agent, status=status).inc()

            llm_duration.labels(model=model, agent=agent).observe(duration)


@contextmanager
def track_rag_query(namespace: str = "default"):
    """
    Context manager para trackear queries RAG.

    Uso:
        with track_rag_query("legal"):
            results = vectorstore.similarity_search(query)
    """
    start_time = time.time()
    status = "success"

    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.time() - start_time

        if settings.metrics_enabled:
            rag_queries_total.labels(namespace=namespace, status=status).inc()

            rag_query_duration.labels(namespace=namespace).observe(duration)


# =========================================================
# DECORADORES
# =========================================================


def track_function_duration(metric_name: str, labels: Optional[dict[str, str]] = None):
    """
    Decorador para trackear duración de funciones.

    Uso:
        @track_function_duration("my_function", labels={"type": "processing"})
        def my_function():
            # ... código ...
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                logger.info(
                    f"Function {func.__name__} completed",
                    action="function_duration",
                    function=func.__name__,
                    duration_seconds=duration,
                    **(labels or {}),
                )

        return wrapper

    return decorator


# =========================================================
# TRACKING DE COSTOS LLM
# =========================================================

# Precios por 1K tokens (actualizar según OpenAI)
LLM_PRICING = {
    "gpt-4": {"prompt": 0.03, "completion": 0.06},
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "gpt-3.5-turbo": {"prompt": 0.0015, "completion": 0.002},
    "text-embedding-3-large": {"prompt": 0.00013, "completion": 0},
    "text-embedding-3-small": {"prompt": 0.00002, "completion": 0},
}


def track_llm_usage(model: str, prompt_tokens: int, completion_tokens: int):
    """
    Trackea uso y costo de LLM.

    Args:
        model: Modelo usado
        prompt_tokens: Tokens del prompt
        completion_tokens: Tokens de la respuesta
    """
    if not settings.metrics_enabled:
        return

    # Trackear tokens
    llm_tokens_total.labels(model=model, token_type="prompt").inc(prompt_tokens)

    llm_tokens_total.labels(model=model, token_type="completion").inc(completion_tokens)

    # Calcular costo
    pricing = LLM_PRICING.get(model, {"prompt": 0, "completion": 0})
    cost = (prompt_tokens / 1000) * pricing["prompt"] + (completion_tokens / 1000) * pricing[
        "completion"
    ]

    llm_cost_usd.labels(model=model).inc(cost)

    logger.info(
        "LLM usage tracked",
        action="llm_usage",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost,
    )


def track_llm_fallback(agent: str, reason: str):
    """
    Trackea fallback a modo degradado.

    Args:
        agent: Nombre del agente
        reason: Razón del fallback
    """
    if not settings.metrics_enabled:
        return

    llm_fallback_total.labels(agent=agent, reason=reason).inc()

    logger.warning("LLM fallback triggered", action="llm_fallback", agent=agent, reason=reason)


# =========================================================
# TRACKING DE CACHÉ RAG
# =========================================================


def track_rag_cache_operation(operation: str, status: str):
    """
    Trackea operaciones de caché RAG.

    Args:
        operation: Tipo de operación (hit, miss, set, invalidate)
        status: Estado (success, error)
    """
    if not settings.metrics_enabled:
        return

    rag_cache_operations.labels(operation=operation, status=status).inc()


# =========================================================
# ENDPOINT DE MÉTRICAS
# =========================================================


def get_metrics_response():
    """
    Genera respuesta con métricas en formato Prometheus.

    Returns:
        Tuple[bytes, str]: (contenido, content_type)
    """
    if not settings.metrics_enabled or not registry:
        return b"Metrics disabled\n", "text/plain"

    return generate_latest(registry), CONTENT_TYPE_LATEST


# =========================================================
# HEALTH CHECK EXTENDIDO
# =========================================================


def get_system_stats() -> dict[str, Any]:
    """
    Obtiene estadísticas del sistema.

    Returns:
        Dict con estadísticas
    """
    from app.rag.cache import get_rag_cache

    stats = {
        "app_version": settings.app_version,
        "environment": settings.environment,
        "llm_available": settings.llm_available,
        "metrics_enabled": settings.metrics_enabled,
    }

    # Stats de caché
    if settings.rag_cache_enabled:
        cache = get_rag_cache()
        stats["cache"] = cache.get_stats()

    return stats
