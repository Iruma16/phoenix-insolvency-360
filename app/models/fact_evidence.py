from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FactEvidence(Base):
    """
    Evidencia de un hecho: de qué documento/chunk viene, y dónde.
    Un mismo Fact puede tener muchas evidencias.
    """

    __tablename__ = "fact_evidences"

    evidence_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    fact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("facts.fact_id", ondelete="CASCADE"),
        nullable=False,
    )

    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )

    chunk_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )  # si lo enlazamos a chunk
    location_hint: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )  # "p2", "row 45", etc.
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    fact = relationship("Fact", backref="evidences")
    document = relationship("Document", backref="fact_evidences")
