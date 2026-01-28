"""
Modelo de ejecución de análisis con versionado completo.

CRÍTICO PARA DEFENSA LEGAL:
- Cada análisis tiene un run_id único
- Versiones de todos los detectores registradas
- Documentos incluidos listados
- Permite explicar divergencias entre ejecuciones

Ejemplo de uso:
    Run A (2026-01-10): 15 docs → 23 patrones detectados
    Run B (2026-01-12): 18 docs → 28 patrones detectados
    
    Con AnalysisExecution:
    ✅ Sabemos QUÉ documentos nuevos causaron los 5 patrones extra
    ✅ Sabemos QUÉ versión del detector se usó
    ✅ Reproducible y defendible legalmente
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AnalysisExecution(Base):
    """
    Registro de ejecución completa de análisis con versionado.

    Garantiza reproducibilidad legal:
    - ID único de cada run
    - Timestamp exacto de inicio/fin
    - Versiones de todos los modelos/detectores
    - Lista de documentos analizados
    - Resultado agregado

    Permite auditoría temporal:
    - "¿Qué documentos tenía el caso el 10/01/2026?"
    - "¿Qué versión del detector de duplicados se usó?"
    - "¿Por qué ahora detecta 5 patrones más?"
    """

    __tablename__ = "analysis_executions"

    # =========================================================
    # IDENTIFICACIÓN
    # =========================================================

    run_id: Mapped[str] = mapped_column(
        String(100), primary_key=True, comment="UUID único de esta ejecución"
    )

    case_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="ID del caso analizado"
    )

    # =========================================================
    # TIMESTAMPS
    # =========================================================

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Timestamp de inicio de análisis (UTC)",
    )

    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Timestamp de fin de análisis (UTC)"
    )

    # =========================================================
    # VERSIONADO DE MODELOS Y DETECTORES
    # =========================================================

    model_versions: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="""
        Versiones de todos los componentes usados.
        Ejemplo:
        {
            "balance_parser": "v2.1.0",
            "timeline_builder": "v1.3.0",
            "credit_classifier": "v2.0.0",
            "pattern_detectors": {
                "duplicate_invoice_v2": "2.0.0",
                "suspicious_transfer": "1.5.0",
                "hidden_assets": "1.2.0"
            },
            "legal_rag": {
                "model": "gpt-4",
                "embedding": "text-embedding-3-small"
            }
        }
        """,
    )

    # =========================================================
    # DOCUMENTOS INCLUIDOS
    # =========================================================

    document_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, comment="IDs de documentos analizados en este run (snapshot)"
    )

    document_count: Mapped[int] = mapped_column(
        nullable=False, comment="Número total de documentos analizados"
    )

    # =========================================================
    # ESTADO Y RESULTADO
    # =========================================================

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="Estado: running/completed/failed/cancelled"
    )

    result_summary: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="""
        Resumen de resultados agregados.
        Ejemplo:
        {
            "timeline_events": 157,
            "suspicious_patterns": 23,
            "balance_found": true,
            "insolvency_detected": true,
            "total_debt": 1250000.0,
            "ratios_calculated": 5
        }
        """,
    )

    # =========================================================
    # ERROR HANDLING
    # =========================================================

    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Mensaje de error si status=failed"
    )

    error_traceback: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Traceback completo si status=failed"
    )

    # =========================================================
    # METADATA Y AUDITORÍA
    # =========================================================

    triggered_by: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Usuario o sistema que disparó el análisis"
    )

    trigger_reason: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Razón del análisis: manual/scheduled/document_upload/etc",
    )

    execution_time_seconds: Mapped[Optional[float]] = mapped_column(
        nullable=True, comment="Tiempo de ejecución en segundos"
    )

    extra_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Metadata adicional específica"
    )

    def __repr__(self) -> str:
        return (
            f"<AnalysisExecution("
            f"run_id={self.run_id[:8]}..., "
            f"case={self.case_id[:8]}..., "
            f"status={self.status}, "
            f"docs={self.document_count}"
            f")>"
        )

    def to_dict(self) -> dict:
        """Convierte a dict para serialización."""
        return {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "model_versions": self.model_versions,
            "document_ids": self.document_ids,
            "document_count": self.document_count,
            "status": self.status,
            "result_summary": self.result_summary,
            "triggered_by": self.triggered_by,
            "execution_time_seconds": self.execution_time_seconds,
        }
