"""
Validaciones HARD de calidad de ingesta.

PRINCIPIO: La ingesta NO es best-effort.
Si un documento NO cumple mínimos objetivos → ABORTAR pipeline para ese documento.

NO chunking, NO embeddings, NO inclusión en vectorstore.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from app.core.logger import logger

# =========================================================
# ENUMS: ESTADOS Y MOTIVOS DE RECHAZO
# =========================================================


class ParsingStatus(str, Enum):
    """Estado final de parsing de un documento."""

    PARSED_OK = "PARSED_OK"
    PARSED_INVALID = "PARSED_INVALID"


class RejectionReason(str, Enum):
    """
    Motivos normalizados de rechazo (enum cerrado).
    Prohibido usar mensajes genéricos o textos libres.
    """

    NO_TEXT_EXTRACTED = "NO_TEXT_EXTRACTED"
    TOO_FEW_CHARACTERS = "TOO_FEW_CHARACTERS"
    TOO_FEW_PAGES = "TOO_FEW_PAGES"
    LOW_TEXT_DENSITY = "LOW_TEXT_DENSITY"
    LOW_EXTRACTION_RATIO = "LOW_EXTRACTION_RATIO"
    PARSER_ERROR = "PARSER_ERROR"


# =========================================================
# UMBRALES CONFIGURABLES (valores conservadores)
# =========================================================

# Umbrales mínimos por defecto
MIN_NUM_PAGES_DETECTED = 1  # Al menos 1 página detectada
MIN_NUM_PAGES_WITH_TEXT = 1  # Al menos 1 página con texto
MIN_NUM_CHARACTERS = 500  # Mínimo 500 caracteres extraídos
MIN_TEXT_DENSITY = 300  # Mínimo 300 caracteres por página con texto
MIN_EXTRACTION_RATIO = 0.005  # Mínimo 0.5% del tamaño en bytes


# =========================================================
# DATACLASSES: MÉTRICAS Y RESULTADO
# =========================================================


@dataclass
class ParsingMetrics:
    """
    Métricas objetivas de calidad de extracción.

    REGLA 2: Estas métricas son OBLIGATORIAS para cada documento.
    """

    # Métricas básicas
    tamaño_original_bytes: int
    tipo_documento: str  # pdf, docx, txt, etc.
    numero_paginas_detectadas: int
    numero_paginas_con_texto: int
    numero_caracteres_extraidos: int
    numero_lineas_no_vacias: int

    # Métricas derivadas
    densidad_texto: float  # caracteres / página con texto
    ratio_extraccion_bytes: float  # caracteres / bytes

    def to_dict(self) -> dict[str, Any]:
        """Convierte métricas a diccionario."""
        return {
            "tamaño_original_bytes": self.tamaño_original_bytes,
            "tipo_documento": self.tipo_documento,
            "numero_paginas_detectadas": self.numero_paginas_detectadas,
            "numero_paginas_con_texto": self.numero_paginas_con_texto,
            "numero_caracteres_extraidos": self.numero_caracteres_extraidos,
            "numero_lineas_no_vacias": self.numero_lineas_no_vacias,
            "densidad_texto": round(self.densidad_texto, 2),
            "ratio_extraccion_bytes": round(self.ratio_extraccion_bytes, 6),
        }


@dataclass
class ParsingValidationResult:
    """
    Resultado de la validación de parsing.

    REGLA 4: Estado explícito y final del documento.
    """

    status: ParsingStatus
    metrics: ParsingMetrics
    rejection_reason: Optional[RejectionReason] = None

    def is_valid(self) -> bool:
        """Retorna True si el documento es válido."""
        return self.status == ParsingStatus.PARSED_OK

    def is_invalid(self) -> bool:
        """Retorna True si el documento es inválido."""
        return self.status == ParsingStatus.PARSED_INVALID


# =========================================================
# CÁLCULO DE MÉTRICAS
# =========================================================


def calculate_parsing_metrics(
    texto_extraido: str,
    file_path: Path,
    tipo_documento: str,
    num_paginas_detectadas: int = 1,
) -> ParsingMetrics:
    """
    Calcula métricas objetivas de calidad de extracción.

    REGLA 2: Métricas obligatorias por documento.

    Args:
        texto_extraido: Texto extraído del documento
        file_path: Ruta del archivo original
        tipo_documento: Tipo de documento (pdf, docx, txt, etc.)
        num_paginas_detectadas: Número de páginas detectadas (default=1)

    Returns:
        ParsingMetrics con todas las métricas calculadas
    """
    # Tamaño original del archivo
    tamaño_original_bytes = file_path.stat().st_size if file_path.exists() else 0

    # Número de caracteres extraídos
    numero_caracteres_extraidos = len(texto_extraido) if texto_extraido else 0

    # Número de líneas no vacías
    lineas = texto_extraido.split("\n") if texto_extraido else []
    numero_lineas_no_vacias = sum(1 for linea in lineas if linea.strip())

    # Número de páginas con texto (heurística: al menos 50 caracteres por página)
    # Para docs sin concepto de página (txt, docx sin paginación), considerar 1 página
    if tipo_documento == "pdf":
        numero_paginas_con_texto = num_paginas_detectadas
    else:
        # Para otros formatos, si hay texto, considerar al menos 1 página
        numero_paginas_con_texto = 1 if numero_caracteres_extraidos > 0 else 0

    # Densidad de texto (caracteres por página con texto)
    if numero_paginas_con_texto > 0:
        densidad_texto = numero_caracteres_extraidos / numero_paginas_con_texto
    else:
        densidad_texto = 0.0

    # Ratio de extracción (caracteres / bytes)
    if tamaño_original_bytes > 0:
        ratio_extraccion_bytes = numero_caracteres_extraidos / tamaño_original_bytes
    else:
        ratio_extraccion_bytes = 0.0

    return ParsingMetrics(
        tamaño_original_bytes=tamaño_original_bytes,
        tipo_documento=tipo_documento,
        numero_paginas_detectadas=num_paginas_detectadas,
        numero_paginas_con_texto=numero_paginas_con_texto,
        numero_caracteres_extraidos=numero_caracteres_extraidos,
        numero_lineas_no_vacias=numero_lineas_no_vacias,
        densidad_texto=densidad_texto,
        ratio_extraccion_bytes=ratio_extraccion_bytes,
    )


# =========================================================
# VALIDACIONES HARD (BLOQUEANTES)
# =========================================================


def validate_parsing_quality(
    metrics: ParsingMetrics,
    *,
    min_num_pages_detected: int = MIN_NUM_PAGES_DETECTED,
    min_num_pages_with_text: int = MIN_NUM_PAGES_WITH_TEXT,
    min_num_characters: int = MIN_NUM_CHARACTERS,
    min_text_density: float = MIN_TEXT_DENSITY,
    min_extraction_ratio: float = MIN_EXTRACTION_RATIO,
) -> ParsingValidationResult:
    """
    Valida la calidad del parsing usando umbrales HARD.

    REGLA 3: Umbrales mínimos (hard validation).
    El documento DEBE cumplir TODOS los mínimos.
    Si cualquiera falla → PARSED_INVALID + motivo específico.

    Args:
        metrics: Métricas calculadas del parsing
        min_num_pages_detected: Mínimo de páginas detectadas
        min_num_pages_with_text: Mínimo de páginas con texto
        min_num_characters: Mínimo de caracteres extraídos
        min_text_density: Mínima densidad de texto (caracteres/página)
        min_extraction_ratio: Mínimo ratio de extracción (caracteres/bytes)

    Returns:
        ParsingValidationResult con estado y motivo de rechazo si aplica
    """
    # VALIDACIÓN 1: Texto extraído no vacío
    if metrics.numero_caracteres_extraidos == 0:
        logger.warning(
            f"[VALIDACIÓN PARSING] ❌ Rechazo: NO_TEXT_EXTRACTED. "
            f"Caracteres extraídos: {metrics.numero_caracteres_extraidos}"
        )
        return ParsingValidationResult(
            status=ParsingStatus.PARSED_INVALID,
            metrics=metrics,
            rejection_reason=RejectionReason.NO_TEXT_EXTRACTED,
        )

    # VALIDACIÓN 2: Páginas detectadas
    if metrics.numero_paginas_detectadas < min_num_pages_detected:
        logger.warning(
            f"[VALIDACIÓN PARSING] ❌ Rechazo: TOO_FEW_PAGES. "
            f"Páginas detectadas: {metrics.numero_paginas_detectadas} < {min_num_pages_detected}"
        )
        return ParsingValidationResult(
            status=ParsingStatus.PARSED_INVALID,
            metrics=metrics,
            rejection_reason=RejectionReason.TOO_FEW_PAGES,
        )

    # VALIDACIÓN 3: Páginas con texto
    if metrics.numero_paginas_con_texto < min_num_pages_with_text:
        logger.warning(
            f"[VALIDACIÓN PARSING] ❌ Rechazo: TOO_FEW_PAGES. "
            f"Páginas con texto: {metrics.numero_paginas_con_texto} < {min_num_pages_with_text}"
        )
        return ParsingValidationResult(
            status=ParsingStatus.PARSED_INVALID,
            metrics=metrics,
            rejection_reason=RejectionReason.TOO_FEW_PAGES,
        )

    # VALIDACIÓN 4: Número mínimo de caracteres
    if metrics.numero_caracteres_extraidos < min_num_characters:
        logger.warning(
            f"[VALIDACIÓN PARSING] ❌ Rechazo: TOO_FEW_CHARACTERS. "
            f"Caracteres: {metrics.numero_caracteres_extraidos} < {min_num_characters}"
        )
        return ParsingValidationResult(
            status=ParsingStatus.PARSED_INVALID,
            metrics=metrics,
            rejection_reason=RejectionReason.TOO_FEW_CHARACTERS,
        )

    # VALIDACIÓN 5: Densidad de texto
    if metrics.densidad_texto < min_text_density:
        logger.warning(
            f"[VALIDACIÓN PARSING] ❌ Rechazo: LOW_TEXT_DENSITY. "
            f"Densidad: {metrics.densidad_texto:.2f} < {min_text_density}"
        )
        return ParsingValidationResult(
            status=ParsingStatus.PARSED_INVALID,
            metrics=metrics,
            rejection_reason=RejectionReason.LOW_TEXT_DENSITY,
        )

    # VALIDACIÓN 6: Ratio de extracción
    if metrics.ratio_extraccion_bytes < min_extraction_ratio:
        logger.warning(
            f"[VALIDACIÓN PARSING] ❌ Rechazo: LOW_EXTRACTION_RATIO. "
            f"Ratio: {metrics.ratio_extraccion_bytes:.6f} < {min_extraction_ratio}"
        )
        return ParsingValidationResult(
            status=ParsingStatus.PARSED_INVALID,
            metrics=metrics,
            rejection_reason=RejectionReason.LOW_EXTRACTION_RATIO,
        )

    # ✅ TODAS las validaciones pasaron
    logger.info(
        f"[VALIDACIÓN PARSING] ✅ PARSED_OK. "
        f"Caracteres: {metrics.numero_caracteres_extraidos}, "
        f"Densidad: {metrics.densidad_texto:.2f}, "
        f"Ratio: {metrics.ratio_extraccion_bytes:.6f}"
    )

    return ParsingValidationResult(
        status=ParsingStatus.PARSED_OK,
        metrics=metrics,
        rejection_reason=None,
    )


# =========================================================
# LOGGING TÉCNICO OBLIGATORIO
# =========================================================


def log_parsing_validation(
    case_id: str,
    doc_id: str,
    filename: str,
    validation_result: ParsingValidationResult,
) -> None:
    """
    Logging técnico obligatorio por cada documento procesado.

    REGLA 7: Loggear SIEMPRE:
    - case_id, doc_id, filename
    - tipo_documento
    - métricas calculadas
    - estado final (PARSED_OK / PARSED_INVALID)
    - motivo exacto del rechazo (si aplica)
    """
    metrics = validation_result.metrics

    logger.info("=" * 80)
    logger.info("[VALIDACIÓN PARSING] Documento procesado")
    logger.info(f"  case_id: {case_id}")
    logger.info(f"  doc_id: {doc_id}")
    logger.info(f"  filename: {filename}")
    logger.info(f"  tipo_documento: {metrics.tipo_documento}")
    logger.info("  MÉTRICAS:")
    logger.info(f"    - tamaño_original_bytes: {metrics.tamaño_original_bytes}")
    logger.info(f"    - numero_paginas_detectadas: {metrics.numero_paginas_detectadas}")
    logger.info(f"    - numero_paginas_con_texto: {metrics.numero_paginas_con_texto}")
    logger.info(f"    - numero_caracteres_extraidos: {metrics.numero_caracteres_extraidos}")
    logger.info(f"    - numero_lineas_no_vacias: {metrics.numero_lineas_no_vacias}")
    logger.info(f"    - densidad_texto: {metrics.densidad_texto:.2f} caracteres/página")
    logger.info(f"    - ratio_extraccion_bytes: {metrics.ratio_extraccion_bytes:.6f}")
    logger.info(f"  ESTADO: {validation_result.status.value}")

    if validation_result.is_invalid():
        logger.error(f"  MOTIVO RECHAZO: {validation_result.rejection_reason.value}")

    logger.info("=" * 80)


# =========================================================
# VALIDACIÓN DE CASO COMPLETO
# =========================================================


def check_case_has_valid_documents(
    case_id: str,
    validation_results: list[ParsingValidationResult],
) -> None:
    """
    Verifica que el caso tenga al menos un documento válido.

    REGLA 6: Si TODOS los documentos resultan PARSED_INVALID:
    → abortar la ingesta del caso completo
    → lanzar excepción clara, explícita y bloqueante

    Args:
        case_id: ID del caso
        validation_results: Lista de resultados de validación

    Raises:
        RuntimeError: Si todos los documentos son inválidos
    """
    if not validation_results:
        logger.warning(f"[VALIDACIÓN CASO] case_id={case_id}: No hay documentos para validar")
        return

    valid_count = sum(1 for r in validation_results if r.is_valid())
    invalid_count = sum(1 for r in validation_results if r.is_invalid())

    logger.info(
        f"[VALIDACIÓN CASO] case_id={case_id}: "
        f"Válidos={valid_count}, Inválidos={invalid_count}, Total={len(validation_results)}"
    )

    if valid_count == 0:
        # TODOS los documentos son inválidos → ABORTAR caso completo
        motivos = {}
        for r in validation_results:
            motivo = r.rejection_reason.value if r.rejection_reason else "UNKNOWN"
            motivos[motivo] = motivos.get(motivo, 0) + 1

        error_msg = (
            f"❌ INGESTA ABORTADA: case_id={case_id}. "
            f"TODOS los documentos ({len(validation_results)}) resultaron PARSED_INVALID. "
            f"Motivos: {motivos}"
        )

        logger.error(f"[VALIDACIÓN CASO] {error_msg}")
        raise RuntimeError(error_msg)

    logger.info(
        f"[VALIDACIÓN CASO] ✅ case_id={case_id}: Al menos {valid_count} documento(s) válido(s)"
    )
