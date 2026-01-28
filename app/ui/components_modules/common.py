"""
Helpers comunes compartidos por todos los componentes.

Funciones puras sin dependencias de Streamlit.
Fácilmente testeables.
"""
from typing import Any, Optional


def get_field_value(field_data: Any) -> Optional[float]:
    """
    Extrae el valor numérico de un campo.

    El campo puede ser:
    - Dict con key 'value': {"value": 100, "confidence": "HIGH"}
    - Número directo: 100
    - None: None

    Args:
        field_data: Campo a extraer (dict, número o None)

    Returns:
        Valor numérico o None

    Examples:
        >>> get_field_value({"value": 100})
        100
        >>> get_field_value(100)
        100
        >>> get_field_value(None)
        None
    """
    if field_data is None:
        return None
    if isinstance(field_data, dict) and "value" in field_data:
        return field_data["value"]
    if isinstance(field_data, (int, float)):
        return field_data
    return None


def get_confidence_emoji(field_data: Any) -> str:
    """
    Obtiene emoji de confianza de un campo.

    Args:
        field_data: Campo con metadata de confianza

    Returns:
        Emoji: ✅ (HIGH), 🟡 (MEDIUM), ❓ (LOW/None)

    Examples:
        >>> get_confidence_emoji({"confidence": "HIGH"})
        '✅'
        >>> get_confidence_emoji({"confidence": "MEDIUM"})
        '🟡'
        >>> get_confidence_emoji(None)
        '❓'
    """
    if field_data is None or not isinstance(field_data, dict):
        return "❓"
    conf = field_data.get("confidence", "LOW")
    return {"HIGH": "✅", "MEDIUM": "🟡", "LOW": "❓"}.get(conf, "❓")
