"""
Servicio para ingerir carpetas completas de documentos.
Soporta PDF, DOCX, TXT, CSV, XLSX.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Tuple

from sqlalchemy.orm import Session

from app.core.variables import DATA
from app.models.document import Document
from app.services.ingesta import ingerir_archivo


# Formatos soportados
SUPPORTED_EXTENSIONS = {
    ".pdf", ".txt", ".docx", ".doc",
    ".csv", ".xls", ".xlsx"
}

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
    Intenta inferir el tipo de documento desde el nombre del archivo.
    Usa reglas heurísticas (palabras clave, patrones, etc.).
    Retorna 'contrato' como default si no se puede inferir.
    
    NOTA: Esta función es mejorable en el futuro con:
    - Un clasificador ML ligero (ej: scikit-learn)
    - Reglas más sofisticadas
    - Análisis del contenido del documento
    
    Ejemplos que funcionan bien:
    - "contrato_servicio.pdf" → "contrato"
    - "balance_final_v3_ok.docx" → "balance"
    - "email_re_abogado_urgente.pdf" → "email_direccion"
    """
    import re
    filename_lower = filename.lower()
    
    # Remover extensiones y números de versión comunes para mejor matching
    # Ej: "balance_final_v3_ok.docx" → "balance_final_ok"
    cleaned = re.sub(r'_v\d+|_\d+$|\.(pdf|docx?|txt|xlsx?|csv)$', '', filename_lower)
    
    # PATRONES MÁS ESPECÍFICOS PRIMERO (mayor prioridad)
    
    # Extractos bancarios (muy específico)
    if any(pattern in cleaned for pattern in ["extracto", "extract", "movimiento", "movimiento bancario"]):
        return "extracto_bancario"
    
    # Email (buscar "re:", "fw:", "email", "correo", etc.)
    if any(pattern in cleaned for pattern in ["re:", "fw:", "email", "correo", "mail", "e-mail"]):
        # Intentar inferir tipo de email por contexto
        if any(word in cleaned for word in ["banco", "bank", "bancario"]):
            return "email_banco"
        elif any(word in cleaned for word in ["abogado", "legal", "juridico"]):
            return "email_direccion"  # o podrías tener "email_legal" en el futuro
        else:
            return "email_direccion"
    
    # Balances (balance, balanza, estado financiero)
    if any(pattern in cleaned for pattern in ["balance", "balanza", "estado financiero", "estado_financiero"]):
        return "balance"
    
    # PYG (cuenta de pérdidas y ganancias)
    if any(pattern in cleaned for pattern in ["pyg", "perdidas", "ganancias", "cuenta resultado"]):
        return "pyg"
    
    # Mayor contable
    if any(pattern in cleaned for pattern in ["mayor", "libro mayor"]):
        return "mayor"
    
    # Sumas y saldos
    if any(pattern in cleaned for pattern in ["sumas", "saldos", "sumas_saldos"]):
        return "sumas_saldos"
    
    # Facturas (mapeadas a contrato ya que factura no está en el constraint)
    # NOTA: Las facturas se consideran contratos/comprobantes de operaciones
    if any(pattern in cleaned for pattern in ["factura", "invoice", "fact", "facturacion"]):
        return "contrato"  # Mapeado a 'contrato' que es un valor válido en el CHECK constraint
    
    # Actas
    if any(pattern in cleaned for pattern in ["acta", "minute", "reunion", "junta"]):
        return "acta"
    
    # Acuerdos societarios
    if any(pattern in cleaned for pattern in ["acuerdo", "acuerdo societario", "resolucion"]):
        return "acuerdo_societario"
    
    # Poderes
    if any(pattern in cleaned for pattern in ["poder", "apoderamiento", "proxy"]):
        return "poder"
    
    # Contratos (más genérico, menor prioridad)
    if any(pattern in cleaned for pattern in ["contrato", "contract", "convenio", "acuerdo"]):
        return "contrato"
    
    # Nóminas
    if any(pattern in cleaned for pattern in ["nomina", "nomina", "nómina", "payroll"]):
        return "nomina"
    
    # Ventas de activos
    if any(pattern in cleaned for pattern in ["venta", "venta activo", "asset sale"]):
        return "venta_activo"
    
    # Préstamos
    if any(pattern in cleaned for pattern in ["prestamo", "prestamo", "préstamo", "loan", "credito", "crédito"]):
        return "prestamo"
    
    # Default: contrato (más común en contextos legales)
    return "contrato"


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
) -> tuple[Optional[Document], List[str]]:
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
    warnings: List[str] = []
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
        if inferred_type == "contrato":
            warnings.append(f"Tipo de documento inferido como 'contrato' (default) para: {filename}")
    
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
    
    # Crear registro en la base de datos
    file_format = EXTENSION_TO_FORMAT.get(extension, extension.lstrip("."))
    
    document = Document(
        case_id=case_id,
        filename=filename,
        doc_type=doc_type,
        source=source or "folder_ingestion",
        date_start=date_start,
        date_end=date_end,
        reliability="original",
        file_format=file_format,
        storage_path=str(storage_path),
    )
    
    try:
        db.add(document)
        db.commit()
        db.refresh(document)
        print(f"✅ [INGESTA] Documento creado: {document.document_id}")
        return document, warnings
    except Exception as e:
        db.rollback()
        warning = f"Error creando documento en BD: {e}"
        print(f"❌ [INGESTA] {warning}")
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
) -> Dict[str, Any]:
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
            f for f in folder_path.rglob("*")
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
    else:
        files = [
            f for f in folder_path.iterdir()
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
    print(f"✅ [INGESTA CARPETA] Completado")
    print(f"   Total archivos: {stats['total_files']}")
    print(f"   Procesados: {stats['processed']}")
    print(f"   Omitidos (ya existían): {stats['skipped']}")
    print(f"   Errores: {stats['errors']}")
    print(f"   Warnings: {len(stats['warnings'])}")
    if stats['warnings']:
        print(f"\n   📋 Warnings encontrados:")
        for warning in stats['warnings'][:10]:  # Mostrar máximo 10
            print(f"      - {warning}")
        if len(stats['warnings']) > 10:
            print(f"      ... y {len(stats['warnings']) - 10} warnings más")
    print("=" * 60)
    
    return stats

