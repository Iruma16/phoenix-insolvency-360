"""
REDISEÑO PROSECUTOR: Schema probatorio estricto.

PRINCIPIO: NO EXISTE ACUSACIÓN SIN PRUEBA COMPLETA.
"""
from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, validator


# ============================
# TIPOS CONTROLADOS
# ============================

Severidad = Literal["BAJA", "MEDIA", "ALTA", "CRITICA"]


# ============================
# OBLIGACIÓN LEGAL
# ============================

class ObligacionLegal(BaseModel):
    """Obligación legal concreta (ley + artículo + deber)."""
    ley: str = Field(..., description="Ley aplicable (ej: 'Ley Concursal')")
    articulo: str = Field(..., description="Artículo concreto (ej: 'Art. 165.1')")
    deber: str = Field(..., description="Deber legal específico")


# ============================
# EVIDENCIA DOCUMENTAL
# ============================

class EvidenciaDocumental(BaseModel):
    """Evidencia trazable 1:1 al documento original."""
    chunk_id: str = Field(..., description="Chunk ID determinista")
    doc_id: str = Field(..., description="Document ID o filename")
    page: int | None = Field(None, description="Número de página")
    start_char: int = Field(..., description="Offset inicio en texto original")
    end_char: int = Field(..., description="Offset fin en texto original")
    extracto_literal: str = Field(..., description="Texto EXACTO del chunk (sin paráfrasis)")


# ============================
# ACUSACIÓN PROBATORIA
# ============================

class EvidenciaFaltante(BaseModel):
    """
    Evidencia requerida pero ausente que bloquea una acusación completa.
    
    ENDURECIMIENTO #5: Explicitación de qué falta y por qué bloquea.
    """
    rule_id: str = Field(..., description="ID de la regla que requiere esta evidencia")
    required_evidence: str = Field(..., description="Tipo de evidencia requerida")
    present_evidence: str = Field(..., description="Evidencia presente (o 'NONE')")
    blocking_reason: str = Field(..., description="Por qué esto bloquea la acusación")


class AcusacionProbatoria(BaseModel):
    """
    Acusación SOLO si cumple los 5 requisitos obligatorios.
    
    GATES BLOQUEANTES (ENDURECIMIENTO #5):
    1. Obligación legal definida
    2. Evidencia documental trazable
    3. Evidencia suficiente (no parcial)
    4. Nivel de confianza calculable
    5. Evidencia faltante listada si aplica
    6. Evidencia verificable del RAG (no_response_reason == None)
    """
    accusation_id: str = Field(..., description="ID único de acusación")
    
    # REQUISITO 1: Obligación legal concreta
    obligacion_legal: ObligacionLegal = Field(
        ...,
        description="Ley + artículo + deber específico"
    )
    
    # REQUISITO 2: Evidencia documental trazable
    evidencia_documental: List[EvidenciaDocumental] = Field(
        ...,
        min_items=1,
        description="Evidencias trazables (mínimo 1)"
    )
    
    # REQUISITO 3: Descripción fáctica (sin adjetivos, sin conclusiones)
    descripcion_factica: str = Field(
        ...,
        description="Descripción OBJETIVA de lo que el documento muestra literalmente"
    )
    
    # REQUISITO 4: Severidad evaluada
    severidad: Severidad = Field(
        ...,
        description="Severidad evaluada (BAJA|MEDIA|ALTA|CRITICA)"
    )
    
    # REQUISITO 5: Nivel de confianza CALCULADO (NO hardcoded)
    nivel_confianza: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Nivel de confianza calculado (0.0-1.0)"
    )
    
    # REQUISITO 6: Evidencia faltante explícita
    evidencia_faltante: List[EvidenciaFaltante] = Field(
        default_factory=list,
        description="Evidencias específicas que faltan (estructurado)"
    )
    
    @validator("evidencia_documental")
    def validate_evidencia_not_empty(cls, v):
        """GATE: Toda acusación DEBE tener al menos 1 evidencia."""
        if not v or len(v) == 0:
            raise ValueError("Acusación sin evidencia documental: PROHIBIDO")
        return v


# ============================
# SOLICITUD DE EVIDENCIA
# ============================

class SolicitudEvidencia(BaseModel):
    """Solicitud explícita cuando NO se puede acusar."""
    motivo: str = Field(
        ...,
        description="Por qué no se puede acusar (evidencia inexistente o parcial)"
    )
    evidencia_requerida: List[str] = Field(
        ...,
        min_items=1,
        description="Lista específica de documentos/evidencias necesarias"
    )


# ============================
# RESULTADO PROSECUTOR
# ============================

class AcusacionBloqueada(BaseModel):
    """
    Acusación BLOQUEADA por falta de evidencia verificable.
    
    ENDURECIMIENTO #5: Explicitación de bloqueo.
    """
    rule_id: str = Field(..., description="Regla que intentó aplicarse")
    blocked_reason: str = Field(..., description="Motivo del bloqueo")
    evidencia_faltante: List[EvidenciaFaltante] = Field(
        ...,
        description="Lista estructurada de evidencia faltante"
    )


class ProsecutorResult(BaseModel):
    """
    Resultado del agente Prosecutor.
    
    ENDURECIMIENTO #5: Puede contener:
    - acusaciones (completas)
    - acusaciones_bloqueadas (parciales, con evidencia_faltante)
    - solicitud_evidencia (si TODO está bloqueado)
    
    ENDURECIMIENTO #6: Incluye audit_trace (opcional) para replay determinista.
    
    PROHIBIDO: summaries, narrativa, texto libre.
    """
    case_id: str = Field(..., description="ID del caso")
    
    acusaciones: List[AcusacionProbatoria] = Field(
        default_factory=list,
        description="Acusaciones probatorias completas"
    )
    
    acusaciones_bloqueadas: List[AcusacionBloqueada] = Field(
        default_factory=list,
        description="Acusaciones bloqueadas por evidencia insuficiente"
    )
    
    solicitud_evidencia: SolicitudEvidencia | None = Field(
        None,
        description="Solicitud explícita si TODO está bloqueado"
    )
    
    # Contador (NO narrativa)
    total_acusaciones: int = Field(
        ...,
        description="Número total de acusaciones completas formuladas"
    )
    
    total_bloqueadas: int = Field(
        default=0,
        description="Número de acusaciones bloqueadas por evidencia insuficiente"
    )
    
    # ENDURECIMIENTO #6: Audit trace para replay determinista
    audit_trace_data: Optional[dict] = Field(
        None,
        description="Audit trace serializado para replay determinista (opcional)"
    )
