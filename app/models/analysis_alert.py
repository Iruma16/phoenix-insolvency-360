"""
ANALYSIS ALERT - Modelo de vista para alertas técnicas (PANTALLA 3).

PRINCIPIO: Este modelo NO interpreta ni concluye legalmente.
Solo detecta y expone problemas técnicos DETECTABLES en los datos.

NO permite:
- emitir conclusiones legales
- clasificar culpabilidad
- generar texto interpretativo
- usar LLMs o embeddings
- ocultar evidencia
- generar alertas sin soporte documental
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class AlertType(str, Enum):
    """
    Tipos de alerta TÉCNICOS (NO legales).

    Cada tipo representa un problema técnico detectable
    en la estructura, consistencia o integridad de los datos.
    """

    MISSING_DATA = "MISSING_DATA"
    INCONSISTENT_DATA = "INCONSISTENT_DATA"
    DUPLICATED_DATA = "DUPLICATED_DATA"
    TEMPORAL_INCONSISTENCY = "TEMPORAL_INCONSISTENCY"
    SUSPICIOUS_PATTERN = "SUSPICIOUS_PATTERN"


class AlertEvidenceLocation(BaseModel):
    """
    Location física de evidencia en el documento original.

    Datos EXACTOS del contrato de DocumentChunk.
    """

    start_char: int = Field(..., description="Offset de inicio en texto original", ge=0)

    end_char: int = Field(..., description="Offset de fin en texto original", ge=0)

    page_start: Optional[int] = Field(
        None, description="Página de inicio (1-indexed, si aplica)", ge=1
    )

    page_end: Optional[int] = Field(None, description="Página de fin (1-indexed, si aplica)", ge=1)

    extraction_method: str = Field(
        ..., description="Método de extracción del texto (pdf_text, ocr, table, etc)"
    )

    model_config = {"extra": "forbid"}


class AlertEvidence(BaseModel):
    """
    Evidencia física que soporta una alerta técnica.

    CONTRATO:
    - chunk_id: identificador del chunk de evidencia
    - document_id: documento de origen
    - filename: nombre del archivo original
    - location: información física de ubicación (OBLIGATORIA)
    - content: texto LITERAL relevante (sin modificar)

    Cada alerta DEBE tener al menos 1 evidencia.
    """

    chunk_id: str = Field(..., description="Identificador del chunk de evidencia", min_length=1)

    document_id: str = Field(..., description="ID del documento de origen", min_length=1)

    filename: str = Field(..., description="Nombre del archivo original", min_length=1)

    location: AlertEvidenceLocation = Field(
        ..., description="Información física de ubicación (OBLIGATORIA)"
    )

    content: str = Field(..., description="Texto LITERAL relevante (sin modificar)", min_length=1)

    model_config = {"extra": "forbid"}


class AnalysisAlert(BaseModel):
    """
    Alerta técnica detectada en el análisis de un caso.

    CONTRATO:
    - alert_id: identificador único de la alerta
    - case_id: caso al que pertenece
    - alert_type: tipo técnico de alerta (NO legal)
    - description: descripción técnica objetiva (≥10 chars)
    - evidence: lista de evidencia física (≥1 item)
    - created_at: timestamp de detección

    Las alertas son TÉCNICAS, NO legales.
    Cada alerta es verificable físicamente.
    NO hay inferencia ni juicio.
    """

    alert_id: str = Field(..., description="Identificador único de la alerta", min_length=1)

    case_id: str = Field(..., description="ID del caso al que pertenece", min_length=1)

    alert_type: AlertType = Field(..., description="Tipo técnico de alerta (NO legal)")

    description: str = Field(..., description="Descripción técnica objetiva", min_length=10)

    evidence: list[AlertEvidence] = Field(
        ..., description="Lista de evidencia física (≥1 item)", min_length=1
    )

    created_at: datetime = Field(..., description="Timestamp de detección de la alerta")

    @field_validator("description")
    @classmethod
    def validate_description_is_technical(cls, v: str) -> str:
        """
        Validar que la descripción sea técnica, no interpretativa.

        Palabras prohibidas (interpretativas/legales):
        - culpable, inocente, delito, fraude, crimen
        - malo, bueno, correcto, incorrecto (juicios de valor)
        """
        prohibited_legal_terms = [
            "culpable",
            "inocente",
            "delito",
            "fraude",
            "crimen",
            "culpabilidad",
            "responsabilidad penal",
            "condena",
        ]

        v_lower = v.lower()
        for term in prohibited_legal_terms:
            if term in v_lower:
                raise ValueError(
                    f"Descripción contiene término legal prohibido: '{term}'. "
                    "Las alertas deben ser técnicas, no legales."
                )

        return v

    model_config = {"extra": "forbid"}
