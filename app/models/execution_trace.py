"""
Modelo ORM para `execution_traces`.

Esta tabla se creó originalmente por migración Alembic (de73ba5c43f9) para
persistir trazas de ejecución y permitir enlazar reportes certificados.

Aunque el pipeline “certificado” no es obligatorio para el MVP, el modelo
de `LegalReportDB` referencia `execution_traces.trace_id` como FK. Por eso,
esta tabla debe existir en el metadata cuando se ejecuta `app.core.init_db`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExecutionTraceDB(Base):
    __tablename__ = "execution_traces"

    trace_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    trace_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Serialización JSON del ExecutionTrace",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

