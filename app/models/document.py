from __future__ import annotations

import uuid
import os
import shutil
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    CheckConstraint,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.variables import DATA
from app.models.document_chunk import DocumentChunk  
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
    parsing_metrics: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
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
            "parsing_status IS NULL OR parsing_status IN ('PARSED_OK', 'PARSED_INVALID')",
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

def store_document_file(
    *,
    client_id: str,
    case_id: str,
    document_id: str,
    original_file_path: str,
) -> str:
    """
    Copia el archivo original al storage del sistema y devuelve la ruta final.

    Estructura en disco:
    DATA/<client_id>/cases/<case_id>/documents/
        YYYYMMDD_HHMMSS_<document_id>_<filename_original>
    """

    print("--------------------------------------------------")
    print("[INGESTA DOCUMENTAL] Inicio de custodia de archivo")
    print(f"Cliente      : {client_id}")
    print(f"Caso         : {case_id}")
    print(f"Document ID  : {document_id}")
    print(f"Origen       : {original_file_path}")

    # --------------------------------------------------
    # 1. Verificación del archivo original
    # --------------------------------------------------
    if not os.path.exists(original_file_path):
        raise FileNotFoundError(
            f"No existe el archivo original: {original_file_path}"
        )

    # --------------------------------------------------
    # 2. Timestamp (trazabilidad)
    # --------------------------------------------------
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    original_name = os.path.basename(original_file_path)

    # --------------------------------------------------
    # 3. Carpeta destino
    # --------------------------------------------------
    target_dir = (
        DATA
        / client_id
        / "cases"
        / case_id
        / "documents"
    )
    target_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------
    # 4. Nombre final
    # --------------------------------------------------
    target_filename = f"{timestamp}_{document_id}_{original_name}"
    target_path = target_dir / target_filename

    # --------------------------------------------------
    # 5. Copia física
    # --------------------------------------------------
    shutil.copy2(original_file_path, target_path)

    print("[INGESTA DOCUMENTAL] Custodia finalizada con éxito")
    print("--------------------------------------------------")

    return str(target_path)
