from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Risk(Base):
    """
    Riesgo detectado en un Case.
    Se usa para el semáforo concursal.
    """

    __tablename__ = "risks"

    risk_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)  # low, medium, high
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0–100

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    case = relationship("Case", backref="risks")
