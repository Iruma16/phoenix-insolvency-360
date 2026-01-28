"""
INTEGRACIÓN FAIL-FAST DE VALIDACIÓN PRE-INGESTA

ENDURECIMIENTO #2 (FASE 3):
Bloquear documentos inválidos ANTES de:
- Chunking
- Embeddings
- Persistencia en DB
- Vectorstore

Modo STRICT: Excepción bloquea todo el pipeline
Modo PERMISSIVE: Documento rechazado pero pipeline continúa con otros
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from app.core.exceptions import DocumentValidationError
from app.core.logger import logger
from app.services.document_pre_ingestion_validation import (
    PreIngestionValidationResult,
    log_pre_ingestion_validation,
    validate_document_pre_ingestion,
)


class ValidationMode(str, Enum):
    """
    Modo de validación fail-fast.

    STRICT: Documento inválido → EXCEPCIÓN (bloquea todo)
    PERMISSIVE: Documento inválido → LOG + SKIP (continúa con otros)
    """

    STRICT = "strict"
    PERMISSIVE = "permissive"


def validate_document_failfast(
    file_path: Path,
    extracted_text: Optional[str],
    case_id: str,
    mode: ValidationMode = ValidationMode.STRICT,
) -> PreIngestionValidationResult:
    """
    Ejecuta validación fail-fast pre-ingesta.

    Args:
        file_path: Ruta del archivo a validar
        extracted_text: Texto extraído del documento
        case_id: ID del caso (para logging)
        mode: Modo de validación (STRICT o PERMISSIVE)

    Returns:
        PreIngestionValidationResult

    Raises:
        DocumentValidationError: Si mode=STRICT y documento es inválido
    """
    logger.info(f"[FAIL-FAST] Validando documento: {file_path.name} (modo={mode.value})")

    # Ejecutar validación completa
    result = validate_document_pre_ingestion(
        file_path=file_path,
        extracted_text=extracted_text,
    )

    # Logging estructurado obligatorio
    log_pre_ingestion_validation(case_id=case_id, result=result)

    # Comportamiento según modo
    if not result.is_valid:
        if mode == ValidationMode.STRICT:
            # MODO STRICT: Lanzar excepción y bloquear pipeline
            logger.error(
                f"[FAIL-FAST] MODO STRICT: Documento rechazado. "
                f"reject_code={result.reject_code}, file={file_path.name}"
            )
            raise DocumentValidationError(
                reject_code=result.reject_code or "UNKNOWN",
                reason=result.details.get("reject_reason", "Unknown reason"),
                filename=file_path.name,
            )
        else:
            # MODO PERMISSIVE: Log y retornar resultado (sin bloquear)
            logger.warning(
                f"[FAIL-FAST] MODO PERMISSIVE: Documento rechazado pero pipeline continúa. "
                f"reject_code={result.reject_code}, file={file_path.name}"
            )
    else:
        logger.info(f"[FAIL-FAST] ✅ Documento válido: {file_path.name}")

    return result


def should_skip_document(result: PreIngestionValidationResult) -> bool:
    """
    Determina si un documento debe ser skipped basado en el resultado de validación.

    Args:
        result: Resultado de validación

    Returns:
        True si el documento debe ser skipped (no procesar chunking/embeddings)
    """
    return not result.is_valid
