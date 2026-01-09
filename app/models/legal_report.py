"""
LEGAL REPORT - Modelo de informe legal certificable (PANTALLA 4).

PRINCIPIO: Esta es la PRIMERA capa que usa LENGUAJE LEGAL.
Traduce alertas técnicas a hallazgos jurídicos con base documental.

PROHIBIDO:
- generar conclusiones sin alerta técnica previa
- generar hallazgos sin evidencia física
- usar lenguaje especulativo ("podría", "parece", "probablemente")
- ocultar evidencia
- modificar chunks, alertas o trace
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ConfidenceLevel(str, Enum):
    """
    Nivel de confianza en un hallazgo legal.
    
    Basado en:
    - Cantidad de evidencia
    - Consistencia de la evidencia
    - Claridad de la base legal
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class LegalEvidenceLocation(BaseModel):
    """
    Location física de evidencia en el documento original.
    
    Datos EXACTOS del contrato de DocumentChunk.
    """
    start_char: int = Field(
        ...,
        description="Offset de inicio en texto original",
        ge=0
    )
    
    end_char: int = Field(
        ...,
        description="Offset de fin en texto original",
        ge=0
    )
    
    page_start: Optional[int] = Field(
        None,
        description="Página de inicio (1-indexed, si aplica)",
        ge=1
    )
    
    page_end: Optional[int] = Field(
        None,
        description="Página de fin (1-indexed, si aplica)",
        ge=1
    )
    
    extraction_method: str = Field(
        ...,
        description="Método de extracción del texto (pdf_text, ocr, table, etc)"
    )
    
    model_config = {"extra": "forbid"}


class LegalEvidence(BaseModel):
    """
    Evidencia física que soporta un hallazgo legal.
    
    CONTRATO:
    - chunk_id: identificador del chunk de evidencia
    - document_id: documento de origen
    - filename: nombre del archivo original
    - location: información física de ubicación (OBLIGATORIA)
    - content: texto LITERAL relevante (sin modificar)
    
    Cada hallazgo DEBE tener al menos 1 evidencia.
    """
    chunk_id: str = Field(
        ...,
        description="Identificador del chunk de evidencia",
        min_length=1
    )
    
    document_id: str = Field(
        ...,
        description="ID del documento de origen",
        min_length=1
    )
    
    filename: str = Field(
        ...,
        description="Nombre del archivo original",
        min_length=1
    )
    
    location: LegalEvidenceLocation = Field(
        ...,
        description="Información física de ubicación (OBLIGATORIA)"
    )
    
    content: str = Field(
        ...,
        description="Texto LITERAL relevante (sin modificar)",
        min_length=1
    )
    
    model_config = {"extra": "forbid"}


class LegalReference(BaseModel):
    """
    Referencia a base legal concreta.
    
    CONTRATO:
    - law_name: nombre de la ley (fijo: "Ley Concursal")
    - article: artículo específico citado
    - description: texto legal literal o técnico
    """
    law_name: str = Field(
        default="Ley Concursal",
        description="Nombre de la ley citada"
    )
    
    article: str = Field(
        ...,
        description="Artículo específico citado",
        min_length=1
    )
    
    description: str = Field(
        ...,
        description="Texto legal literal o técnico",
        min_length=10
    )
    
    model_config = {"extra": "forbid"}


class LegalFinding(BaseModel):
    """
    Hallazgo legal derivado de alertas técnicas.
    
    CONTRATO:
    - finding_id: identificador único del hallazgo
    - title: título conciso técnico-legal
    - description: descripción en lenguaje jurídico objetivo
    - related_alert_types: tipos de alerta técnica que originan el hallazgo
    - legal_basis: base legal concreta (artículos)
    - evidence: evidencia física (≥1 item)
    - confidence_level: nivel de confianza
    
    Cada hallazgo:
    - se mapea desde al menos una alerta técnica
    - incluye evidencia física
    - cita artículos concretos
    """
    finding_id: str = Field(
        ...,
        description="Identificador único del hallazgo",
        min_length=1
    )
    
    title: str = Field(
        ...,
        description="Título conciso técnico-legal",
        min_length=10,
        max_length=200
    )
    
    description: str = Field(
        ...,
        description="Descripción en lenguaje jurídico objetivo",
        min_length=20
    )
    
    related_alert_types: List[str] = Field(
        ...,
        description="Tipos de alerta técnica que originan el hallazgo",
        min_length=1
    )
    
    legal_basis: List[LegalReference] = Field(
        ...,
        description="Base legal concreta (artículos)",
        min_length=1
    )
    
    evidence: List[LegalEvidence] = Field(
        ...,
        description="Evidencia física (≥1 item)",
        min_length=1
    )
    
    confidence_level: ConfidenceLevel = Field(
        ...,
        description="Nivel de confianza en el hallazgo"
    )
    
    @field_validator('description')
    @classmethod
    def validate_description_is_not_speculative(cls, v: str) -> str:
        """
        Validar que la descripción no use lenguaje especulativo.
        
        Términos prohibidos:
        - podría, posiblemente, probablemente, quizás, tal vez
        - parece, aparenta, sugiere (cuando no hay certeza)
        """
        speculative_terms = [
            'podría', 'posiblemente', 'probablemente', 'quizás', 'tal vez',
            'quizá', 'acaso'
        ]
        
        v_lower = v.lower()
        for term in speculative_terms:
            if term in v_lower:
                raise ValueError(
                    f"Descripción contiene término especulativo prohibido: '{term}'. "
                    "Los hallazgos legales deben ser afirmativos y técnicos."
                )
        
        return v
    
    model_config = {"extra": "forbid"}


class LegalReport(BaseModel):
    """
    Informe legal certificable generado desde alertas técnicas.
    
    CONTRATO:
    - report_id: identificador único del informe
    - case_id: caso analizado
    - generated_at: timestamp de generación
    - schema_version: versión del esquema del informe
    - source_system: sistema de origen (fijo: "phoenix_legal")
    - issue_analyzed: descripción del asunto analizado
    - findings: lista de hallazgos legales (puede estar vacía)
    - disclaimer_legal: aviso legal obligatorio
    
    El informe:
    - es jurídicamente legible
    - cada afirmación es verificable físicamente
    - puede ser auditado ex post
    - es apto para revisión humana
    """
    report_id: str = Field(
        ...,
        description="Identificador único del informe",
        min_length=1
    )
    
    case_id: str = Field(
        ...,
        description="Caso analizado",
        min_length=1
    )
    
    generated_at: datetime = Field(
        ...,
        description="Timestamp de generación del informe"
    )
    
    schema_version: str = Field(
        default="1.0.0",
        description="Versión del esquema del informe"
    )
    
    source_system: str = Field(
        default="phoenix_legal",
        description="Sistema de origen del informe"
    )
    
    issue_analyzed: str = Field(
        ...,
        description="Descripción del asunto analizado",
        min_length=10
    )
    
    findings: List[LegalFinding] = Field(
        default_factory=list,
        description="Lista de hallazgos legales (puede estar vacía si no hay alertas)"
    )
    
    disclaimer_legal: str = Field(
        default=(
            "Este informe ha sido generado mediante análisis automatizado de documentación "
            "aportada. Los hallazgos presentados se basan en la detección técnica de patrones "
            "y anomalías en los datos, y deben ser revisados por un profesional legal cualificado "
            "antes de su uso en cualquier procedimiento judicial o administrativo. "
            "El sistema no sustituye el criterio jurídico experto."
        ),
        description="Aviso legal obligatorio"
    )
    
    model_config = {"extra": "forbid"}

