"""
Pricing Table Versionada.

ENDURECIMIENTO #7: Tabla de precios con versión explícita y hash estable.

PRINCIPIO: Todo coste debe ser calculable de forma determinista.
"""
import hashlib
import json

# ============================
# PRICING VERSION
# ============================

PRICING_VERSION = "2026-01-06"  # YYYY-MM-DD


# ============================
# PRICING TABLE
# ============================

PRICING_TABLE: dict[str, dict[str, float]] = {
    # OpenAI models (USD per 1K tokens)
    "gpt-4o": {
        "input_per_1k": 0.0025,
        "output_per_1k": 0.01,
    },
    "gpt-4o-mini": {
        "input_per_1k": 0.00015,
        "output_per_1k": 0.0006,
    },
    "gpt-4-turbo": {
        "input_per_1k": 0.01,
        "output_per_1k": 0.03,
    },
    "gpt-3.5-turbo": {
        "input_per_1k": 0.0005,
        "output_per_1k": 0.0015,
    },
    # Embeddings (USD per 1K tokens)
    "text-embedding-3-small": {
        "input_per_1k": 0.00002,
        "output_per_1k": 0.0,  # Embeddings no tienen output tokens
    },
    "text-embedding-3-large": {
        "input_per_1k": 0.00013,
        "output_per_1k": 0.0,
    },
    "text-embedding-ada-002": {
        "input_per_1k": 0.0001,
        "output_per_1k": 0.0,
    },
}


# ============================
# COST ESTIMATION
# ============================


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int = 0,
) -> float:
    """
    Calcula coste en USD de forma determinista.

    GARANTÍA: Mismo modelo + tokens → mismo coste.

    Args:
        model: Nombre del modelo
        input_tokens: Tokens de entrada
        output_tokens: Tokens de salida (0 para embeddings)

    Returns:
        Coste en USD

    Raises:
        ValueError: Si el modelo no existe en PRICING_TABLE
    """
    if model not in PRICING_TABLE:
        raise ValueError(f"Modelo desconocido: {model}. Añadir a PRICING_TABLE.")

    pricing = PRICING_TABLE[model]

    input_cost = (input_tokens / 1000.0) * pricing["input_per_1k"]
    output_cost = (output_tokens / 1000.0) * pricing["output_per_1k"]

    total_cost = input_cost + output_cost

    return round(total_cost, 6)  # 6 decimales para precisión


def pricing_fingerprint() -> str:
    """
    Calcula hash estable de la tabla de precios.

    GARANTÍA: Misma tabla → mismo hash.

    INVARIANTE: Si cambia un precio → cambia el hash.

    Returns:
        Hash SHA256 de la tabla + versión
    """
    # Serializar de forma ordenada y determinista
    data = {
        "version": PRICING_VERSION,
        "table": PRICING_TABLE,
    }

    serialized = json.dumps(data, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def get_pricing_info() -> dict[str, str]:
    """
    Retorna información de pricing para trazabilidad.

    Returns:
        Dict con version y fingerprint
    """
    return {
        "pricing_version": PRICING_VERSION,
        "pricing_fingerprint": pricing_fingerprint(),
    }
