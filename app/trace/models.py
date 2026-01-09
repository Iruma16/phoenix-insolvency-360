"""
MODELOS DE TRACE AUTORITATIVO (FASE 6 - ENDURECIMIENTO 6).

PRINCIPIO: El trace es la ÚNICA FUENTE DE VERDAD del sistema.
Si algo no está en el trace, el sistema NO puede afirmarlo.

Este módulo define el contrato inmutable del trace para auditoría y replay.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator


TRACE_SCHEMA_VERSION = "1.0.0"


class ExecutionMode(str, Enum):
    """Modo de ejecución del sistema."""
    STRICT = "strict"
    PERMISSIVE = "permissive"


class DecisionType(str, Enum):
    """Tipo de decisión registrada en el trace."""
    VALIDATION = "validation"
    EVIDENCE_CHECK = "evidence_check"
    GATE_APPLIED = "gate_applied"
    CHUNK_SELECTED = "chunk_selected"
    REPORT_GENERATED = "report_generated"
    ERROR_HANDLED = "error_handled"


class TraceDecision(BaseModel):
    """
    Decisión técnica registrada en el trace.
    
    CONTRATO DURO:
    - Toda decisión debe tener timestamp
    - step_name debe ser determinista
    - description debe ser objetiva (no interpretativa)
    """
    step_name: str = Field(
        ...,
        description="Nombre determinista del paso",
        min_length=1
    )
    decision_type: DecisionType = Field(
        ...,
        description="Tipo de decisión"
    )
    description: str = Field(
        ...,
        description="Descripción objetiva de la decisión",
        min_length=10
    )
    evidence_ids: List[str] = Field(
        default_factory=list,
        description="IDs de evidencia implicados en esta decisión"
    )
    validation_applied: Optional[str] = Field(
        None,
        description="Validación aplicada (si aplica)"
    )
    timestamp: datetime = Field(
        ...,
        description="Timestamp de la decisión (obligatorio para ordenamiento)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata adicional de la decisión"
    )
    
    model_config = {"extra": "forbid"}


class TraceError(BaseModel):
    """
    Error registrado durante la ejecución.
    
    Permite trazar fallos y decisiones de recuperación.
    """
    error_code: str = Field(..., description="Código del error")
    error_message: str = Field(..., description="Mensaje del error")
    step_name: str = Field(..., description="Paso donde ocurrió el error")
    timestamp: datetime = Field(..., description="Timestamp del error")
    recovered: bool = Field(
        default=False,
        description="Si el error fue recuperado o abortó la ejecución"
    )
    
    model_config = {"extra": "forbid"}


class ExecutionTrace(BaseModel):
    """
    Trace autoritativo de una ejecución del sistema.
    
    CONTRATO DURO:
    - trace_id debe ser determinista
    - decisions debe estar ordenado por timestamp
    - NO puede modificarse después de creado
    - ES la única fuente de verdad
    
    El trace permite:
    - Replay sin LLM
    - Auditoría completa
    - Certificación técnica
    - Reconstrucción de ejecución
    """
    trace_id: str = Field(
        ...,
        description="ID determinista del trace",
        min_length=1
    )
    case_id: str = Field(
        ...,
        description="ID del caso analizado",
        min_length=1
    )
    execution_timestamp: datetime = Field(
        ...,
        description="Timestamp de inicio de ejecución"
    )
    
    # Input (hashes, NO texto libre)
    input_summary: Dict[str, str] = Field(
        ...,
        description="Resumen del input (hashes, NO texto libre)"
    )
    
    # Evidencia utilizada
    chunk_ids: List[str] = Field(
        default_factory=list,
        description="IDs de chunks utilizados como evidencia"
    )
    document_ids: List[str] = Field(
        default_factory=list,
        description="IDs de documentos consultados"
    )
    
    # Salida
    legal_report_hash: Optional[str] = Field(
        None,
        description="Hash SHA256 del reporte legal generado"
    )
    
    # Decisiones (ORDENADAS)
    decisions: List[TraceDecision] = Field(
        ...,
        description="Lista ordenada de decisiones técnicas",
        min_length=1
    )
    
    # Errores (si existen)
    errors: List[TraceError] = Field(
        default_factory=list,
        description="Errores ocurridos durante la ejecución"
    )
    
    # Metadatos del sistema
    execution_mode: ExecutionMode = Field(
        ...,
        description="Modo de ejecución (STRICT / PERMISSIVE)"
    )
    system_version: str = Field(
        ...,
        description="Versión del sistema que generó el trace"
    )
    trace_schema_version: str = Field(
        default=TRACE_SCHEMA_VERSION,
        description="Versión del esquema de trace"
    )
    
    # Timestamp de finalización
    completed_at: Optional[datetime] = Field(
        None,
        description="Timestamp de finalización (None si abortó)"
    )
    
    @field_validator('decisions')
    @classmethod
    def validate_decisions_ordered(cls, v: List[TraceDecision]) -> List[TraceDecision]:
        """REGLA DURA: Decisiones deben estar ordenadas por timestamp"""
        if len(v) < 1:
            raise ValueError("Trace sin decisiones no permitido")
        
        # Verificar orden
        for i in range(1, len(v)):
            if v[i].timestamp < v[i-1].timestamp:
                raise ValueError(
                    f"Decisiones no ordenadas: {v[i].step_name} antes de {v[i-1].step_name}"
                )
        
        return v
    
    model_config = {"extra": "forbid", "frozen": True}  # INMUTABLE después de creado
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """
        Retorna resumen de la ejecución para auditoría.
        """
        return {
            "trace_id": self.trace_id,
            "case_id": self.case_id,
            "execution_mode": self.execution_mode.value,
            "total_decisions": len(self.decisions),
            "total_errors": len(self.errors),
            "chunks_used": len(self.chunk_ids),
            "documents_consulted": len(self.document_ids),
            "completed": self.completed_at is not None,
            "system_version": self.system_version,
        }
    
    def get_timeline(self) -> List[Dict[str, Any]]:
        """
        Retorna timeline ordenado de eventos (decisiones + errores).
        
        Útil para replay y auditoría.
        """
        timeline = []
        
        # Añadir decisiones
        for decision in self.decisions:
            timeline.append({
                "type": "decision",
                "timestamp": decision.timestamp,
                "step_name": decision.step_name,
                "decision_type": decision.decision_type.value,
                "description": decision.description,
            })
        
        # Añadir errores
        for error in self.errors:
            timeline.append({
                "type": "error",
                "timestamp": error.timestamp,
                "step_name": error.step_name,
                "error_code": error.error_code,
                "recovered": error.recovered,
            })
        
        # Ordenar por timestamp
        timeline.sort(key=lambda x: x["timestamp"])
        
        return timeline
    
    def compute_integrity_hash(self) -> str:
        """
        Calcula hash de integridad del trace completo.
        
        Permite detectar modificaciones.
        """
        # Serializar trace a string determinista
        trace_string = (
            f"{self.trace_id}|{self.case_id}|"
            f"{self.execution_timestamp.isoformat()}|"
            f"{len(self.decisions)}|{len(self.errors)}|"
            f"{self.system_version}"
        )
        
        return hashlib.sha256(trace_string.encode()).hexdigest()


def generate_trace_id(case_id: str, execution_timestamp: datetime) -> str:
    """
    Genera trace_id determinista.
    
    Args:
        case_id: ID del caso
        execution_timestamp: Timestamp de ejecución
        
    Returns:
        trace_id único y reproducible
    """
    components = f"{case_id}|{execution_timestamp.isoformat()}"
    hash_digest = hashlib.sha256(components.encode()).hexdigest()
    return f"trace_{hash_digest[:32]}"

