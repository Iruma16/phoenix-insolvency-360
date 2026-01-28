from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Event(Base):
    """
    Hecho relevante en la historia del Case.
    Ejemplos:
    - pérdida relevante
    - venta de activo
    - pago a acreedor
    - email clave
    - presentación de concurso
    """

    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source_document_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("documents.document_id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relaciones
    case = relationship("Case", backref="events")
    document = relationship("Document", backref="events")
