"""
Auditoría inmutable de decisiones sobre duplicados.

CRÍTICO: Tabla append-only. NUNCA se modifica ni borra.
Cada decisión genera una entrada permanente para auditoría legal.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DuplicateDecisionAudit(Base):
    """
    Auditoría inmutable de cada decisión sobre duplicados.

    PRINCIPIOS CRÍTICOS:
    - Append-only: NO hay UPDATE ni DELETE
    - Snapshot completo del estado antes y después
    - Hash de integridad para detectar manipulación
    - Metadata completa del contexto de decisión
    """

    __tablename__ = "duplicate_decision_audit"

    audit_id: Mapped[str] = mapped_column(
        String(40),
        primary_key=True,
        default=lambda: uuid.uuid4().hex,
        comment="ID único de la entrada de auditoría",
    )

    pair_id: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True, comment="ID del par de duplicados"
    )

    case_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True, comment="ID del caso"
    )

    # Snapshot COMPLETO del estado anterior
    state_before: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="Estado completo del par ANTES de la decisión"
    )

    state_after: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="Estado completo del par DESPUÉS de la decisión"
    )

    # Hash de integridad (detecta manipulación)
    state_before_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="SHA256 del state_before para verificación"
    )

    state_after_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="SHA256 del state_after para verificación"
    )

    # Quién, cuándo, qué, por qué
    decided_by: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Usuario que tomó la decisión"
    )

    decided_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, comment="Timestamp de la decisión"
    )

    decision: Mapped[str] = mapped_column(String(50), nullable=False, comment="Decisión tomada")

    reason: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Razón de la decisión (obligatoria para auditoría legal)"
    )

    # Metadata del sistema
    system_version: Mapped[str] = mapped_column(
        String(50), nullable=False, default="1.0.0", comment="Versión de Phoenix Legal"
    )

    ip_address: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="IP del usuario (si disponible)"
    )

    user_agent: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="User agent (si disponible)"
    )

    # Version del par en el momento de la decisión
    pair_version: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="decision_version del par en ese momento"
    )

    @staticmethod
    def compute_hash(data: dict) -> str:
        """
        Calcula hash SHA256 de un dict para integridad.

        Args:
            data: Dict a hashear

        Returns:
            Hash SHA256 en hexadecimal
        """
        import json

        # Ordenar keys para hash consistente
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def verify_integrity(self) -> bool:
        """
        Verifica que los hashes coincidan con los snapshots.

        Returns:
            True si la integridad es válida
        """
        expected_before = self.compute_hash(self.state_before)
        expected_after = self.compute_hash(self.state_after)

        return self.state_before_hash == expected_before and self.state_after_hash == expected_after


def create_audit_entry(
    pair_id: str,
    case_id: str,
    state_before: dict,
    state_after: dict,
    decided_by: str,
    decision: str,
    reason: str,
    pair_version: int,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> DuplicateDecisionAudit:
    """
    Crea entrada de auditoría con hashes de integridad.

    Args:
        pair_id: ID del par
        case_id: ID del caso
        state_before: Estado antes de decisión
        state_after: Estado después de decisión
        decided_by: Usuario
        decision: Decisión tomada
        reason: Razón
        pair_version: Versión del par
        ip_address: IP del usuario (opcional)
        user_agent: User agent (opcional)

    Returns:
        Entrada de auditoría lista para persist
    """
    audit = DuplicateDecisionAudit(
        pair_id=pair_id,
        case_id=case_id,
        state_before=state_before,
        state_after=state_after,
        state_before_hash=DuplicateDecisionAudit.compute_hash(state_before),
        state_after_hash=DuplicateDecisionAudit.compute_hash(state_after),
        decided_by=decided_by,
        decision=decision,
        reason=reason,
        pair_version=pair_version,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return audit
