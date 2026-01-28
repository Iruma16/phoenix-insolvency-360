"""
Modelo de persistencia para LegalReport.

Almacena el informe legal certificado generado por el sistema,
vinculado al caso y al trace de ejecución.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LegalReportDB(Base):
    """
    Informe legal certificado persistido en BD.

    Contiene el resultado serializado del análisis legal (LegalOutput)
    junto con referencias al caso y al trace de ejecución.

    Relaciones:
    - Un Case puede tener múltiples LegalReportDB (histórico)
    - Un LegalReportDB tiene exactamente un ExecutionTraceDB
    """

    __tablename__ = "legal_reports"

    # Primary key
    report_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Foreign keys
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False, index=True
    )

    trace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("execution_traces.trace_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # Un trace genera exactamente un report
        index=True,
    )

    # Contenido serializado
    content_json: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Serialización JSON del LegalOutput"
    )

    # Metadatos
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relaciones
    # case: Mapped["Case"] = relationship("Case", back_populates="legal_reports")
    # trace: Mapped["ExecutionTrace"] = relationship("ExecutionTrace", back_populates="legal_report", uselist=False)

    def __repr__(self) -> str:
        return f"<LegalReportDB(report_id={self.report_id}, case_id={self.case_id}, trace_id={self.trace_id})>"
