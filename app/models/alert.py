from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Alert(Base):
    """
    Alerta de despacho (persistida).

    Nota: distinta de AnalysisAlert (técnica).
    Esta tabla almacena la salida "abogado-friendly" + estado editorial.
    """

    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="ID estable de alerta de despacho (no depende de timestamps)",
    )

    case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Dominio de negocio (no legal): TGSS/BANCO/CONTABILIDAD/VINCULADAS/DOCS
    domain: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Relevancia humana: ALTA/MEDIA/BAJA
    relevance: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # Score interno (0-100). No es protagonista en UI, pero se exporta/ordena si hace falta.
    score: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)

    title_human: Mapped[str] = mapped_column(Text, nullable=False)
    summary_human: Mapped[str] = mapped_column(Text, nullable=False)
    disclaimer_detail: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Checklist + acciones sugeridas (contrato despacho)
    # Estructura (lista de objetos):
    # - to_clarify: [{item_text, why_needed, blocking_level}]
    # - recommended_actions: [{action_text, priority, why}]
    to_clarify: Mapped[Optional[list[dict]]] = mapped_column(JSON, nullable=True)
    recommended_actions: Mapped[Optional[list[dict]]] = mapped_column(JSON, nullable=True)

    # Fingerprint estable del "hecho" (para merge/regeneración)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Referencias a alertas técnicas que alimentaron esta alerta (best-effort)
    source_alert_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)

    # Estado editorial (trabajo abogado)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente", index=True)
    lawyer_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    para_informe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    changed_since_last_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    rules_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    voice_prompt_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    generator_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dataset_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
    )
