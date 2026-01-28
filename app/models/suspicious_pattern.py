"""
Modelo formal de patrones sospechosos con contrato auditable.

Para producción legal, cada patrón debe ser:
1. Reproducible (con criterios explícitos)
2. Auditable (con versión del detector)
3. Defendible (con base legal)
"""

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# =========================================================
# MODELO PYDANTIC: CONTRATO DE DETECTOR
# =========================================================


class PatternDetector(BaseModel):
    """
    Definición formal del detector de patrones.

    Garantiza reproducibilidad y auditabilidad:
    - Cada detector tiene un ID único versionado
    - Criterios explícitos en JSON
    - Base legal referenciada

    Example:
        detector = PatternDetector(
            detector_id="duplicate_invoice_v2",
            version="2.1.0",
            criteria={
                "threshold": 0.85,
                "window_days": 30,
                "min_amount": 1000.00
            },
            legal_basis="Art. 164.2.5º TRLC - Simulación contractual"
        )
    """

    detector_id: str = Field(
        ...,
        description="ID único del detector (ej: duplicate_invoice_v2)",
        min_length=3,
        max_length=100,
    )

    version: str = Field(
        ..., description="Versión semántica del detector (ej: 2.1.0)", pattern=r"^\d+\.\d+\.\d+$"
    )

    criteria: dict[str, Any] = Field(
        ...,
        description="Criterios técnicos usados para la detección (thresholds, ventanas temporales, etc.)",
    )

    legal_basis: str = Field(
        ..., description="Artículo legal que justifica este patrón como sospechoso", min_length=5
    )

    model_config = {"extra": "forbid"}


# =========================================================
# MODELO PYDANTIC: PATRÓN SOSPECHOSO
# =========================================================


class SuspiciousPatternBase(BaseModel):
    """
    Patrón sospechoso detectado con trazabilidad completa.

    Incluye:
    - Identificador único del patrón
    - Detector que lo identificó (con versión)
    - Severidad y confianza
    - Explicación reproducible
    - Evidencias con trazabilidad
    """

    pattern_type: str = Field(
        ..., description="Tipo de patrón (ej: duplicate_invoice, suspicious_transfer)", min_length=3
    )

    detected_by: PatternDetector = Field(..., description="Detector que identificó este patrón")

    severity: Literal["critical", "high", "medium", "low"] = Field(
        ..., description="Nivel de severidad del patrón"
    )

    severity_score: float = Field(
        ..., ge=0, le=100, description="Score numérico de severidad (0-100)"
    )

    confidence: float = Field(..., ge=0, le=1, description="Confianza del detector (0.0-1.0)")

    explanation: str = Field(
        ..., description="Explicación detallada y reproducible del patrón detectado", min_length=10
    )

    recommendation: Optional[str] = Field(
        None, description="Recomendación legal/técnica para este patrón"
    )

    # Evidencias (simplificado, en producción sería List[Evidence])
    evidence_ids: list[str] = Field(
        default_factory=list, description="IDs de las evidencias que soportan este patrón"
    )

    category: str = Field(
        default="otros", description="Categoría del patrón (ej: culpabilidad, elusión, simulación)"
    )


class SuspiciousPatternCreate(SuspiciousPatternBase):
    """Modelo para crear un nuevo patrón sospechoso."""

    case_id: str = Field(..., description="ID del caso al que pertenece este patrón")


class SuspiciousPatternResponse(SuspiciousPatternBase):
    """Modelo de respuesta con ID y fecha de detección."""

    pattern_id: str
    case_id: str
    detected_at: datetime

    class Config:
        from_attributes = True


# =========================================================
# MODELO SQLAlchemy: PERSISTENCIA
# =========================================================


class SuspiciousPattern(Base):
    """
    Tabla de patrones sospechosos detectados.

    Garantiza:
    - Persistencia de todos los patrones
    - Trazabilidad completa del detector
    - Auditoría de criterios usados
    - Base legal explícita
    """

    __tablename__ = "suspicious_patterns"

    # Identificación
    pattern_id: Mapped[str] = mapped_column(
        String(100), primary_key=True, comment="ID único del patrón detectado"
    )

    case_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="ID del caso al que pertenece"
    )

    # ✅ TRAZABILIDAD DE EJECUCIÓN (CRÍTICO LEGAL)
    pipeline_run_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="ID de la ejecución del pipeline que detectó este patrón (reproducibilidad)",
    )

    pattern_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="Tipo de patrón detectado"
    )

    # Detector (auditable)
    detector_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="ID del detector que identificó el patrón"
    )

    detector_version: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="Versión del detector (semver)"
    )

    detector_criteria: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="Criterios técnicos usados (JSON)"
    )

    legal_basis: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Base legal que justifica este patrón"
    )

    # Clasificación
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Nivel de severidad: critical/high/medium/low",
    )

    severity_score: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Score numérico 0-100"
    )

    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Confianza del detector 0.0-1.0"
    )

    category: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="Categoría del patrón"
    )

    # Explicación
    explanation: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Explicación detallada reproducible"
    )

    recommendation: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Recomendación legal/técnica"
    )

    # Evidencias
    evidence_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, comment="IDs de evidencias (JSON array)"
    )

    # Auditoría temporal
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Fecha/hora de detección (UTC)",
    )

    # Metadata adicional (opcional) - renombrado para evitar colisión con SQLAlchemy
    extra_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Metadata adicional específica del patrón"
    )

    def __repr__(self) -> str:
        return (
            f"<SuspiciousPattern("
            f"pattern_id={self.pattern_id}, "
            f"type={self.pattern_type}, "
            f"severity={self.severity}, "
            f"detector={self.detector_id}@{self.detector_version}"
            f")>"
        )
