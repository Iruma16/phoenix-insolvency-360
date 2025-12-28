from __future__ import annotations

from app.graphs.state import AuditState


def ingest_documents(state: AuditState) -> AuditState:
    """
    Nodo: Ingesta / preparación de documentos.
    """
    return state


def analyze_timeline(state: AuditState) -> AuditState:
    """
    Nodo: Análisis temporal (Digger).
    """
    return state


def detect_risks(state: AuditState) -> AuditState:
    """
    Nodo: Detección de riesgos (Prosecutor).
    """
    return state


def build_report(state: AuditState) -> AuditState:
    """
    Nodo: Construcción de salida (Shield / Report).
    """
    return state
