"""
Módulo de handoff entre agentes.

Convierte el resultado del Agente 1 (Auditor) en el formato esperado
por el Agente 2 (Prosecutor).
"""
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator

from app.agents.agent_1_auditor.schema import AuditorResult

logger = logging.getLogger(__name__)


# =========================================================
# MODELO PYDANTIC PARA VALIDACIÓN
# =========================================================

class HandoffPayload(BaseModel):
    """Payload validado para el handoff del Auditor al Prosecutor."""
    
    case_id: str = Field(..., min_length=1, description="ID del caso")
    question: str = Field(..., min_length=1, description="Pregunta original del usuario")
    summary: str = Field(..., description="Resumen del análisis del Auditor")
    risks: List[str] = Field(default_factory=list, description="Lista de riesgos detectados")
    next_actions: List[str] = Field(default_factory=list, description="Acciones siguientes recomendadas")
    auditor_fallback: bool = Field(default=False, description="True si el Auditor usó fallback (sin contexto)")
    
    # Campos opcionales de ingesta
    source_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Metadatos de documentos ingeridos")
    full_text: Optional[str] = Field(default=None, description="Texto completo ingerido")
    
    @field_validator('case_id', 'question', 'summary')
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        """Valida que los strings obligatorios no estén vacíos."""
        if not v or not v.strip():
            raise ValueError("Este campo no puede estar vacío")
        return v.strip()


# =========================================================
# FUNCIÓN DE CONSTRUCCIÓN DEL PAYLOAD
# =========================================================

def build_agent2_payload(
    auditor_result: AuditorResult,
    case_id: str,
    question: str,
    auditor_fallback: bool = False,
    ingesta_result: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Construye el payload para el Agente 2 a partir del resultado del Auditor.

    Args:
        auditor_result: Resultado del Agente 1 (Auditor)
        case_id: ID del caso
        question: Pregunta original del usuario
        auditor_fallback: True si el Auditor usó fallback (sin contexto válido)
        ingesta_result: Resultado opcional de la ingesta de documentos

    Returns:
        Payload estructurado para el Agente 2 (dict, puede ser validado con HandoffPayload)
    """
    logger.info(
        "Construyendo payload del handoff",
        extra={
            "agent_name": "handoff",
            "case_id": case_id,
            "stage": "build_payload",
            "auditor_fallback": auditor_fallback,
        }
    )
    
    payload = {
        "case_id": case_id,
        "question": question,
        "summary": auditor_result.summary,
        "risks": auditor_result.risks,
        "next_actions": auditor_result.next_actions,
        "auditor_fallback": auditor_fallback,
    }

    # Añadir metadatos de ingesta si se proporcionan
    if ingesta_result:
        payload["source_metadata"] = ingesta_result.get("metadata", {})
        
        # Añadir texto completo si existe
        if "ingested_text" in ingesta_result:
            payload["full_text"] = ingesta_result["ingested_text"]
        elif "text" in ingesta_result:
            payload["full_text"] = ingesta_result["text"]

    return payload
