"""
REDISEÑO PROSECUTOR: Schema probatorio estricto.

PRINCIPIO: NO EXISTE ACUSACIÓN SIN PRUEBA COMPLETA.
"""
from __future__ import annotations

from typing import List, Literal
from pydantic import BaseModel, Field


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

class AcusacionProbatoria(BaseModel):
    """
    Acusación SOLO si cumple los 5 requisitos obligatorios.
    
    GATES BLOQUEANTES:
    1. Obligación legal definida
    2. Evidencia documental trazable
    3. Evidencia suficiente (no parcial)
    4. Nivel de confianza calculable
    5. Evidencia faltante listada si aplica
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
    evidencia_faltante: List[str] = Field(
        default_factory=list,
        description="Documentos específicos que faltan para concluir"
    )


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

class ProsecutorResult(BaseModel):
    """
    Resultado del agente Prosecutor.
    
    SOLO contiene:
    - Lista de acusaciones probatorias (si las hay)
    - Solicitud de evidencia (si NO puede acusar)
    
    PROHIBIDO: summaries, narrativa, texto libre.
    """
    case_id: str = Field(..., description="ID del caso")
    
    acusaciones: List[AcusacionProbatoria] = Field(
        default_factory=list,
        description="Acusaciones probatorias (vacío si no hay evidencia suficiente)"
    )
    
    solicitud_evidencia: SolicitudEvidencia | None = Field(
        None,
        description="Solicitud explícita si no se puede acusar"
    )
    
    # Contador (NO narrativa)
    total_acusaciones: int = Field(
        ...,
        description="Número total de acusaciones formuladas"
    )
