from __future__ import annotations

import inspect
import os
from typing import Any

import streamlit as st

from app.ui.api_client import PhoenixLegalClient

# Bump this cuando cambie la API del cliente (evita bugs por cache viejo)
CLIENT_API_VERSION = 5


@st.cache_resource
def _get_api_client_cached(base_url: str, _v: int = CLIENT_API_VERSION) -> PhoenixLegalClient:
    """
    Cachea el cliente por URL.

    Importante: incluir base_url como parámetro para que Streamlit cachee por URL
    (si no, puede quedarse apuntando al puerto viejo aunque cambies PHOENIX_API_BASE_URL).
    """
    if not base_url:
        raise RuntimeError(
            "Falta PHOENIX_API_BASE_URL. Copia env.example a .env y define PHOENIX_API_BASE_URL "
            "(ej: http://localhost:8000)."
        )
    return PhoenixLegalClient(base_url=base_url)


def get_api_client() -> PhoenixLegalClient:
    """
    Wrapper sin args para evitar errores en call-sites.
    Mantiene cache por base_url (leído de env) vía _get_api_client_cached().
    """
    base_url = (os.getenv("PHOENIX_API_BASE_URL") or "").strip()
    return _get_api_client_cached(base_url=base_url, _v=CLIENT_API_VERSION)


@st.cache_data(ttl=300)
def get_financial_analysis_cached(case_id: str) -> dict[str, Any]:
    """Obtiene análisis financiero con caché (serializable)."""
    client = get_api_client()
    analysis = client.get_financial_analysis(case_id)
    return {
        "balance": analysis.balance.dict() if analysis.balance else None,
        "profit_loss": analysis.profit_loss.dict() if analysis.profit_loss else None,
        "credit_classification": [c.dict() for c in analysis.credit_classification],
        "total_debt": analysis.total_debt,
        "ratios": [r.dict() for r in analysis.ratios],
        "insolvency": analysis.insolvency.dict() if analysis.insolvency else None,
        "timeline": [t.dict() for t in analysis.timeline],
    }


def download_doc_url(
    client: PhoenixLegalClient, case_id: str, document_id: str, *, disposition: str
) -> str:
    """
    Compatibilidad: si Streamlit conserva un cliente cacheado antiguo sin parámetro `disposition`,
    construimos la URL manualmente.
    """
    disp = (disposition or "attachment").strip().lower()
    if disp not in ("attachment", "inline"):
        disp = "attachment"

    try:
        sig = inspect.signature(client.download_document_url)
        if "disposition" in sig.parameters:
            return client.download_document_url(case_id, document_id, disposition=disp)  # type: ignore[arg-type]
    except Exception:
        pass

    base = getattr(client, "base_url", None) or (
        os.getenv("PHOENIX_API_BASE_URL") or "http://localhost:8000"
    )
    return f"{str(base).rstrip('/')}/api/cases/{case_id}/documents/{document_id}/download?disposition={disp}"
