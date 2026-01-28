"""
Modelo formal de eventos del timeline con persistencia en BD.

Permite queries paginadas y filtradas eficientemente para escalabilidad.

Garantiza:
- Paginación eficiente con índices optimizados
- Filtros por tipo, fecha, monto, severidad
- Búsqueda full-text en descripción
- Trazabilidad completa con evidencias
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TimelineEvent(Base):
    """
    Evento del timeline persistido en BD.

    Optimizado para queries paginadas y filtradas:
    - Índice compuesto (case_id, date) para paginación eficiente
    - Índices adicionales para filtros comunes
    - JSON para evidencias flexibles
    """

    __tablename__ = "timeline_events"

    # =========================================================
    # IDENTIFICACIÓN
    # =========================================================

    event_id: Mapped[str] = mapped_column(
        String(100), primary_key=True, comment="ID único del evento (UUID)"
    )

    case_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,  # ✅ Índice para queries por caso
        comment="ID del caso al que pertenece",
    )

    # ✅ TRAZABILIDAD DE EJECUCIÓN (CRÍTICO LEGAL)
    analysis_run_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,  # ✅ Índice para queries por ejecución
        comment="ID de la ejecución de análisis que generó este evento (reproducibilidad)",
    )

    # =========================================================
    # DATOS DEL EVENTO
    # =========================================================

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,  # ✅ Índice para ordenamiento y filtrado por fecha
        comment="Fecha del evento (UTC)",
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,  # ✅ Índice para filtrado por tipo
        comment="Tipo: embargo, factura_vencida, reclamacion, evento_corporativo",
    )

    category: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,  # ✅ Índice para filtrado por categoría
        comment="Categoría: financiero, legal, operativo",
    )

    description: Mapped[str] = mapped_column(Text, nullable=False, comment="Descripción del evento")

    title: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="Título corto del evento (opcional)"
    )

    amount: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Importe asociado en euros (si aplica)"
    )

    severity: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,  # ✅ Índice para filtrado por severidad
        comment="Severidad: critical, high, medium, low",
    )

    # =========================================================
    # EVIDENCIA Y TRAZABILIDAD
    # =========================================================

    document_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,  # ✅ Índice para queries por documento
        comment="ID del documento fuente",
    )

    chunk_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="ID del chunk fuente"
    )

    page: Mapped[Optional[int]] = mapped_column(
        nullable=True, comment="Número de página en el documento"
    )

    evidence: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Evidencia probatoria completa (JSON)"
    )

    # =========================================================
    # METADATA Y CALIDAD
    # =========================================================

    extraction_method: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Método de extracción: pdf_text, excel_cell, llm, rule_engine",
    )

    extraction_confidence: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Confianza de extracción 0.0-1.0"
    )

    source_reliability: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="Fiabilidad de fuente: official, reliable, uncertain"
    )

    extra_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Metadata adicional específica del tipo de evento"
    )

    # =========================================================
    # AUDITORÍA TEMPORAL
    # =========================================================

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Fecha de creación del registro en BD (UTC)",
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=lambda: datetime.now(timezone.utc),
        comment="Fecha de última actualización (UTC)",
    )

    # =========================================================
    # ÍNDICES COMPUESTOS OPTIMIZADOS
    # =========================================================

    __table_args__ = (
        # Índice principal para paginación ordenada por fecha
        Index(
            "ix_timeline_case_date_desc",
            "case_id",
            "date",
            postgresql_ops={"date": "DESC"},  # Optimizar para ORDER BY date DESC
        ),
        # Índice para filtro por tipo + fecha
        Index("ix_timeline_case_type_date", "case_id", "event_type", "date"),
        # Índice para filtro por severidad + fecha
        Index("ix_timeline_case_severity_date", "case_id", "severity", "date"),
        # Índice para filtro por categoría + fecha
        Index("ix_timeline_case_category_date", "case_id", "category", "date"),
    )

    def __repr__(self) -> str:
        return (
            f"<TimelineEvent("
            f"id={self.event_id[:8]}..., "
            f"case={self.case_id[:8]}..., "
            f"date={self.date.strftime('%Y-%m-%d') if self.date else 'N/A'}, "
            f"type={self.event_type}"
            f")>"
        )

    def to_dict(self) -> dict:
        """Convierte el evento a diccionario para serialización."""
        return {
            "event_id": self.event_id,
            "case_id": self.case_id,
            "date": self.date.isoformat() if self.date else None,
            "event_type": self.event_type,
            "category": self.category,
            "description": self.description,
            "title": self.title,
            "amount": self.amount,
            "severity": self.severity,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "page": self.page,
            "evidence": self.evidence,
            "extraction_method": self.extraction_method,
            "extraction_confidence": self.extraction_confidence,
            "source_reliability": self.source_reliability,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
