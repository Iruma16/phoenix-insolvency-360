"""
Modelo de Dictamen Jurídico Preliminar.

FASE 1.3: Balance de Situación Automático
"""
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

# Disclaimer legal estándar
DISCLAIMER_BALANCE_CONCURSAL = """
═══════════════════════════════════════════════════════════════
ADVERTENCIA LEGAL — ANÁLISIS PRELIMINAR
═══════════════════════════════════════════════════════════════

Este análisis automatizado de Balance de Situación Concursal:

✓ Es una herramienta de asistencia técnica preliminar
✓ Se basa exclusivamente en la documentación aportada al sistema
✓ Utiliza reglas automatizadas del TRLC (RDL 1/2020)
✓ Puede contener errores de extracción o interpretación

✗ NO constituye asesoramiento legal ni dictamen jurídico
✗ NO sustituye la revisión de un abogado concursalista
✗ NO garantiza exactitud absoluta de datos extraídos
✗ NO toma decisiones legales vinculantes
✗ La calificación definitiva corresponde al órgano judicial

OBLIGATORIO: Toda conclusión debe ser validada por un profesional
del Derecho especializado en Derecho Concursal antes de tomar
cualquier decisión (presentación de concurso, clasificación de
créditos, impugnaciones, etc.).

Phoenix Legal declina cualquier responsabilidad por decisiones
tomadas sin validación profesional adecuada.

═══════════════════════════════════════════════════════════════
"""


class OpinionConclusion(str, Enum):
    """Conclusión del dictamen jurídico."""

    INSOLVENCIA_ACTUAL_ACREDITADA = "insolvencia_actual_acreditada"
    INSOLVENCIA_INMINENTE = "insolvencia_inminente"
    SITUACION_PREOCUPANTE = "situacion_preocupante"
    SIN_INDICIOS_INSOLVENCIA = "sin_indicios_insolvencia"


class LegalOpinion(BaseModel):
    """Dictamen jurídico preliminar estructurado."""

    conclusion: OpinionConclusion

    fundamentos: list[str] = Field(..., description="Fundamentos jurídicos de la conclusión")

    base_legal: list[str] = Field(
        ...,
        description="Artículos TRLC citados explícitamente (P0.11 - defensibilidad jurídica)",
        json_schema_extra={"example": ["Art. 2.2 TRLC", "Art. 249 TRLC"]},
    )

    confianza: Literal["ALTA", "MEDIA", "BAJA"]

    recomendacion: str = Field(..., description="Recomendación legal clara y accionable")

    advertencia: str = Field(
        default=DISCLAIMER_BALANCE_CONCURSAL, description="Advertencia legal estándar"
    )

    model_config = {"extra": "forbid"}
