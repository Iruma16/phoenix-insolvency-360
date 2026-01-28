from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.exceptions import ChunkContractViolationError

# =========================================================
# CONTRATO FUNDACIONAL DE CHUNK (ENDURECIMIENTO 3.0)
# =========================================================


class ExtractionMethod(str, Enum):
    """
    Método de extracción del texto del chunk.

    OBLIGATORIO: Todo chunk DEBE declarar cómo fue extraído.
    """

    PDF_TEXT = "pdf_text"  # Texto nativo del PDF
    OCR = "ocr"  # OCR (PDF escaneado)
    TABLE = "table"  # Extracción de tabla
    DOCX_TEXT = "docx_text"  # Texto de DOCX
    TXT = "txt"  # Archivo de texto plano
    UNKNOWN = "unknown"  # Fallback (debe evitarse)


class ChunkLocation(BaseModel):
    """
    Ubicación OBLIGATORIA de un chunk en el documento original.

    CONTRATO DURO (ENDURECIMIENTO 3.0):
    - char_start < char_end (SIEMPRE)
    - page_start <= page_end (si ambos existen)
    - extraction_method SIEMPRE informado
    - NO se permiten offsets implícitos o asumidos

    Este contrato es PREREQUISITO para:
    - Offsets reales (Endurecimiento 3.1)
    - RAG con evidencia obligatoria (Endurecimiento 4)
    - Plantilla formal legal (Endurecimiento 5)
    """

    char_start: int = Field(
        ..., description="Offset de inicio en texto original (OBLIGATORIO)", ge=0
    )

    char_end: int = Field(..., description="Offset de fin en texto original (OBLIGATORIO)", ge=0)

    extraction_method: ExtractionMethod = Field(
        ..., description="Método de extracción (OBLIGATORIO)"
    )

    page_start: Optional[int] = Field(
        None, description="Página de inicio (1-indexed, opcional)", ge=1
    )

    page_end: Optional[int] = Field(None, description="Página de fin (1-indexed, opcional)", ge=1)

    @field_validator("char_end")
    @classmethod
    def validate_char_range(cls, v: int, info) -> int:
        """REGLA DURA: char_start < char_end"""
        char_start = info.data.get("char_start")
        if char_start is not None and v <= char_start:
            raise ChunkContractViolationError(
                rule_violated=f"char_end ({v}) debe ser > char_start ({char_start})"
            )
        return v

    @field_validator("page_end")
    @classmethod
    def validate_page_range(cls, v: Optional[int], info) -> Optional[int]:
        """REGLA DURA: page_start <= page_end (si ambos existen)"""
        if v is None:
            return v

        page_start = info.data.get("page_start")
        if page_start is not None and v < page_start:
            raise ChunkContractViolationError(
                rule_violated=f"page_end ({v}) debe ser >= page_start ({page_start})"
            )
        return v

    model_config = {"extra": "forbid", "validate_assignment": True}


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
    MODELO SQL - Fragmento (chunk) de documento.

    CONTRATO FUNDACIONAL (ENDURECIMIENTO 3.0):
    - chunk_id DEBE ser determinista
    - location OBLIGATORIA (char_start, char_end, extraction_method)
    - NO se permite creación sin contrato válido

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

    # =========================================================
    # LOCATION (OBLIGATORIO - ENDURECIMIENTO 3.0)
    # =========================================================

    # Offsets reales en texto original (OBLIGATORIO)
    start_char: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Offset de inicio en texto original (OBLIGATORIO)",
    )

    end_char: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Offset de fin en texto original (OBLIGATORIO)",
    )

    # Método de extracción (OBLIGATORIO)
    extraction_method: Mapped[str] = mapped_column(
        SQLEnum(ExtractionMethod),
        nullable=False,
        comment="Método de extracción del texto (OBLIGATORIO)",
    )

    # Páginas de origen (OPCIONAL - NULL si no aplica)
    page_start: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Página de inicio (1-indexed) o NULL",
    )

    page_end: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Página de fin (1-indexed) o NULL",
    )

    # =========================================================
    # METADATA ADICIONAL (OPCIONAL)
    # =========================================================

    # Section hint controlado (NULL si no se puede inferir)
    section_hint: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Sección/encabezado inferido o NULL",
    )

    # Estrategia de chunking aplicada
    chunking_strategy: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Estrategia de chunking aplicada",
    )

    # Hash de contenido (opcional)
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64),  # SHA256 hex = 64 caracteres
        nullable=True,
        comment="SHA256 del contenido del chunk (opcional)",
    )

    # Tipo de contenido detectado (opcional)
    content_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Tipo de contenido: table/text/list (opcional)",
    )

    # Relación inversa con Document
    document = relationship(
        "Document",
        back_populates="chunks",
    )

    def get_location(self) -> ChunkLocation:
        """
        Retorna ChunkLocation validado del chunk.

        Aplica validaciones del contrato HARD.
        """
        return ChunkLocation(
            char_start=self.start_char,
            char_end=self.end_char,
            extraction_method=ExtractionMethod(self.extraction_method),
            page_start=self.page_start,
            page_end=self.page_end,
        )

    def validate_contract(self) -> None:
        """
        Valida que el chunk cumpla el contrato fundacional.

        REGLAS DURAS:
        - char_start < char_end
        - page_start <= page_end (si ambos existen)
        - extraction_method informado

        Raises:
            ChunkContractViolationError: Si alguna regla falla
        """
        # Validar offsets
        if self.end_char <= self.start_char:
            raise ChunkContractViolationError(
                rule_violated=f"end_char ({self.end_char}) debe ser > start_char ({self.start_char})",
                chunk_id=self.chunk_id,
            )

        # Validar páginas (si existen)
        if self.page_start is not None and self.page_end is not None:
            if self.page_end < self.page_start:
                raise ChunkContractViolationError(
                    rule_violated=f"page_end ({self.page_end}) debe ser >= page_start ({self.page_start})",
                    chunk_id=self.chunk_id,
                )

        # Validar extraction_method
        if not self.extraction_method:
            raise ChunkContractViolationError(
                rule_violated="extraction_method es obligatorio", chunk_id=self.chunk_id
            )
