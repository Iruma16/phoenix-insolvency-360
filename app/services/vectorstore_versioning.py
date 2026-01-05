"""
Sistema de versionado estricto del vectorstore para casos.

REGLAS CRÍTICAS:
- NUNCA sobrescribir un vectorstore existente
- Cada ingesta crea una versión nueva: v_YYYYMMDD_HHMMSS
- Validaciones de integridad BLOQUEANTES antes de activar
- Puntero ACTIVE solo apunta a versiones válidas (status=READY)
- Control estricto de case_id en todos los niveles
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from app.core.variables import CASES_VECTORSTORE_BASE, EMBEDDING_MODEL
from app.core.logger import logger


# =========================================================
# CONSTANTES
# =========================================================

VERSION_PREFIX = "v_"
ACTIVE_POINTER = "ACTIVE"
MANIFEST_FILENAME = "manifest.json"
STATUS_FILENAME = "status.json"
INDEX_DIRNAME = "index"

VALID_STATUSES = ["BUILDING", "READY", "FAILED"]


# =========================================================
# DATACLASSES
# =========================================================

@dataclass
class VersionInfo:
    """Información de una versión del vectorstore."""
    case_id: str
    version: str
    status: str  # BUILDING | READY | FAILED
    path: Path
    created_at: datetime
    
    def is_ready(self) -> bool:
        return self.status == "READY"
    
    def is_failed(self) -> bool:
        return self.status == "FAILED"


@dataclass
class ManifestData:
    """Datos del manifest técnico de una versión."""
    case_id: str
    version: str
    embedding_model: str
    embedding_dim: int
    chunking: Dict[str, Any]
    documents: List[Dict[str, Any]]  # [{doc_id, filename, sha256, num_chunks}, ...]
    total_chunks: int
    created_at: str  # ISO8601
    generator: str = "phoenix-ingestion"


# =========================================================
# UTILIDADES DE RUTA
# =========================================================

def _get_case_vectorstore_root(case_id: str) -> Path:
    """
    Retorna la ruta raíz donde se almacenan todas las versiones de un caso.
    
    Estructura:
    clients_data/_vectorstore/cases/{case_id}/
    """
    return CASES_VECTORSTORE_BASE.parent / "_vectorstore" / "cases" / case_id


def _get_version_path(case_id: str, version: str) -> Path:
    """Retorna la ruta de una versión específica."""
    return _get_case_vectorstore_root(case_id) / version


def _get_active_pointer_path(case_id: str) -> Path:
    """Retorna la ruta del puntero ACTIVE."""
    return _get_case_vectorstore_root(case_id) / ACTIVE_POINTER


def _get_manifest_path(case_id: str, version: str) -> Path:
    """Retorna la ruta del manifest.json de una versión."""
    return _get_version_path(case_id, version) / MANIFEST_FILENAME


def _get_status_path(case_id: str, version: str) -> Path:
    """Retorna la ruta del status.json de una versión."""
    return _get_version_path(case_id, version) / STATUS_FILENAME


def _get_index_path(case_id: str, version: str) -> Path:
    """Retorna la ruta del directorio del índice vectorial."""
    return _get_version_path(case_id, version) / INDEX_DIRNAME


# =========================================================
# GENERACIÓN DE VERSIONES
# =========================================================

def generate_version_id() -> str:
    """
    Genera un identificador de versión único basado en timestamp.
    
    Formato: v_YYYYMMDD_HHMMSS
    
    Returns:
        str: Identificador de versión (ej: "v_20260105_143052")
    """
    now = datetime.now()
    return f"{VERSION_PREFIX}{now.strftime('%Y%m%d_%H%M%S')}"


def create_new_version(case_id: str) -> Tuple[str, Path]:
    """
    Crea una nueva versión del vectorstore.
    
    REGLA: NUNCA sobrescribir versiones existentes.
    
    Args:
        case_id: ID del caso
        
    Returns:
        Tupla (version_id, version_path)
        
    Raises:
        ValueError: Si case_id está vacío
        RuntimeError: Si no se puede crear la versión
    """
    if not case_id or not case_id.strip():
        raise ValueError("case_id no puede estar vacío")
    
    version_id = generate_version_id()
    version_path = _get_version_path(case_id, version_id)
    
    logger.info(f"[VERSIONADO] Creando nueva versión: {version_id} para case_id={case_id}")
    
    try:
        # Crear estructura de directorios
        version_path.mkdir(parents=True, exist_ok=False)  # exist_ok=False → falla si existe
        index_path = _get_index_path(case_id, version_id)
        index_path.mkdir(parents=True, exist_ok=True)
        
        # Crear status.json inicial con estado BUILDING
        write_status(
            case_id=case_id,
            version=version_id,
            status="BUILDING",
        )
        
        logger.info(f"[VERSIONADO] Versión creada: {version_path}")
        return version_id, version_path
        
    except FileExistsError:
        # Esto NO debería pasar nunca (timestamps únicos)
        # Si pasa, es un error grave del sistema
        error_msg = f"La versión {version_id} ya existe. Esto NO debería ocurrir."
        logger.error(f"[VERSIONADO] {error_msg}")
        raise RuntimeError(error_msg)
    except Exception as e:
        error_msg = f"Error creando versión {version_id}: {e}"
        logger.error(f"[VERSIONADO] {error_msg}")
        raise RuntimeError(error_msg)


# =========================================================
# STATUS.JSON
# =========================================================

def write_status(
    case_id: str,
    version: str,
    status: str,
) -> None:
    """
    Escribe el status.json de una versión.
    
    Args:
        case_id: ID del caso
        version: ID de la versión
        status: Estado (BUILDING | READY | FAILED)
        
    Raises:
        ValueError: Si status no es válido o case_id vacío
    """
    if not case_id or not case_id.strip():
        raise ValueError("case_id no puede estar vacío")
    
    if status not in VALID_STATUSES:
        raise ValueError(f"Status inválido: {status}. Debe ser uno de {VALID_STATUSES}")
    
    status_path = _get_status_path(case_id, version)
    
    status_data = {
        "case_id": case_id,
        "version": version,
        "status": status,
        "updated_at": datetime.now().isoformat(),
    }
    
    try:
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(status_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"[VERSIONADO] Status actualizado: case_id={case_id}, version={version}, status={status}")
        
    except Exception as e:
        error_msg = f"Error escribiendo status.json: {e}"
        logger.error(f"[VERSIONADO] {error_msg}")
        raise RuntimeError(error_msg)


def read_status(case_id: str, version: str) -> Dict[str, Any]:
    """
    Lee el status.json de una versión.
    
    Args:
        case_id: ID del caso
        version: ID de la versión
        
    Returns:
        Diccionario con los datos del status
        
    Raises:
        FileNotFoundError: Si el archivo no existe
        ValueError: Si el contenido es inválido
    """
    status_path = _get_status_path(case_id, version)
    
    if not status_path.exists():
        raise FileNotFoundError(f"Status no encontrado: {status_path}")
    
    try:
        with open(status_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Validar campos obligatorios
        required_fields = ["case_id", "version", "status", "updated_at"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Campo obligatorio faltante en status.json: {field}")
        
        # Validar que case_id coincide
        if data["case_id"] != case_id:
            raise ValueError(
                f"case_id no coincide en status.json. "
                f"Esperado: {case_id}, Encontrado: {data['case_id']}"
            )
        
        return data
        
    except json.JSONDecodeError as e:
        raise ValueError(f"status.json corrupto: {e}")


# =========================================================
# MANIFEST.JSON
# =========================================================

def calculate_file_sha256(file_path: Path) -> str:
    """
    Calcula el SHA256 de un archivo.
    
    Args:
        file_path: Ruta del archivo
        
    Returns:
        Hash SHA256 en hexadecimal
    """
    sha256 = hashlib.sha256()
    
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    
    return sha256.hexdigest()


def write_manifest(
    case_id: str,
    version: str,
    manifest_data: ManifestData,
) -> None:
    """
    Escribe el manifest.json de una versión.
    
    Args:
        case_id: ID del caso
        version: ID de la versión
        manifest_data: Datos del manifest
        
    Raises:
        ValueError: Si los datos son inválidos
    """
    if not case_id or not case_id.strip():
        raise ValueError("case_id no puede estar vacío")
    
    if manifest_data.case_id != case_id:
        raise ValueError(
            f"case_id no coincide en manifest_data. "
            f"Esperado: {case_id}, Encontrado: {manifest_data.case_id}"
        )
    
    if manifest_data.version != version:
        raise ValueError(
            f"version no coincide en manifest_data. "
            f"Esperado: {version}, Encontrado: {manifest_data.version}"
        )
    
    manifest_path = _get_manifest_path(case_id, version)
    
    # Convertir dataclass a dict
    manifest_dict = {
        "case_id": manifest_data.case_id,
        "version": manifest_data.version,
        "embedding_model": manifest_data.embedding_model,
        "embedding_dim": manifest_data.embedding_dim,
        "chunking": manifest_data.chunking,
        "documents": manifest_data.documents,
        "total_chunks": manifest_data.total_chunks,
        "created_at": manifest_data.created_at,
        "generator": manifest_data.generator,
    }
    
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_dict, f, indent=2, ensure_ascii=False)
        
        logger.info(
            f"[VERSIONADO] Manifest creado: case_id={case_id}, version={version}, "
            f"total_chunks={manifest_data.total_chunks}"
        )
        
    except Exception as e:
        error_msg = f"Error escribiendo manifest.json: {e}"
        logger.error(f"[VERSIONADO] {error_msg}")
        raise RuntimeError(error_msg)


def read_manifest(case_id: str, version: str) -> Dict[str, Any]:
    """
    Lee el manifest.json de una versión.
    
    Args:
        case_id: ID del caso
        version: ID de la versión
        
    Returns:
        Diccionario con los datos del manifest
        
    Raises:
        FileNotFoundError: Si el archivo no existe
        ValueError: Si el contenido es inválido
    """
    manifest_path = _get_manifest_path(case_id, version)
    
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest no encontrado: {manifest_path}")
    
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Validar campos obligatorios
        required_fields = [
            "case_id", "version", "embedding_model", "embedding_dim",
            "chunking", "documents", "total_chunks", "created_at", "generator"
        ]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Campo obligatorio faltante en manifest.json: {field}")
        
        # Validar que case_id coincide
        if data["case_id"] != case_id:
            raise ValueError(
                f"case_id no coincide en manifest.json. "
                f"Esperado: {case_id}, Encontrado: {data['case_id']}"
            )
        
        return data
        
    except json.JSONDecodeError as e:
        raise ValueError(f"manifest.json corrupto: {e}")


# =========================================================
# VALIDACIONES DE INTEGRIDAD (BLOQUEANTES)
# =========================================================

def validate_version_integrity(
    case_id: str,
    version: str,
    collection,  # ChromaDB collection
) -> Tuple[bool, List[str]]:
    """
    Valida la integridad de una versión ANTES de marcarla como READY.
    
    REGLA 5: Validaciones BLOQUEANTES.
    Si falla CUALQUIER validación → status=FAILED + excepción.
    
    Validaciones:
    1. nº de chunks reales == total_chunks del manifest
    2. todos los doc_id del manifest existen
    3. todos los chunks contienen case_id correcto
    4. el índice vectorial existe y es accesible
    5. el modelo de embeddings coincide
    
    Args:
        case_id: ID del caso
        version: ID de la versión
        collection: Colección de ChromaDB
        
    Returns:
        Tupla (is_valid, errors)
        
    Raises:
        ValueError: Si case_id está vacío
        FileNotFoundError: Si no existe manifest o status
    """
    if not case_id or not case_id.strip():
        raise ValueError("case_id no puede estar vacío")
    
    errors: List[str] = []
    
    logger.info(f"[VALIDACIÓN] Iniciando validación de integridad: case_id={case_id}, version={version}")
    
    # --------------------------------------------------
    # 1. Validar que existen manifest y status
    # --------------------------------------------------
    try:
        manifest = read_manifest(case_id, version)
        status = read_status(case_id, version)
    except FileNotFoundError as e:
        errors.append(f"Archivos de control faltantes: {e}")
        return False, errors
    except ValueError as e:
        errors.append(f"Archivos de control inválidos: {e}")
        return False, errors
    
    # --------------------------------------------------
    # 2. Validar que el índice vectorial existe
    # --------------------------------------------------
    index_path = _get_index_path(case_id, version)
    if not index_path.exists() or not index_path.is_dir():
        errors.append(f"Índice vectorial no existe: {index_path}")
        return False, errors
    
    # --------------------------------------------------
    # 3. Validar que la colección de ChromaDB es accesible
    # --------------------------------------------------
    try:
        chunk_count = collection.count()
        logger.info(f"[VALIDACIÓN] Chunks en colección: {chunk_count}")
    except Exception as e:
        errors.append(f"Error accediendo a colección de ChromaDB: {e}")
        return False, errors
    
    # --------------------------------------------------
    # 4. Validar nº de chunks: real == manifest
    # --------------------------------------------------
    expected_chunks = manifest["total_chunks"]
    if chunk_count != expected_chunks:
        errors.append(
            f"Número de chunks no coincide. "
            f"Manifest: {expected_chunks}, ChromaDB: {chunk_count}"
        )
    
    # --------------------------------------------------
    # 5. Validar que todos los chunks contienen case_id correcto
    # --------------------------------------------------
    try:
        # Obtener todos los metadatos de la colección
        all_data = collection.get(include=["metadatas"])
        all_metadatas = all_data.get("metadatas", [])
        
        for i, meta in enumerate(all_metadatas):
            if not meta:
                errors.append(f"Chunk {i} sin metadata")
                continue
            
            chunk_case_id = meta.get("case_id")
            if not chunk_case_id:
                errors.append(f"Chunk {i} sin case_id en metadata")
            elif chunk_case_id != case_id:
                errors.append(
                    f"Chunk {i} con case_id incorrecto. "
                    f"Esperado: {case_id}, Encontrado: {chunk_case_id}"
                )
    except Exception as e:
        errors.append(f"Error validando metadatos de chunks: {e}")
    
    # --------------------------------------------------
    # 6. Validar modelo de embeddings
    # --------------------------------------------------
    manifest_model = manifest.get("embedding_model")
    if not manifest_model:
        errors.append("Manifest sin embedding_model")
    elif manifest_model != EMBEDDING_MODEL:
        errors.append(
            f"Modelo de embeddings no coincide. "
            f"Manifest: {manifest_model}, Sistema: {EMBEDDING_MODEL}"
        )
    
    # --------------------------------------------------
    # 7. Validar que todos los doc_id del manifest existen en chunks
    # --------------------------------------------------
    try:
        manifest_doc_ids = set(doc["doc_id"] for doc in manifest["documents"])
        chunk_doc_ids = set(meta.get("document_id") for meta in all_metadatas if meta)
        
        missing_docs = manifest_doc_ids - chunk_doc_ids
        if missing_docs:
            errors.append(f"Documentos en manifest sin chunks: {missing_docs}")
    except Exception as e:
        errors.append(f"Error validando document_ids: {e}")
    
    # --------------------------------------------------
    # Resultado final
    # --------------------------------------------------
    is_valid = len(errors) == 0
    
    if is_valid:
        logger.info(f"[VALIDACIÓN] ✅ Versión válida: case_id={case_id}, version={version}")
    else:
        logger.error(
            f"[VALIDACIÓN] ❌ Versión INVÁLIDA: case_id={case_id}, version={version}. "
            f"Errores: {len(errors)}"
        )
        for error in errors:
            logger.error(f"[VALIDACIÓN]   - {error}")
    
    return is_valid, errors


# =========================================================
# PUNTERO ACTIVE
# =========================================================

def update_active_pointer(case_id: str, version: str) -> None:
    """
    Actualiza el puntero ACTIVE para que apunte a la versión especificada.
    
    REGLA: SOLO se actualiza cuando una versión es válida (status=READY).
    
    Intenta crear un symlink. Si no es posible (SO no lo permite),
    crea un archivo de texto con el nombre de la versión.
    
    Args:
        case_id: ID del caso
        version: ID de la versión a activar
        
    Raises:
        ValueError: Si case_id está vacío o versión no existe
        RuntimeError: Si la versión no está en estado READY
    """
    if not case_id or not case_id.strip():
        raise ValueError("case_id no puede estar vacío")
    
    # Validar que la versión existe y está READY
    try:
        status = read_status(case_id, version)
        if status["status"] != "READY":
            raise RuntimeError(
                f"No se puede activar versión con status={status['status']}. "
                f"Solo se pueden activar versiones con status=READY"
            )
    except FileNotFoundError:
        raise ValueError(f"La versión {version} no existe para case_id={case_id}")
    
    active_path = _get_active_pointer_path(case_id)
    version_path = _get_version_path(case_id, version)
    
    logger.info(f"[VERSIONADO] Actualizando ACTIVE: case_id={case_id}, version={version}")
    
    # Eliminar puntero ACTIVE anterior si existe
    if active_path.exists():
        if active_path.is_symlink():
            active_path.unlink()
        elif active_path.is_file():
            active_path.unlink()
        elif active_path.is_dir():
            # NUNCA debería ser un directorio, pero por seguridad
            logger.warning(f"[VERSIONADO] ACTIVE es un directorio (inesperado). Eliminando...")
            shutil.rmtree(active_path)
    
    # Intentar crear symlink
    try:
        active_path.symlink_to(version_path, target_is_directory=True)
        logger.info(f"[VERSIONADO] Symlink creado: {active_path} -> {version_path}")
        return
    except (OSError, NotImplementedError) as e:
        logger.warning(f"[VERSIONADO] No se pudo crear symlink: {e}. Usando archivo de texto...")
    
    # Si symlink falla, crear archivo de texto
    try:
        with open(active_path, "w", encoding="utf-8") as f:
            f.write(version)
        logger.info(f"[VERSIONADO] Archivo ACTIVE creado: {active_path} (contenido: {version})")
    except Exception as e:
        error_msg = f"Error creando puntero ACTIVE: {e}"
        logger.error(f"[VERSIONADO] {error_msg}")
        raise RuntimeError(error_msg)


def get_active_version(case_id: str) -> Optional[str]:
    """
    Obtiene la versión activa para un caso.
    
    Args:
        case_id: ID del caso
        
    Returns:
        ID de la versión activa o None si no existe
    """
    active_path = _get_active_pointer_path(case_id)
    
    if not active_path.exists():
        logger.warning(f"[VERSIONADO] No existe puntero ACTIVE para case_id={case_id}")
        return None
    
    # Si es symlink
    if active_path.is_symlink():
        target = active_path.resolve()
        version = target.name
        logger.info(f"[VERSIONADO] ACTIVE (symlink): case_id={case_id}, version={version}")
        return version
    
    # Si es archivo de texto
    if active_path.is_file():
        try:
            with open(active_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
            logger.info(f"[VERSIONADO] ACTIVE (archivo): case_id={case_id}, version={version}")
            return version
        except Exception as e:
            logger.error(f"[VERSIONADO] Error leyendo ACTIVE: {e}")
            return None
    
    logger.error(f"[VERSIONADO] ACTIVE en estado inesperado: {active_path}")
    return None


def get_active_version_path(case_id: str) -> Optional[Path]:
    """
    Obtiene la ruta de la versión activa para un caso.
    
    Args:
        case_id: ID del caso
        
    Returns:
        Ruta de la versión activa o None si no existe
    """
    version = get_active_version(case_id)
    if not version:
        return None
    
    return _get_version_path(case_id, version)


# =========================================================
# LISTADO Y GESTIÓN DE VERSIONES
# =========================================================

def list_versions(case_id: str) -> List[VersionInfo]:
    """
    Lista todas las versiones de un caso.
    
    Args:
        case_id: ID del caso
        
    Returns:
        Lista de VersionInfo ordenada por fecha de creación (más reciente primero)
    """
    root = _get_case_vectorstore_root(case_id)
    
    if not root.exists():
        logger.info(f"[VERSIONADO] No existen versiones para case_id={case_id}")
        return []
    
    versions: List[VersionInfo] = []
    
    for item in root.iterdir():
        # Ignorar ACTIVE
        if item.name == ACTIVE_POINTER:
            continue
        
        # Solo directorios que empiezan con VERSION_PREFIX
        if not item.is_dir() or not item.name.startswith(VERSION_PREFIX):
            continue
        
        version_id = item.name
        
        # Leer status
        try:
            status_data = read_status(case_id, version_id)
            status = status_data["status"]
            created_at_str = status_data["updated_at"]
            created_at = datetime.fromisoformat(created_at_str)
        except Exception as e:
            logger.warning(f"[VERSIONADO] Error leyendo status de {version_id}: {e}")
            status = "UNKNOWN"
            created_at = datetime.min
        
        versions.append(
            VersionInfo(
                case_id=case_id,
                version=version_id,
                status=status,
                path=item,
                created_at=created_at,
            )
        )
    
    # Ordenar por fecha de creación (más reciente primero)
    versions.sort(key=lambda v: v.created_at, reverse=True)
    
    logger.info(f"[VERSIONADO] Versiones encontradas para case_id={case_id}: {len(versions)}")
    
    return versions


def cleanup_old_versions(case_id: str, keep_last: int = 3) -> int:
    """
    Elimina versiones antiguas manteniendo las N más recientes.
    
    REGLA 6: Política de housekeeping.
    - Mantener N versiones (default=3)
    - NO borrar la versión ACTIVE
    - Log obligatorio de eliminaciones
    
    Args:
        case_id: ID del caso
        keep_last: Número de versiones a mantener (default=3)
        
    Returns:
        Número de versiones eliminadas
        
    Raises:
        ValueError: Si keep_last < 1
    """
    if keep_last < 1:
        raise ValueError("keep_last debe ser >= 1")
    
    logger.info(
        f"[HOUSEKEEPING] Iniciando limpieza de versiones antiguas: "
        f"case_id={case_id}, keep_last={keep_last}"
    )
    
    versions = list_versions(case_id)
    
    if len(versions) <= keep_last:
        logger.info(
            f"[HOUSEKEEPING] No es necesario limpiar. "
            f"Versiones actuales: {len(versions)}, Mantener: {keep_last}"
        )
        return 0
    
    # Obtener versión activa (NO se debe borrar)
    active_version = get_active_version(case_id)
    
    # Versiones READY ordenadas por fecha (más reciente primero)
    ready_versions = [v for v in versions if v.is_ready()]
    
    # Determinar qué versiones mantener:
    # - Versión ACTIVE (siempre)
    # - Las keep_last versiones READY más recientes
    versions_to_keep = set()
    
    if active_version:
        versions_to_keep.add(active_version)
        logger.info(f"[HOUSEKEEPING] Manteniendo versión ACTIVE: {active_version}")
    
    for v in ready_versions[:keep_last]:
        versions_to_keep.add(v.version)
        logger.info(f"[HOUSEKEEPING] Manteniendo versión reciente: {v.version}")
    
    # Determinar qué versiones eliminar
    versions_to_delete = [
        v for v in versions
        if v.version not in versions_to_keep
    ]
    
    if not versions_to_delete:
        logger.info(f"[HOUSEKEEPING] No hay versiones para eliminar")
        return 0
    
    # Eliminar versiones
    deleted_count = 0
    for v in versions_to_delete:
        try:
            shutil.rmtree(v.path)
            logger.info(
                f"[HOUSEKEEPING] ✅ Versión eliminada: {v.version} "
                f"(status={v.status}, created_at={v.created_at.isoformat()})"
            )
            deleted_count += 1
        except Exception as e:
            logger.error(f"[HOUSEKEEPING] ❌ Error eliminando versión {v.version}: {e}")
    
    logger.info(
        f"[HOUSEKEEPING] Limpieza completada: "
        f"case_id={case_id}, eliminadas={deleted_count}"
    )
    
    return deleted_count

