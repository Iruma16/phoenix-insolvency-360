"""
Modelo persistente de pares de documentos duplicados.

CRÍTICO: Par es una entidad estable con identidad propia.
- pair_id único e inmutable
- Orden canónico (doc_a < doc_b)
- Versionado para control de concurrencia
- Snapshot para rollback
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DuplicatePair(Base):
    """
    Entidad persistente e inmutable de par de documentos duplicados.

    PRINCIPIOS CRÍTICOS:
    - Orden canónico SIEMPRE (doc_a_id < doc_b_id alfabéticamente)
    - pair_id = hash(doc_a + doc_b), independiente del orden de detección
    - Versionado para lock optimista
    - Snapshot antes de cada decisión para rollback
    - Metadata de similitud inmutable (explicabilidad)
    """

    __tablename__ = "duplicate_pairs"

    # Identidad única del par
    pair_id: Mapped[str] = mapped_column(
        String(40), primary_key=True, comment="Hash SHA256 del par ordenado canónicamente"
    )

    case_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True, comment="Caso al que pertenecen los documentos"
    )

    # Documentos del par (ORDEN CANÓNICO)
    doc_a_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="ID del primer documento (menor alfabéticamente)",
    )

    doc_b_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="ID del segundo documento (mayor alfabéticamente)",
    )

    # Metadata de detección (INMUTABLE)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, comment="Cuándo se detectó el duplicado"
    )

    similarity: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Score de similitud 0.0-1.0"
    )

    similarity_method: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Método usado: cosine_embeddings, hash_exact, etc."
    )

    similarity_model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Modelo usado si aplica: text-embedding-ada-002, etc."
    )

    duplicate_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="exact o semantic"
    )

    # Decisión (MUTABLE pero versionada)
    decision: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        default="pending",
        comment="pending, keep_both, mark_duplicate, exclude_from_analysis",
    )

    decision_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Versión de la decisión para lock optimista"
    )

    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="Cuándo se tomó la decisión"
    )

    decided_by: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Usuario que tomó la decisión"
    )

    decision_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Razón de la decisión (auditoría legal)"
    )

    # Snapshot para rollback
    snapshot_before_decision: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Estado completo antes de la última decisión"
    )

    # Invalidación en cascada (PUNTO 3)
    invalidated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True, comment="Cuándo se invalidó este par (si aplica)"
    )

    invalidation_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Por qué se invalidó (ej: documento excluido)"
    )

    # Soft-delete del par
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="Si el par fue eliminado (soft-delete)"
    )

    @staticmethod
    def generate_pair_id(doc_id_1: str, doc_id_2: str) -> str:
        """
        Genera pair_id canónico independiente del orden.

        Args:
            doc_id_1: ID del primer documento
            doc_id_2: ID del segundo documento

        Returns:
            Hash SHA256 truncado a 32 chars
        """
        ids_sorted = sorted([doc_id_1, doc_id_2])
        pair_str = f"{ids_sorted[0]}|{ids_sorted[1]}"
        return hashlib.sha256(pair_str.encode()).hexdigest()[:32]

    @staticmethod
    def get_canonical_order(doc_id_1: str, doc_id_2: str) -> tuple[str, str]:
        """
        Retorna IDs en orden canónico (alfabético).

        Returns:
            (doc_a_id, doc_b_id) donde doc_a < doc_b
        """
        ids_sorted = sorted([doc_id_1, doc_id_2])
        return ids_sorted[0], ids_sorted[1]

    def create_snapshot(self) -> dict:
        """
        Crea snapshot del estado actual para rollback.

        Returns:
            Dict con estado completo
        """
        return {
            "decision": self.decision,
            "decision_version": self.decision_version,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "decision_reason": self.decision_reason,
            "snapshot_at": datetime.utcnow().isoformat(),
        }


class SimilarityMetadata(BaseModel):
    """
    Metadata explicable de similitud.

    CRÍTICO: Permite auditar cómo se calculó el score.
    """

    score: float = Field(..., ge=0.0, le=1.0)
    method: str = Field(..., description="cosine_embeddings | hash_exact")
    model: Optional[str] = Field(None, description="Modelo usado si aplica")
    model_version: Optional[str] = None
    computed_at: datetime

    # Explicación human-readable
    explanation: str
    threshold_used: float
    confidence: str = Field(..., description="high | medium | low")

    # Componentes del score (si aplica)
    components: Optional[dict] = None


def explain_similarity(score: float, method: str, duplicate_type: str) -> str:
    """
    Genera explicación human-readable del score de similitud.

    Args:
        score: Score 0.0-1.0
        method: Método usado
        duplicate_type: exact o semantic

    Returns:
        Explicación clara para auditoría
    """
    if duplicate_type == "exact":
        return "Documentos idénticos a nivel binario (hash SHA256 coincide)"

    if method == "cosine_embeddings":
        if score >= 0.99:
            return f"Prácticamente idénticos ({score:.1%} similitud semántica)"
        elif score >= 0.95:
            return f"Alta similitud ({score:.1%}): contenido muy similar con ligeras variaciones"
        elif score >= 0.90:
            return f"Similitud moderada ({score:.1%}): mismo tema, diferente redacción"
        else:
            return f"Similitud baja ({score:.1%}): contenido potencialmente diferente"

    return f"Similitud {score:.1%} calculada con {method}"
