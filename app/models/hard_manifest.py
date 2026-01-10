"""
Modelo de persistencia para HardManifest.

Almacena el certificado técnico inmutable con hashes criptográficos
que garantizan la integridad del informe y del trace.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class HardManifestDB(Base):
    """
    Certificado técnico inmutable persistido en BD.
    
    Contiene hashes criptográficos del trace y del report,
    garantizando la inmutabilidad y trazabilidad del sistema.
    
    Relaciones:
    - Un ExecutionTraceDB tiene exactamente un HardManifestDB
    """
    
    __tablename__ = "hard_manifests"
    
    # Primary key
    manifest_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    
    # Foreign key
    trace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("execution_traces.trace_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # Un trace tiene exactamente un manifest
        index=True
    )
    
    # Hashes de certificación
    trace_hash: Mapped[str] = mapped_column(
        String(64),  # SHA-256 = 64 caracteres hex
        nullable=False,
        comment="Hash SHA-256 del trace completo"
    )
    
    report_hash: Mapped[str] = mapped_column(
        String(64),  # SHA-256 = 64 caracteres hex
        nullable=False,
        comment="Hash SHA-256 del report completo"
    )
    
    # Contenido serializado
    manifest_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Serialización JSON del HardManifest"
    )
    
    # Metadatos
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )
    
    # Relaciones
    # trace: Mapped["ExecutionTrace"] = relationship("ExecutionTrace", back_populates="hard_manifest", uselist=False)
    
    def __repr__(self) -> str:
        return f"<HardManifestDB(manifest_id={self.manifest_id}, trace_id={self.trace_id})>"
