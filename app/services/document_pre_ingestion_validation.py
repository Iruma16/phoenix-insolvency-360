"""
VALIDACIÓN DURA PRE-INGESTA (FAIL FAST)

Endurecimiento #2: Bloquear documentos de calidad insuficiente ANTES de:
- Chunking
- Embeddings
- Persistencia en vectorstore

PRINCIPIO: FAIL HARD si cualquier check falla.
El documento NO debe contaminar el RAG ni la plantilla legal.

Versión del validador: 1.0.0
"""
from __future__ import annotations

import os
import chardet
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from pathlib import Path
from datetime import datetime
import PyPDF2

from app.core.logger import logger


# =========================================================
# CONSTANTES Y CONFIGURACIÓN
# =========================================================

VALIDATOR_VERSION = "1.0.0"

# Formatos soportados (WHITELIST explícita)
SUPPORTED_FORMATS = {
    ".pdf",
    ".txt",
    ".docx",
    ".doc",
    ".csv",
    ".xls",
    ".xlsx",
}

# Umbrales DUROS (más estrictos que validación post-parsing)
MIN_TEXT_LENGTH_HARD = 100  # Mínimo absoluto: 100 caracteres
MIN_TEXT_NOISE_RATIO = 0.7  # 70% del texto debe ser alfanumérico/espacios
MAX_FILE_SIZE_MB = 50  # Máximo 50 MB por archivo

# Encodings válidos para archivos de texto
VALID_TEXT_ENCODINGS = {
    "utf-8",
    "utf-16",
    "latin-1",
    "iso-8859-1",
    "windows-1252",
    "ascii",
}


# =========================================================
# ENUMS: CÓDIGOS DE RECHAZO
# =========================================================

class PreIngestionRejectCode(str, Enum):
    """
    Códigos normalizados de rechazo PRE-ingesta.
    Nomenclatura: [CATEGORIA]_[DETALLE]
    """
    # Formato
    FORMAT_UNSUPPORTED = "FORMAT_UNSUPPORTED"
    FORMAT_CORRUPTED = "FORMAT_CORRUPTED"
    
    # Encriptación/Protección
    ENCRYPTION_DETECTED = "ENCRYPTION_DETECTED"
    PASSWORD_PROTECTED = "PASSWORD_PROTECTED"
    
    # Contenido
    CONTENT_TOO_SHORT = "CONTENT_TOO_SHORT"
    CONTENT_TOO_NOISY = "CONTENT_TOO_NOISY"
    CONTENT_NO_TEXT_EXTRACTED = "CONTENT_NO_TEXT_EXTRACTED"
    
    # PDF específico
    PDF_SCANNED_NO_OCR = "PDF_SCANNED_NO_OCR"
    PDF_CORRUPTED = "PDF_CORRUPTED"
    
    # Encoding
    ENCODING_INVALID = "ENCODING_INVALID"
    ENCODING_DETECTION_FAILED = "ENCODING_DETECTION_FAILED"
    
    # Tamaño
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_EMPTY = "FILE_EMPTY"


# =========================================================
# DATACLASS: RESULTADO DE VALIDACIÓN
# =========================================================

@dataclass
class PreIngestionValidationResult:
    """
    Resultado de la validación PRE-ingesta.
    
    Si is_valid=False → el documento NO debe procesarse.
    Contrato OBLIGATORIO según FASE 3.
    """
    is_valid: bool
    reject_code: Optional[str]  # PreIngestionRejectCode.value o None
    details: dict  # Detalles estructurados del rechazo/validación
    validator_version: str
    metrics: dict  # Métricas obligatorias: text_len, file_size_mb, pages_estimated, noise_ratio


# =========================================================
# CHECK 1: FORMATO SOPORTADO
# =========================================================

def check_format_supported(file_path: Path) -> tuple[bool, Optional[PreIngestionRejectCode], str]:
    """
    Verifica que el formato del archivo esté en la WHITELIST.
    
    Returns:
        (is_valid, reject_code, message)
    """
    extension = file_path.suffix.lower()
    
    if extension not in SUPPORTED_FORMATS:
        return (
            False,
            PreIngestionRejectCode.FORMAT_UNSUPPORTED,
            f"Formato {extension} no está en la whitelist de formatos soportados: {SUPPORTED_FORMATS}"
        )
    
    return True, None, "Formato soportado"


# =========================================================
# CHECK 2: DOCUMENTO NO ENCRIPTADO (PDF)
# =========================================================

def check_not_encrypted(file_path: Path) -> tuple[bool, Optional[PreIngestionRejectCode], str]:
    """
    Verifica que el documento PDF no esté encriptado o protegido con contraseña.
    
    Returns:
        (is_valid, reject_code, message)
    """
    extension = file_path.suffix.lower()
    
    # Solo aplica a PDFs
    if extension != ".pdf":
        return True, None, "No es PDF, no aplica check de encriptación"
    
    try:
        with open(file_path, "rb") as f:
            pdf_reader = PyPDF2.PdfReader(f)
            
            # Check 1: ¿Está encriptado?
            if pdf_reader.is_encrypted:
                return (
                    False,
                    PreIngestionRejectCode.ENCRYPTION_DETECTED,
                    "PDF está encriptado. No se puede extraer texto sin contraseña."
                )
            
            # Check 2: ¿Requiere contraseña? (algunos PDFs reportan esto sin is_encrypted)
            # Intentar acceder a la primera página para verificar
            try:
                if len(pdf_reader.pages) > 0:
                    _ = pdf_reader.pages[0]
            except Exception as e:
                if "password" in str(e).lower():
                    return (
                        False,
                        PreIngestionRejectCode.PASSWORD_PROTECTED,
                        f"PDF protegido con contraseña: {e}"
                    )
        
        return True, None, "PDF no encriptado"
    
    except Exception as e:
        # Si falla la lectura del PDF, marcar como corrupto
        return (
            False,
            PreIngestionRejectCode.PDF_CORRUPTED,
            f"Error leyendo PDF (posible corrupción): {e}"
        )


# =========================================================
# CHECK 3: TEXTO EXTRAÍDO ≥ 100 CARACTERES
# =========================================================

def check_min_text_length(
    text: str,
    min_length: int = MIN_TEXT_LENGTH_HARD
) -> tuple[bool, Optional[PreIngestionRejectCode], str]:
    """
    Verifica que el texto extraído tenga al menos min_length caracteres.
    
    Returns:
        (is_valid, reject_code, message)
    """
    if not text or len(text.strip()) == 0:
        return (
            False,
            PreIngestionRejectCode.CONTENT_NO_TEXT_EXTRACTED,
            "No se extrajo ningún texto del documento"
        )
    
    text_length = len(text.strip())
    
    if text_length < min_length:
        return (
            False,
            PreIngestionRejectCode.CONTENT_TOO_SHORT,
            f"Texto extraído ({text_length} chars) < mínimo requerido ({min_length} chars)"
        )
    
    return True, None, f"Texto suficiente: {text_length} caracteres"


# =========================================================
# CHECK 4: RATIO TEXTO/RUIDO MÍNIMO
# =========================================================

def check_text_noise_ratio(
    text: str,
    min_ratio: float = MIN_TEXT_NOISE_RATIO
) -> tuple[bool, Optional[PreIngestionRejectCode], str, float]:
    """
    Verifica que el texto no sea mayormente ruido/caracteres extraños.
    
    Ratio = (caracteres alfanuméricos + espacios + puntuación) / total caracteres
    
    Returns:
        (is_valid, reject_code, message, ratio)
    """
    if not text:
        return False, PreIngestionRejectCode.CONTENT_NO_TEXT_EXTRACTED, "Texto vacío", 0.0
    
    total_chars = len(text)
    
    # Contar caracteres válidos (alfanuméricos, espacios, puntuación común)
    valid_chars = sum(
        1 for char in text
        if char.isalnum() or char.isspace() or char in ".,;:!?¿¡-()[]{}\"'/@#$%&*+=<>|\\~`"
    )
    
    ratio = valid_chars / total_chars if total_chars > 0 else 0.0
    
    if ratio < min_ratio:
        return (
            False,
            PreIngestionRejectCode.CONTENT_TOO_NOISY,
            f"Ratio texto/ruido ({ratio:.2%}) < mínimo requerido ({min_ratio:.2%})",
            ratio
        )
    
    return True, None, f"Ratio texto/ruido aceptable: {ratio:.2%}", ratio


# =========================================================
# CHECK 5: NO PDF ESCANEADO SIN OCR
# =========================================================

def check_not_scanned_without_ocr(file_path: Path) -> tuple[bool, Optional[PreIngestionRejectCode], str, Optional[bool]]:
    """
    Detecta si un PDF es escaneado (imagen) sin capa de texto OCR.
    
    Heurística:
    - Si el PDF tiene páginas pero NO tiene texto extraíble → es escaneado sin OCR
    
    Returns:
        (is_valid, reject_code, message, is_scanned)
    """
    extension = file_path.suffix.lower()
    
    # Solo aplica a PDFs
    if extension != ".pdf":
        return True, None, "No es PDF, no aplica check de escaneo", None
    
    try:
        with open(file_path, "rb") as f:
            pdf_reader = PyPDF2.PdfReader(f)
            
            num_pages = len(pdf_reader.pages)
            
            if num_pages == 0:
                return (
                    False,
                    PreIngestionRejectCode.PDF_CORRUPTED,
                    "PDF sin páginas detectadas",
                    None
                )
            
            # Intentar extraer texto de las primeras 3 páginas
            total_text_length = 0
            pages_to_check = min(3, num_pages)
            
            for i in range(pages_to_check):
                try:
                    page = pdf_reader.pages[i]
                    text = page.extract_text() or ""
                    total_text_length += len(text.strip())
                except Exception as e:
                    logger.warning(f"Error extrayendo texto de página {i+1}: {e}")
            
            # Heurística: Si 3 páginas tienen < 50 caracteres total → es escaneado sin OCR
            avg_text_per_page = total_text_length / pages_to_check if pages_to_check > 0 else 0
            
            if avg_text_per_page < 20:  # Menos de 20 caracteres por página en promedio
                return (
                    False,
                    PreIngestionRejectCode.PDF_SCANNED_NO_OCR,
                    f"PDF escaneado sin OCR detectado. Promedio {avg_text_per_page:.1f} chars/página en {pages_to_check} páginas",
                    True
                )
            
            return True, None, f"PDF con texto extraíble: ~{avg_text_per_page:.0f} chars/página", False
    
    except Exception as e:
        return (
            False,
            PreIngestionRejectCode.PDF_CORRUPTED,
            f"Error analizando PDF: {e}",
            None
        )


# =========================================================
# CHECK 6: ENCODING VÁLIDO (TXT)
# =========================================================

def check_encoding_valid(file_path: Path) -> tuple[bool, Optional[PreIngestionRejectCode], str, Optional[str]]:
    """
    Detecta el encoding de archivos de texto y verifica que sea válido.
    
    Solo aplica a .txt (otros formatos tienen encoding implícito).
    
    Returns:
        (is_valid, reject_code, message, detected_encoding)
    """
    extension = file_path.suffix.lower()
    
    # Solo aplica a .txt
    if extension != ".txt":
        return True, None, "No es TXT, no aplica check de encoding", None
    
    try:
        # Leer primeros 10KB para detección de encoding
        with open(file_path, "rb") as f:
            raw_data = f.read(10240)
        
        if not raw_data:
            return (
                False,
                PreIngestionRejectCode.FILE_EMPTY,
                "Archivo TXT vacío",
                None
            )
        
        # Detectar encoding con chardet
        detection_result = chardet.detect(raw_data)
        detected_encoding = detection_result.get("encoding")
        confidence = detection_result.get("confidence", 0.0)
        
        if not detected_encoding:
            return (
                False,
                PreIngestionRejectCode.ENCODING_DETECTION_FAILED,
                "No se pudo detectar el encoding del archivo TXT",
                None
            )
        
        # Normalizar encoding
        detected_encoding_normalized = detected_encoding.lower().replace("-", "").replace("_", "")
        
        # Verificar si está en la lista de encodings válidos
        is_valid_encoding = any(
            valid_enc.lower().replace("-", "").replace("_", "") in detected_encoding_normalized
            or detected_encoding_normalized in valid_enc.lower().replace("-", "").replace("_", "")
            for valid_enc in VALID_TEXT_ENCODINGS
        )
        
        if not is_valid_encoding:
            return (
                False,
                PreIngestionRejectCode.ENCODING_INVALID,
                f"Encoding detectado ({detected_encoding}, confianza {confidence:.2%}) no está en la lista de encodings válidos",
                detected_encoding
            )
        
        # Verificar que se puede decodificar correctamente
        try:
            raw_data.decode(detected_encoding)
        except Exception as decode_error:
            return (
                False,
                PreIngestionRejectCode.ENCODING_INVALID,
                f"Error decodificando con encoding detectado ({detected_encoding}): {decode_error}",
                detected_encoding
            )
        
        return True, None, f"Encoding válido detectado: {detected_encoding} (confianza {confidence:.2%})", detected_encoding
    
    except Exception as e:
        return (
            False,
            PreIngestionRejectCode.ENCODING_DETECTION_FAILED,
            f"Error detectando encoding: {e}",
            None
        )


# =========================================================
# CHECK 7: TAMAÑO DE ARCHIVO
# =========================================================

def check_file_size(file_path: Path, max_size_mb: int = MAX_FILE_SIZE_MB) -> tuple[bool, Optional[PreIngestionRejectCode], str]:
    """
    Verifica que el archivo no sea ni vacío ni excesivamente grande.
    
    Returns:
        (is_valid, reject_code, message)
    """
    file_size_bytes = file_path.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
    
    if file_size_bytes == 0:
        return (
            False,
            PreIngestionRejectCode.FILE_EMPTY,
            "Archivo vacío (0 bytes)"
        )
    
    if file_size_mb > max_size_mb:
        return (
            False,
            PreIngestionRejectCode.FILE_TOO_LARGE,
            f"Archivo demasiado grande ({file_size_mb:.2f} MB) > límite ({max_size_mb} MB)"
        )
    
    return True, None, f"Tamaño de archivo OK: {file_size_mb:.2f} MB"


# =========================================================
# FUNCIÓN PRINCIPAL: VALIDACIÓN PRE-INGESTA COMPLETA
# =========================================================

def validate_document_pre_ingestion(
    file_path: Path,
    extracted_text: Optional[str] = None,
) -> PreIngestionValidationResult:
    """
    Ejecuta TODOS los checks de validación PRE-ingesta.
    
    Si CUALQUIER check falla → el documento es RECHAZADO (FAIL HARD).
    
    Args:
        file_path: Ruta del archivo a validar
        extracted_text: Texto extraído (opcional, si ya se extrajo)
        
    Returns:
        PreIngestionValidationResult con estado y detalles de rechazo
    """
    filename = file_path.name
    file_size_bytes = file_path.stat().st_size if file_path.exists() else 0
    file_format = file_path.suffix.lower()
    
    # Inicializar detalles y métricas
    details: dict = {
        "filename": filename,
        "file_format": file_format,
        "timestamp": datetime.now().isoformat(),
    }
    
    metrics: dict = {
        "file_size_mb": file_size_bytes / (1024 * 1024),
        "text_len": 0,
        "pages_estimated": 0,
        "noise_ratio": 0.0,
    }
    
    logger.info(f"[PRE-INGESTION] Iniciando validación DURA para: {filename}")
    
    # ========================================
    # CHECK 1: FORMATO SOPORTADO
    # ========================================
    is_valid, reject_code, message = check_format_supported(file_path)
    if not is_valid:
        logger.error(f"[PRE-INGESTION] ❌ {reject_code.value}: {message}")
        details["reject_reason"] = message
        details["reject_code"] = reject_code.value
        return PreIngestionValidationResult(
            is_valid=False,
            reject_code=reject_code.value,
            details=details,
            validator_version=VALIDATOR_VERSION,
            metrics=metrics,
        )
    
    logger.info(f"[PRE-INGESTION] ✓ Check 1: {message}")
    
    # ========================================
    # CHECK 2: TAMAÑO DE ARCHIVO
    # ========================================
    is_valid, reject_code, message = check_file_size(file_path)
    if not is_valid:
        logger.error(f"[PRE-INGESTION] ❌ {reject_code.value}: {message}")
        details["reject_reason"] = message
        details["reject_code"] = reject_code.value
        return PreIngestionValidationResult(
            is_valid=False,
            reject_code=reject_code.value,
            details=details,
            validator_version=VALIDATOR_VERSION,
            metrics=metrics,
        )
    
    logger.info(f"[PRE-INGESTION] ✓ Check 2: {message}")
    
    # ========================================
    # CHECK 3: NO ENCRIPTADO (PDF)
    # ========================================
    is_valid, reject_code, message = check_not_encrypted(file_path)
    if not is_valid:
        logger.error(f"[PRE-INGESTION] ❌ {reject_code.value}: {message}")
        details["reject_reason"] = message
        details["reject_code"] = reject_code.value
        return PreIngestionValidationResult(
            is_valid=False,
            reject_code=reject_code.value,
            details=details,
            validator_version=VALIDATOR_VERSION,
            metrics=metrics,
        )
    
    logger.info(f"[PRE-INGESTION] ✓ Check 3: {message}")
    
    # ========================================
    # CHECK 4: NO PDF ESCANEADO SIN OCR
    # ========================================
    is_valid, reject_code, message, is_scanned = check_not_scanned_without_ocr(file_path)
    if not is_valid:
        logger.error(f"[PRE-INGESTION] ❌ {reject_code.value}: {message}")
        details["reject_reason"] = message
        details["reject_code"] = reject_code.value
        if is_scanned is not None:
            details["is_pdf_scanned"] = is_scanned
        return PreIngestionValidationResult(
            is_valid=False,
            reject_code=reject_code.value,
            details=details,
            validator_version=VALIDATOR_VERSION,
            metrics=metrics,
        )
    
    logger.info(f"[PRE-INGESTION] ✓ Check 4: {message}")
    if file_format == ".pdf" and is_scanned is not None:
        details["is_pdf_scanned"] = is_scanned
    
    # ========================================
    # CHECK 5: ENCODING VÁLIDO (TXT)
    # ========================================
    is_valid, reject_code, message, detected_encoding = check_encoding_valid(file_path)
    if not is_valid:
        logger.error(f"[PRE-INGESTION] ❌ {reject_code.value}: {message}")
        details["reject_reason"] = message
        details["reject_code"] = reject_code.value
        if detected_encoding:
            details["detected_encoding"] = detected_encoding
        return PreIngestionValidationResult(
            is_valid=False,
            reject_code=reject_code.value,
            details=details,
            validator_version=VALIDATOR_VERSION,
            metrics=metrics,
        )
    
    logger.info(f"[PRE-INGESTION] ✓ Check 5: {message}")
    if detected_encoding:
        details["detected_encoding"] = detected_encoding
    
    # ========================================
    # CHECKS QUE REQUIEREN TEXTO EXTRAÍDO
    # ========================================
    if extracted_text is not None:
        text_len = len(extracted_text.strip())
        metrics["text_len"] = text_len
        
        # CHECK 6: LONGITUD MÍNIMA
        is_valid, reject_code, message = check_min_text_length(extracted_text)
        if not is_valid:
            logger.error(f"[PRE-INGESTION] ❌ {reject_code.value}: {message}")
            details["reject_reason"] = message
            details["reject_code"] = reject_code.value
            return PreIngestionValidationResult(
                is_valid=False,
                reject_code=reject_code.value,
                details=details,
                validator_version=VALIDATOR_VERSION,
                metrics=metrics,
            )
        
        logger.info(f"[PRE-INGESTION] ✓ Check 6: {message}")
        
        # CHECK 7: RATIO TEXTO/RUIDO
        is_valid, reject_code, message, ratio = check_text_noise_ratio(extracted_text)
        metrics["noise_ratio"] = ratio
        if not is_valid:
            logger.error(f"[PRE-INGESTION] ❌ {reject_code.value}: {message}")
            details["reject_reason"] = message
            details["reject_code"] = reject_code.value
            return PreIngestionValidationResult(
                is_valid=False,
                reject_code=reject_code.value,
                details=details,
                validator_version=VALIDATOR_VERSION,
                metrics=metrics,
            )
        
        logger.info(f"[PRE-INGESTION] ✓ Check 7: {message}")
    
    # ========================================
    # ✅ TODOS LOS CHECKS PASARON
    # ========================================
    logger.info(f"[PRE-INGESTION] ✅ Documento VÁLIDO: {filename}")
    
    details["validation_status"] = "passed"
    details["message"] = "Documento válido - todos los checks pasaron"
    
    return PreIngestionValidationResult(
        is_valid=True,
        reject_code=None,
        details=details,
        validator_version=VALIDATOR_VERSION,
        metrics=metrics,
    )


# =========================================================
# LOGGING ESTRUCTURADO
# =========================================================

def log_pre_ingestion_validation(
    case_id: str,
    result: PreIngestionValidationResult,
) -> None:
    """
    Logging estructurado obligatorio para validación PRE-ingesta.
    Usa SOLO campos del contrato: is_valid, reject_code, details, validator_version, metrics.
    """
    logger.info("=" * 80)
    logger.info(f"[PRE-INGESTION VALIDATION] Resultado")
    logger.info(f"  Validator Version: {result.validator_version}")
    logger.info(f"  Case ID: {case_id}")
    logger.info(f"  Status: {'✅ VALID' if result.is_valid else '❌ REJECTED'}")
    
    if not result.is_valid:
        logger.error(f"  Reject Code: {result.reject_code}")
        logger.error(f"  Reject Reason: {result.details.get('reject_reason', 'N/A')}")
    
    # Métricas
    logger.info(f"  Metrics:")
    logger.info(f"    - File Size: {result.metrics.get('file_size_mb', 0):.2f} MB")
    logger.info(f"    - Text Length: {result.metrics.get('text_len', 0)} chars")
    logger.info(f"    - Noise Ratio: {result.metrics.get('noise_ratio', 0.0):.2%}")
    logger.info(f"    - Pages (est.): {result.metrics.get('pages_estimated', 0)}")
    
    # Detalles (solo claves existentes)
    if result.details:
        logger.info(f"  Details: {len(result.details)} entries")
        for key in ["filename", "file_format", "timestamp", "detected_encoding", "is_pdf_scanned"]:
            if key in result.details:
                logger.info(f"    - {key}: {result.details[key]}")
    
    logger.info("=" * 80)

