from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.variables import DATA
from app.models.case import Case

case = relationship(Case, backref="documents")


# =========================================================
# CATÁLOGO DE TIPOS DOCUMENTALES (doc_type)
# =========================================================

DOCUMENT_TYPES = {
    # Financiero / contable
    "balance",
    "pyg",
    "mayor",
    "sumas_saldos",
    "extracto_bancario",
    # Societario
    "acta",
    "acuerdo_societario",
    "poder",
    # Dirección / gestión
    "email_direccion",
    "email_banco",
    "email_asesoria",
    # Operaciones
    "contrato",
    "venta_activo",
    "prestamo",
    "nomina",
}


# =========================================================
# PUNTO 1 — DOCUMENT (REGISTRO DOCUMENTAL / EVIDENCIA)
# =========================================================


class Document(Base):
    """
    Documento asociado a un Case.
    Representa evidencia legal (input documental).
    Punto 1 del sistema: SIN IA, SIN TEXTO PROCESADO.
    """

    __tablename__ = "documents"

    __table_args__ = (
        # Unique compuesto: mismo archivo puede estar en casos diferentes
        UniqueConstraint("case_id", "sha256_hash", name="uq_case_sha256"),
    )

    document_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # --- Identificación del caso ---
    case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Metadatos clave ---
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # =====================================================
    # INTEGRIDAD LEGAL Y CADENA DE CUSTODIA
    # =====================================================

    # Hash SHA256 del contenido binario original (inmutable)
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        unique=False,  # No unique global (mismo archivo puede estar en casos diferentes)
        nullable=False,
        index=True,
        comment="Hash SHA256 del archivo original para integridad y deduplicación",
    )

    # Tamaño del archivo original en bytes
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Tamaño en bytes del archivo original",
    )

    # Tipo MIME del archivo
    mime_type: Mapped[str] = mapped_column(
        String(127),
        nullable=False,
        comment="Tipo MIME del archivo (ej: application/pdf)",
    )

    # Timestamp de subida (cadena de custodia)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Momento exacto de subida al sistema (cadena de custodia)",
    )

    # ID del trace que procesó este documento (trazabilidad)
    processing_trace_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="ID del ExecutionTrace que procesó este documento",
    )

    # Legal hold (si está en litigio activo, no se puede borrar)
    legal_hold: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Si está en litigio activo (no se puede borrar)",
    )

    # Fecha hasta la que debe conservarse (RGPD + Código de Comercio)
    retention_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha hasta la que debe conservarse (Art. 30 Código de Comercio: 6 años)",
    )

    # =====================================================
    # DEDUPLICACIÓN (FASE 2A)
    # =====================================================

    # Hash SHA256 del texto normalizado (deduplicación semántica)
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="SHA256 del texto normalizado extraído (detecta contenido duplicado entre formatos)",
    )

    # Embedding del documento completo (para comparación semántica)
    document_embedding: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Embedding del documento completo (vector) para comparación de similaridad",
    )

    # Flag de duplicado
    is_duplicate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Indica si este documento es un duplicado de otro",
    )

    # Referencia al documento original (si es duplicado)
    duplicate_of_document_id: Mapped[Optional[str]] = mapped_column(
        String(36),  # UUID = 36 chars
        ForeignKey("documents.document_id"),
        nullable=True,
        index=True,
        comment="ID del documento original del que este es duplicado",
    )

    # Score de similaridad con el documento original (0.0 - 1.0)
    duplicate_similarity: Mapped[Optional[float]] = mapped_column(
        nullable=True,
        comment="Score de similaridad con el documento original (0.0=diferente, 1.0=idéntico)",
    )

    # Acción del abogado sobre el duplicado
    duplicate_action: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Acción del abogado: pending, keep_both, mark_duplicate, exclude_from_analysis",
    )

    # Auditoría de decisión del abogado (cadena de custodia legal)
    duplicate_action_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp de la decisión del abogado sobre duplicado",
    )

    duplicate_action_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Usuario/email que tomó la decisión sobre duplicado",
    )

    duplicate_action_reason: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Razón de la decisión (auditoría legal)",
    )

    # =====================================================
    # SOFT-DELETE (CRITICAL LEGAL: NO BORRADO FÍSICO)
    # =====================================================

    # Soft-delete: marca documento como excluido sin borrarlo físicamente
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Timestamp de soft-delete (null = activo)",
    )

    deleted_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Usuario/email que excluyó el documento",
    )

    deletion_reason: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Razón de la exclusión (auditoría legal)",
    )

    # Snapshot COMPLETO del estado antes de borrar (para rollback)
    snapshot_before_deletion: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Snapshot del Document antes de soft-delete (para recuperación/auditoría)",
    )

    # =====================================================

    doc_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    source: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )

    date_start: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    date_end: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    reliability: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    file_format: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    # Ruta FINAL del archivo bajo custodia del sistema
    storage_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # --- Texto bruto extraído (FASE 1 - SINGLE SOURCE OF TRUTH) ---
    raw_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Texto bruto extraído del documento (inmutable, single source of truth)",
    )

    # --- Validación de parsing (HARD) ---
    # REGLA 4: Estado explícito del documento
    parsing_status: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,  # NULL hasta que se valide
        index=True,
    )

    # REGLA 5: Motivo de rechazo normalizado (enum cerrado)
    parsing_rejection_reason: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    # REGLA 2: Métricas objetivas de calidad de extracción
    # FASE 2A: Incluye parser_used, num_entities, processing_time_ms, extraction_methods
    parsing_metrics: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Métricas de parsing: parser_used, num_entities, processing_time_ms, has_structured_data, extraction_methods",
    )

    # FASE 2A: Metadata de OCR (trazabilidad legal)
    ocr_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Metadata de OCR: applied, pages, language, chars_detected (trazabilidad para auditoría)",
    )

    # =====================================================
    # RELACIONES
    # =====================================================

    case = relationship(
        "Case",
        backref="documents",
    )

    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    # =====================================================
    # REGLAS DE INTEGRIDAD
    # =====================================================

    __table_args__ = (
        CheckConstraint(
            "date_start <= date_end",
            name="ck_documents_date_range",
        ),
        CheckConstraint(
            "reliability IN ('original', 'escaneado', 'foto')",
            name="ck_documents_reliability",
        ),
        CheckConstraint(
            "doc_type IN ("
            "'balance','pyg','mayor','sumas_saldos','extracto_bancario',"
            "'acta','acuerdo_societario','poder',"
            "'email_direccion','email_banco','email_asesoria',"
            "'contrato','venta_activo','prestamo','nomina'"
            ")",
            name="ck_documents_doc_type",
        ),
        CheckConstraint(
            # Históricamente el proyecto ha usado estados simples de pipeline
            # (pending/completed/failed/rejected). Algunas migraciones/etapas
            # introdujeron valores más “validación hard” (PARSED_OK/PARSED_INVALID).
            # Aceptamos ambos para compatibilidad y para que la ingesta no falle.
            "parsing_status IS NULL OR parsing_status IN ("
            "'pending','completed','failed','rejected',"
            "'PARSED_OK','PARSED_INVALID'"
            ")",
            name="ck_documents_parsing_status",
        ),
        CheckConstraint(
            "parsing_rejection_reason IS NULL OR parsing_rejection_reason IN ("
            "'NO_TEXT_EXTRACTED','TOO_FEW_CHARACTERS','TOO_FEW_PAGES',"
            "'LOW_TEXT_DENSITY','LOW_EXTRACTION_RATIO','PARSER_ERROR'"
            ")",
            name="ck_documents_rejection_reason",
        ),
    )


# =========================================================
# CUSTODIA DE ARCHIVOS (INPUT DOCUMENTAL)
# =========================================================


def calculate_file_hash(file_path: str) -> str:
    """
    Calcula el hash SHA256 de un archivo para integridad y deduplicación.

    Args:
        file_path: Ruta al archivo

    Returns:
        Hash SHA256 en hexadecimal (64 caracteres)

    Uso legal:
        - Cadena de custodia documental
        - Detección de duplicados
        - Verificación de integridad
        - Prueba pericial informática
    """
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        # Leer en chunks para soportar archivos grandes
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def get_file_size(file_path: str) -> int:
    """
    Obtiene el tamaño del archivo en bytes.

    Args:
        file_path: Ruta al archivo

    Returns:
        Tamaño en bytes
    """
    return os.path.getsize(file_path)


def get_mime_type(filename: str) -> str:
    """
    Determina el tipo MIME basado en la extensión del archivo.

    Args:
        filename: Nombre del archivo

    Returns:
        Tipo MIME (ej: "application/pdf")
    """
    ext = Path(filename).suffix.lower()

    mime_types = {
        ".pdf": "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".eml": "message/rfc822",
        ".msg": "application/vnd.ms-outlook",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }

    return mime_types.get(ext, "application/octet-stream")


def store_document_file(
    *,
    client_id: str,
    case_id: str,
    document_id: str,
    original_file_path: str,
    original_filename: str = None,
) -> dict:
    """
    Copia el archivo original al storage del sistema con integridad legal.

    Estructura en disco (NUEVA):
    DATA/<client_id>/cases/<case_id>/documents/original/
        <document_id>.<ext>

    Args:
        client_id: ID del cliente
        case_id: ID del caso
        document_id: UUID del documento
        original_file_path: Ruta temporal del archivo subido
        original_filename: Nombre original del archivo (opcional, se inferirá si no se proporciona)

    Returns:
        dict con metadatos de integridad legal:
            - storage_path: Ruta final del archivo
            - sha256_hash: Hash SHA256
            - file_size_bytes: Tamaño en bytes
            - mime_type: Tipo MIME
            - original_filename: Nombre original
    """

    print("--------------------------------------------------")
    print("[INGESTA DOCUMENTAL] Inicio de custodia con integridad legal")
    print(f"Cliente      : {client_id}")
    print(f"Caso         : {case_id}")
    print(f"Document ID  : {document_id}")
    print(f"Origen       : {original_file_path}")

    # --------------------------------------------------
    # 1. Verificación del archivo original
    # --------------------------------------------------
    if not os.path.exists(original_file_path):
        raise FileNotFoundError(f"No existe el archivo original: {original_file_path}")

    # --------------------------------------------------
    # 2. Calcular metadatos de integridad ANTES de mover
    # --------------------------------------------------
    # Usar el nombre original proporcionado o inferirlo del path
    if original_filename is None:
        original_filename = os.path.basename(original_file_path)

    sha256_hash = calculate_file_hash(original_file_path)
    file_size_bytes = get_file_size(original_file_path)
    mime_type = get_mime_type(original_filename)

    print(f"Nombre orig  : {original_filename}")
    print(f"SHA256       : {sha256_hash}")
    print(f"Tamaño       : {file_size_bytes} bytes")
    print(f"MIME Type    : {mime_type}")

    # --------------------------------------------------
    # 3. Carpeta destino: /original/ para inmutabilidad
    # --------------------------------------------------
    target_dir = (
        DATA
        / client_id
        / "cases"
        / case_id
        / "documents"
        / "original"  # Subdirectorio para archivos originales inmutables
    )
    target_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------
    # 4. Nombre final: <document_id>.<ext> (determinista)
    # --------------------------------------------------
    file_extension = Path(original_filename).suffix
    target_filename = f"{document_id}{file_extension}"
    target_path = target_dir / target_filename

    # --------------------------------------------------
    # 5. Copia física (inmutable, write-once)
    # --------------------------------------------------
    if target_path.exists():
        raise FileExistsError(f"Ya existe un archivo con este document_id: {target_path}")

    shutil.copy2(original_file_path, target_path)

    # Hacer el archivo read-only (inmutabilidad)
    os.chmod(target_path, 0o444)

    print("[INGESTA DOCUMENTAL] Custodia finalizada con éxito")
    print(f"Almacenado   : {target_path}")
    print("--------------------------------------------------")

    return {
        "storage_path": str(target_path),
        "sha256_hash": sha256_hash,
        "file_size_bytes": file_size_bytes,
        "mime_type": mime_type,
        "original_filename": original_filename,
    }
