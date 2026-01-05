from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def generate_deterministic_chunk_id(
    case_id: str,
    doc_id: str,
    chunk_index: int,
    start_char: int,
    end_char: int,
) -> str:
    """
    Genera chunk_id DETERMINISTA y reproducible.
    
    CORRECCIÓN: NO usar uuid4 aleatorio.
    chunk_id depende de: case_id, doc_id, chunk_index, start_char, end_char.
    """
    components = f"{case_id}|{doc_id}|{chunk_index}|{start_char}|{end_char}"
    hash_digest = hashlib.sha256(components.encode()).hexdigest()
    return f"chunk_{hash_digest[:32]}"


class DocumentChunk(Base):
    """
    MODELO SQL.
    Representa un fragmento (chunk) de un documento.

    NO hace chunking.
    NO lee archivos.
    NO genera embeddings.
    """

    __tablename__ = "document_chunks"

    chunk_id: Mapped[str] = mapped_column(
        String(40),  # Aumentado para sha256 truncado
        primary_key=True,
        # NO default - se calcula explícitamente al crear chunk
    )

    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    
    # --- METADATA OBLIGATORIA DE TRAZABILIDAD (REGLA 1) ---
    # Offsets reales en texto original (REGLA 2)
    start_char: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Offset de inicio en texto original",
    )
    
    end_char: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Offset de fin en texto original",
    )
    
    # Página de origen (NULL si no aplica - ej: TXT)
    page: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Número de página del documento o NULL",
    )
    
    # Section hint controlado (NULL si no se puede inferir - REGLA 4)
    section_hint: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Sección/encabezado inferido o NULL",
    )
    
    # Estrategia de chunking aplicada (REGLA 3)
    chunking_strategy: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Estrategia de chunking aplicada",
    )

    # Relación inversa con Document
    document = relationship(
        "Document",
        back_populates="chunks",
    )
