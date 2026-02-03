"""
Servicio para ingerir carpetas completas de documentos.
Soporta PDF, DOCX, TXT, CSV, XLSX.

VALIDACIÓN HARD: Los documentos DEBEN pasar validaciones de calidad de parsing.
Si un documento NO cumple mínimos → NO se guarda en BD, NO entra en chunking.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.variables import DATA
from app.models.document import Document, calculate_file_hash, get_file_size, get_mime_type
from app.services.document_parsing_validation import (
    ParsingStatus,
    calculate_parsing_metrics,
    log_parsing_validation,
    validate_parsing_quality,
)
from app.services.document_pre_ingestion_validation import (
    log_pre_ingestion_validation,
    validate_document_pre_ingestion,
)
from app.services.ingesta import ParsingResult, ingerir_archivo

# Formatos soportados
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".docx", ".csv", ".xls", ".xlsx"}
if os.getenv("PHOENIX_ENABLE_DOC_LEGACY", "").strip() == "1":
    SUPPORTED_EXTENSIONS.add(".doc")

# Mapeo de extensiones a formato interno
EXTENSION_TO_FORMAT = {
    ".pdf": "pdf",
    ".txt": "txt",
    ".docx": "docx",
    ".doc": "doc",  # Mantener .doc separado (best effort, puede fallar)
    ".csv": "csv",
    ".xls": "xls",
    ".xlsx": "xlsx",
}


def _get_default_doc_type(filename: str) -> str:
    """
    Backward-compatible wrapper: inferencia determinista doc_type (abogado-friendly)
    a partir del filename (sin texto).
    """
    try:
        from app.core.doc_types import infer_doc_type

        inferred = infer_doc_type(filename=filename, raw_text_preview=None)
        return inferred.doc_type
    except Exception:
        return "OTRO"


def _save_file_to_storage(
    source_path: Path,
    case_id: str,
    filename: str,
) -> Path:
    """
    Copia el archivo al almacenamiento del sistema.
    Retorna la ruta final donde se guardó el archivo.
    """
    # Crear estructura de carpetas: DATA/cases/{case_id}/documents/
    storage_dir = DATA / "cases" / case_id / "documents"
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Ruta final del archivo
    destination_path = storage_dir / filename

    # Si el archivo ya existe, añadir un sufijo numérico
    counter = 1
    original_destination = destination_path
    while destination_path.exists():
        stem = original_destination.stem
        suffix = original_destination.suffix
        destination_path = storage_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    # Copiar el archivo
    shutil.copy2(source_path, destination_path)

    return destination_path


def ingest_file_from_path(
    db: Session,
    file_path: Path,
    case_id: str,
    doc_type: Optional[str] = None,
    source: Optional[str] = None,
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
) -> tuple[Optional[Document], list[str]]:
    """
    Ingiere un solo archivo desde una ruta del sistema de archivos.

    Parámetros
    ----------
    db : Session
        Sesión de base de datos
    file_path : Path
        Ruta del archivo a ingerir
    case_id : str
        ID del caso al que pertenece el documento
    doc_type : str, optional
        Tipo de documento. Si no se proporciona, se intenta inferir desde el nombre
    source : str, optional
        Origen del documento (ej: "upload", "folder_scan")
    date_start : datetime, optional
        Fecha de inicio del documento
    date_end : datetime, optional
        Fecha de fin del documento

    Retorna
    -------
    Tuple[Optional[Document], List[str]]
        Tupla con (documento creado o None, lista de warnings)
    """
    warnings: list[str] = []
    file_path = Path(file_path)

    # Validar que el archivo existe
    if not file_path.exists():
        warning = f"Archivo no existe: {file_path}"
        print(f"❌ [INGESTA] {warning}")
        return None, [warning]

    # Validar extensión
    extension = file_path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        warning = f"Formato no soportado: {extension}"
        print(f"⚠️  [INGESTA] {warning}")
        return None, [warning]

    filename = file_path.name

    print("--------------------------------------------------")
    print(f"📥 [INGESTA] Procesando archivo: {filename}")

    # Verificar que no existe ya un documento con este filename en este caso
    existing = (
        db.query(Document)
        .filter(
            Document.case_id == case_id,
            Document.filename == filename,
        )
        .first()
    )

    if existing:
        warning = f"Documento ya existe: {filename} (document_id: {existing.document_id})"
        print(f"⚠️  [INGESTA] {warning}")
        return existing, [warning]

    # Inferir doc_type si no se proporcionó
    inferred_type = None
    if not doc_type:
        inferred_type = _get_default_doc_type(filename)
        doc_type = inferred_type
        print(f"ℹ️  [INGESTA] Tipo inferido: {doc_type}")
    else:
        # Si llega un doc_type legacy o fuera de catálogo, degradar a inferencia (no inventar)
        try:
            from app.core.doc_types import DOC_TYPES_SET, infer_doc_type

            if doc_type not in DOC_TYPES_SET:
                inferred_type = infer_doc_type(filename=filename, raw_text_preview=None).doc_type
                warnings.append(
                    f"doc_type '{doc_type}' no válido en catálogo v2; usando inferencia por filename: {inferred_type}"
                )
                doc_type = inferred_type
        except Exception:
            doc_type = "OTRO"

    # Warnings específicos por formato
    if extension == ".doc":
        warnings.append(f"Archivo .doc (legacy) - puede requerir conversión a .docx: {filename}")

    # Usar fechas por defecto si no se proporcionan
    if not date_start:
        date_start = datetime.now().replace(day=1)  # Primer día del mes actual
        warnings.append(f"Fecha de inicio no proporcionada, usando default para: {filename}")
    if not date_end:
        date_end = datetime.now()  # Fecha actual
        warnings.append(f"Fecha de fin no proporcionada, usando default para: {filename}")

    # Guardar el archivo en el almacenamiento del sistema
    try:
        storage_path = _save_file_to_storage(file_path, case_id, filename)
        print(f"✅ [INGESTA] Archivo guardado en: {storage_path}")
    except Exception as e:
        warning = f"Error guardando archivo: {e}"
        print(f"❌ [INGESTA] {warning}")
        return None, [warning]

    # --------------------------------------------------
    # VALIDACIÓN PRE-INGESTA (ENDURECIMIENTO #2: FAIL FAST)
    # --------------------------------------------------
    # ANTES de extraer texto o parsear, validar:
    # - Formato soportado
    # - No encriptado
    # - No PDF escaneado sin OCR
    # - Encoding válido
    # - Tamaño razonable

    logger.info(f"[INGESTA] Iniciando validación PRE-ingesta (FAIL FAST) para {filename}")

    # Ejecutar validación PRE-ingesta (sin texto todavía)
    pre_validation_result = validate_document_pre_ingestion(
        file_path=storage_path,
        extracted_text=None,  # Aún no hemos extraído texto
    )

    # Logging obligatorio
    log_pre_ingestion_validation(
        case_id=case_id,
        result=pre_validation_result,
    )

    # FAIL HARD si la validación PRE-ingesta falla
    if not pre_validation_result.is_valid:
        warning = (
            f"Documento rechazado en validación PRE-ingesta. "
            f"Código: {pre_validation_result.reject_code.value}, "
            f"Motivo: {pre_validation_result.reject_message}"
        )
        logger.error(f"[INGESTA] ❌ {warning}")
        warnings.append(warning)

        # NO continuar con parsing ni crear documento
        return None, warnings

    logger.info(f"[INGESTA] ✅ Validación PRE-ingesta OK para {filename}")

    # --------------------------------------------------
    # VALIDACIÓN HARD DE CALIDAD DE PARSING
    # --------------------------------------------------
    # REGLA 1: La ingesta NO es best-effort
    # El pipeline NO puede continuar con texto parcial, dudoso o vacío

    logger.info(f"[INGESTA] Iniciando validación HARD de parsing para {filename}")

    try:
        # Leer y parsear el archivo
        result = ingerir_archivo(storage_path, filename)

        if result is None:
            warning = "El sistema de ingesta no pudo procesar el archivo"
            logger.error(f"[INGESTA] ❌ {warning}")
            warnings.append(warning)
            return None, warnings

        # Procesar resultado según el tipo
        text = ""
        parsing_result = None

        if isinstance(result, ParsingResult):
            # Archivo de texto (PDF, DOCX, TXT, DOC)
            text = result.texto
            parsing_result = result
        else:
            # DataFrame (CSV/Excel) - convertir a texto

            text = result.to_string()
            logger.info(f"[INGESTA] Archivo CSV/Excel convertido a texto ({len(text)} caracteres)")

            # Crear ParsingResult para CSV/Excel
            parsing_result = ParsingResult(
                texto=text,
                num_paginas=1,
                tipo_documento=EXTENSION_TO_FORMAT.get(extension, "csv"),
            )

    except Exception as e:
        warning = f"Error leyendo/parseando archivo: {e}"
        logger.error(f"[INGESTA] ❌ {warning}")
        warnings.append(warning)
        import traceback

        traceback.print_exc()
        return None, warnings

    # --------------------------------------------------
    # VALIDACIÓN PRE-INGESTA POST-EXTRACCIÓN
    # --------------------------------------------------
    # Ahora que tenemos el texto, ejecutar checks que requieren texto
    pre_validation_with_text = validate_document_pre_ingestion(
        file_path=Path(storage_path),
        extracted_text=text,
    )

    # Logging adicional con texto
    if not pre_validation_with_text.is_valid:
        warning = (
            f"Documento rechazado en validación PRE-ingesta (post-extracción). "
            f"Código: {pre_validation_with_text.reject_code.value}, "
            f"Motivo: {pre_validation_with_text.reject_message}"
        )
        logger.error(f"[INGESTA] ❌ {warning}")
        warnings.append(warning)
        return None, warnings

    logger.info(f"[INGESTA] ✅ Validación PRE-ingesta (con texto) OK para {filename}")

    # Calcular métricas de calidad de extracción
    metrics = calculate_parsing_metrics(
        texto_extraido=text,
        file_path=Path(storage_path),
        tipo_documento=parsing_result.tipo_documento,
        num_paginas_detectadas=parsing_result.num_paginas,
    )

    # Validar calidad usando umbrales HARD
    validation_result = validate_parsing_quality(metrics)

    # Logging técnico obligatorio (REGLA 7)
    log_parsing_validation(
        case_id=case_id,
        doc_id="PENDIENTE",  # Aún no tenemos doc_id
        filename=filename,
        validation_result=validation_result,
    )

    # REGLA 3: Si falla validación → NO crear documento en BD
    if validation_result.is_invalid():
        warning = (
            f"Documento rechazado por validación de parsing. "
            f"Estado: {validation_result.status.value}, "
            f"Motivo: {validation_result.rejection_reason.value if validation_result.rejection_reason else 'UNKNOWN'}"
        )
        logger.error(f"[INGESTA] ❌ {warning}")
        warnings.append(warning)

        # NO crear registro en BD
        # El archivo queda en storage pero sin registro
        return None, warnings

    # ✅ Documento válido → crear registro en BD con métricas
    logger.info(f"[INGESTA] ✅ Documento válido: {filename}")

    file_format = EXTENSION_TO_FORMAT.get(extension, extension.lstrip("."))

    # Cadena de custodia / integridad: campos obligatorios (NOT NULL en DB)
    sha256_hash = calculate_file_hash(Path(storage_path))
    file_size_bytes = get_file_size(Path(storage_path))
    mime_type = get_mime_type(filename)

    # Refinar doc_type con texto (si existe) antes de persistir
    doc_type_confidence = None
    doc_type_source = None
    try:
        from app.core.doc_types import DOC_TYPES_SET, infer_doc_type

        inferred_final = infer_doc_type(
            filename=filename,
            title=None,
            source=source or "folder_ingestion",
            raw_text_preview=text,
        )
        if inferred_final.doc_type in DOC_TYPES_SET:
            doc_type = inferred_final.doc_type
            doc_type_confidence = inferred_final.confidence
            doc_type_source = "inferred"
    except Exception:
        # Mantener doc_type actual (por filename o input) y no bloquear la ingesta
        pass

    document = Document(
        case_id=case_id,
        filename=filename,
        sha256_hash=sha256_hash,
        file_size_bytes=file_size_bytes,
        mime_type=mime_type,
        doc_type=doc_type,
        doc_type_confidence=doc_type_confidence,
        doc_type_source=doc_type_source,
        source=source or "folder_ingestion",
        date_start=date_start,
        date_end=date_end,
        reliability="original",
        file_format=file_format,
        storage_path=str(storage_path),
        # Campos de validación de parsing
        parsing_status=validation_result.status.value,
        parsing_rejection_reason=None,  # Es válido, no hay rechazo
        parsing_metrics=validation_result.metrics.to_dict(),
    )

    try:
        db.add(document)
        db.commit()
        db.refresh(document)
        logger.info(f"[INGESTA] ✅ Documento creado: {document.document_id}")
        return document, warnings
    except Exception as e:
        db.rollback()
        warning = f"Error creando documento en BD: {e}"
        logger.error(f"[INGESTA] ❌ {warning}")
        return None, [warning]


def ingest_folder(
    db: Session,
    folder_path: Path,
    case_id: str,
    doc_type: Optional[str] = None,
    source: Optional[str] = None,
    recursive: bool = True,
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
) -> dict[str, Any]:
    """
    Ingiere todos los archivos soportados de una carpeta.

    Parámetros
    ----------
    db : Session
        Sesión de base de datos
    folder_path : Path
        Ruta de la carpeta a procesar
    case_id : str
        ID del caso al que pertenecen los documentos
    doc_type : str, optional
        Tipo de documento por defecto para todos los archivos
    source : str, optional
        Origen de los documentos
    recursive : bool
        Si True, procesa también subcarpetas
    date_start : datetime, optional
        Fecha de inicio por defecto
    date_end : datetime, optional
        Fecha de fin por defecto

    Retorna
    -------
    dict
        Estadísticas del proceso:
        {
            "total_files": int,
            "processed": int,
            "skipped": int,
            "errors": int,
            "documents": List[Document]
        }
    """
    folder_path = Path(folder_path)

    if not folder_path.exists() or not folder_path.is_dir():
        print(f"❌ [INGESTA CARPETA] La ruta no es una carpeta válida: {folder_path}")
        return {
            "total_files": 0,
            "processed": 0,
            "skipped": 0,
            "errors": 0,
            "documents": [],
        }

    print("=" * 60)
    print(f"📁 [INGESTA CARPETA] Procesando: {folder_path}")
    print(f"📁 [INGESTA CARPETA] case_id: {case_id}")
    print(f"📁 [INGESTA CARPETA] Recursivo: {recursive}")
    print("=" * 60)

    # Encontrar todos los archivos soportados
    if recursive:
        files = [
            f
            for f in folder_path.rglob("*")
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
    else:
        files = [
            f
            for f in folder_path.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

    print(f"📊 [INGESTA CARPETA] Archivos encontrados: {len(files)}")

    stats = {
        "total_files": len(files),
        "processed": 0,
        "skipped": 0,
        "errors": 0,
        "documents": [],
        "warnings": [],  # ✅ Lista de todos los warnings acumulados
        "validation_results": [],  # ✅ Lista de resultados de validación (para REGLA 6)
    }

    # Procesar cada archivo
    for file_path in files:
        document, file_warnings = ingest_file_from_path(
            db=db,
            file_path=file_path,
            case_id=case_id,
            doc_type=doc_type,
            source=source,
            date_start=date_start,
            date_end=date_end,
        )

        # Acumular warnings
        stats["warnings"].extend(file_warnings)

        if document:
            stats["processed"] += 1
            stats["documents"].append(document)
        elif document is None:
            # Si retorna None, puede ser porque ya existe (skipped) o error
            # Verificamos si existe
            existing = (
                db.query(Document)
                .filter(
                    Document.case_id == case_id,
                    Document.filename == file_path.name,
                )
                .first()
            )
            if existing:
                stats["skipped"] += 1
            else:
                stats["errors"] += 1

    print("=" * 60)
    print("✅ [INGESTA CARPETA] Completado")
    print(f"   Total archivos: {stats['total_files']}")
    print(f"   Procesados: {stats['processed']}")
    print(f"   Omitidos (ya existían): {stats['skipped']}")
    print(f"   Errores: {stats['errors']}")
    print(f"   Warnings: {len(stats['warnings'])}")
    if stats["warnings"]:
        print("\n   📋 Warnings encontrados:")
        for warning in stats["warnings"][:10]:  # Mostrar máximo 10
            print(f"      - {warning}")
        if len(stats["warnings"]) > 10:
            print(f"      ... y {len(stats['warnings']) - 10} warnings más")
    print("=" * 60)

    # --------------------------------------------------
    # REGLA 6: Verificar que al menos un documento es válido
    # --------------------------------------------------
    if stats["processed"] > 0:
        # Contar documentos PARSED_OK vs PARSED_INVALID
        valid_docs = [
            d for d in stats["documents"] if d.parsing_status == ParsingStatus.PARSED_OK.value
        ]

        logger.info(
            f"[INGESTA CARPETA] case_id={case_id}: "
            f"Documentos válidos (PARSED_OK): {len(valid_docs)}/{stats['processed']}"
        )

        # Si ningún documento es válido → ABORTAR caso completo
        if len(valid_docs) == 0 and stats["processed"] > 0:
            error_msg = (
                f"❌ INGESTA ABORTADA: case_id={case_id}. "
                f"TODOS los documentos procesados ({stats['processed']}) resultaron PARSED_INVALID. "
                f"No se puede continuar con un caso sin documentos válidos."
            )
            logger.error(f"[INGESTA CARPETA] {error_msg}")
            raise RuntimeError(error_msg)

    return stats
