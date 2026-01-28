from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Fact(Base):
    """
    Hecho deduplicado. Es la unidad de verdad para cálculos.
    Ej: factura emitida, pago, transferencia, deuda, etc.
    """

    __tablename__ = "facts"

    fact_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
    )

    fact_type: Mapped[str] = mapped_column(String(64), nullable=False)  # invoice, payment, debt...
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex
    score_confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=70)  # 0-100

    # Campos comunes (opcionales; no siempre existirá todo)
    date_iso: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    amount_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    counterparty: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    case = relationship("Case", backref="facts")
