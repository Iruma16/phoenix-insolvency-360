"""
Preparación de datos para gráficos con caching optimizado.

Todas las funciones usan @st.cache_data para evitar recálculos
innecesarios en reruns de Streamlit.
"""

import json
from collections import Counter
from typing import Any

import streamlit as st


@st.cache_data(ttl=300, show_spinner=False)
def prepare_ratio_chart_data(ratios_json: str) -> dict[str, Any]:
    """
    Prepara datos de ratios para gráfico (CACHEADO).

    Args:
        ratios_json: JSON string de ratios (para hasheable)

    Returns:
        Dict con names, values, colors, interpretations
    """
    ratios_dicts = json.loads(ratios_json)

    names = []
    values = []
    colors = []
    interpretations = []

    for ratio in ratios_dicts:
        if ratio.get("value") is not None:
            names.append(ratio.get("name", "Ratio"))
            values.append(ratio.get("value", 0))

            # Color según status
            status = ratio.get("status", "stable")
            color_map = {
                "critical": "#dc2626",
                "red": "#dc2626",
                "concerning": "#f59e0b",
                "yellow": "#f59e0b",
                "stable": "#10b981",
                "green": "#10b981",
            }
            colors.append(color_map.get(status, "#6b7280"))
            interpretations.append(ratio.get("interpretation", ""))

    return {"names": names, "values": values, "colors": colors, "interpretations": interpretations}


@st.cache_data(ttl=300, show_spinner=False)
def prepare_balance_chart_data(balance_json: str) -> dict[str, Any]:
    """
    Prepara datos de balance para gráficos (CACHEADO).

    Args:
        balance_json: JSON string de balance

    Returns:
        Dict con todos los valores necesarios para gráficos
    """
    balance_dict = json.loads(balance_json)

    def get_value(field_dict):
        if field_dict is None:
            return None
        if isinstance(field_dict, dict):
            return field_dict.get("value")
        return field_dict

    return {
        "ac": get_value(balance_dict.get("activo_corriente")),
        "anc": get_value(balance_dict.get("activo_no_corriente")),
        "at": get_value(balance_dict.get("activo_total")),
        "pc": get_value(balance_dict.get("pasivo_corriente")),
        "pnc": get_value(balance_dict.get("pasivo_no_corriente")),
        "pt": get_value(balance_dict.get("pasivo_total")),
        "pn": get_value(balance_dict.get("patrimonio_neto")),
    }


@st.cache_data(ttl=300, show_spinner=False)
def prepare_patterns_chart_data(alerts_json: str) -> dict[str, Any]:
    """
    Prepara datos de patrones sospechosos para gráficos (CACHEADO).

    Args:
        alerts_json: JSON string de alerts

    Returns:
        Dict con datos agregados para gráficos
    """
    alerts = json.loads(alerts_json)

    # Contar por categoría
    category_counts = Counter(a.get("category", "otros") for a in alerts)

    # Score promedio por categoría
    category_scores = {}
    for cat in category_counts.keys():
        cat_alerts = [a for a in alerts if a.get("category", "otros") == cat]
        category_scores[cat] = sum(a.get("severity_score", 0) for a in cat_alerts) / len(cat_alerts)

    # Contar por severidad
    severity_counts = Counter(a.get("severity", "medium") for a in alerts)

    # Top alerts por score
    sorted_alerts = sorted(alerts, key=lambda x: x.get("severity_score", 0), reverse=True)
    top_alerts = sorted_alerts[:5]

    return {
        "category_counts": dict(category_counts),
        "category_scores": category_scores,
        "severity_counts": dict(severity_counts),
        "top_alerts": top_alerts,
        "total": len(alerts),
    }
