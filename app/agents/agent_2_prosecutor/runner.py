
"""
Runner del Agente 2: Prosecutor.

Este archivo define el punto de entrada estándar del agente.
Debe ser simple, predecible y sin lógica de negocio.
"""

from __future__ import annotations
import logging
from typing import Dict, Any, Optional

from .logic import ejecutar_analisis_prosecutor
from .schema import ProsecutorResult

logger = logging.getLogger(__name__)


def run_prosecutor(*, case_id: str) -> ProsecutorResult:
    """
    Ejecuta el Agente Prosecutor para un caso concreto.

    Args:
        case_id (str): Identificador único del caso

    Returns:
        ProsecutorResult: Resultado estructurado del análisis fiscal
    """
    if not case_id:
        raise ValueError("case_id es obligatorio para ejecutar el Agente Prosecutor")

    logger.info(
        "Agente Prosecutor iniciado",
        extra={
            "agent_name": "prosecutor",
            "case_id": case_id,
            "stage": "analysis",
        }
    )

    result = ejecutar_analisis_prosecutor(case_id=case_id)

    logger.info(
        "Agente Prosecutor finalizado",
        extra={
            "agent_name": "prosecutor",
            "case_id": case_id,
            "stage": "analysis",
            "accusations_count": len(result.accusations),
            "overall_risk_level": result.overall_risk_level,
        }
    )

    return result


def run_prosecutor_from_auditor(handoff_payload: Dict[str, Any]) -> ProsecutorResult:
    """
    Ejecuta el Agente Prosecutor a partir del payload del handoff del Auditor.

    Args:
        handoff_payload: Payload del handoff que contiene case_id, summary, risks, etc.

    Returns:
        ProsecutorResult: Resultado estructurado del análisis fiscal
    """
    if not handoff_payload:
        raise ValueError("handoff_payload es obligatorio")
    
    case_id = handoff_payload.get("case_id")
    if not case_id:
        raise ValueError("handoff_payload debe contener 'case_id'")
    
    auditor_fallback = handoff_payload.get("auditor_fallback", False)
    auditor_summary = handoff_payload.get("summary")
    auditor_risks = handoff_payload.get("risks", [])
    
    logger.info(
        "Agente Prosecutor iniciado desde handoff",
        extra={
            "agent_name": "prosecutor",
            "case_id": case_id,
            "stage": "handoff",
            "auditor_fallback": auditor_fallback,
            "has_auditor_context": bool(auditor_summary),
        }
    )
    
    # El Prosecutor usa su propia lógica interna, pero recibe el contexto del Auditor
    # Actualmente, el Prosecutor hace su propio análisis con preguntas hostiles,
    # pero pasamos el contexto del Auditor como parámetros opcionales para uso futuro
    result = ejecutar_analisis_prosecutor(
        case_id=case_id,
        auditor_summary=auditor_summary,
        auditor_risks=auditor_risks,
        auditor_fallback=auditor_fallback,
    )
    
    logger.info(
        "Agente Prosecutor finalizado desde handoff",
        extra={
            "agent_name": "prosecutor",
            "case_id": case_id,
            "stage": "handoff",
            "accusations_count": len(result.accusations),
            "overall_risk_level": result.overall_risk_level,
        }
    )
    
    return result

