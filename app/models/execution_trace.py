"""
Modelo de persistencia para ExecutionTrace.

Almacena la trazabilidad completa de la ejecución del agente legal,
incluyendo todos los pasos, decisiones y llamadas al LLM.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ExecutionTraceDB(Base):
    """
    Traza de ejecución del agente legal persistida en BD.
    
    Contiene el registro completo de la ejecución serializado como JSON,
    permitiendo reproducibilidad y auditoría.
    
    Relaciones:
    - Un Case puede tener múltiples ExecutionTraceDB (histórico)
    - Un ExecutionTraceDB tiene exactamente un LegalReportDB
    - Un ExecutionTraceDB tiene exactamente un HardManifestDB
    """
    
    __tablename__ = "execution_traces"
    
    # Primary key
    trace_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    
    # Foreign key
    case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Contenido serializado
    trace_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Serialización JSON del ExecutionTrace"
    )
    
    # Metadatos
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )
    
    # Relaciones
    # case: Mapped["Case"] = relationship("Case", back_populates="execution_traces")
    # legal_report: Mapped["LegalReport"] = relationship("LegalReport", back_populates="trace", uselist=False)
    # hard_manifest: Mapped["HardManifest"] = relationship("HardManifest", back_populates="trace", uselist=False)
    
    def __repr__(self) -> str:
        return f"<ExecutionTraceDB(trace_id={self.trace_id}, case_id={self.case_id})>"
