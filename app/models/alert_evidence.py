from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AlertEvidence(Base):
    """
    Evidencia normalizada asociada a una alerta de despacho.

    No inventa evidencia: se deriva de chunks/documentos existentes.
    """

    __tablename__ = "alert_evidences"

    evidence_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    alert_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("alerts.alert_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("documents.document_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    chunk_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    page_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    start_char: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_char: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    snippet: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Señal humana (1 frase) que explica “qué soporta” este snippet (sin conclusiones).
    signal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
