"""
Pipeline de generación de embeddings con versionado estricto.

CAMBIO CRÍTICO vs versión anterior:
- NUNCA sobrescribe un vectorstore existente
- Cada ejecución crea una versión nueva
- Validaciones de integridad BLOQUEANTES
- Solo activa versiones válidas (status=READY)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import chromadb
from sqlalchemy import select
from sqlalchemy.orm import Session
from openai import OpenAI

from app.core.variables import (
    EMBEDDING_MODEL,
    EMBEDDING_BATCH_SIZE,
)
from app.core.logger import logger
from app.models.document_chunk import DocumentChunk
from app.models.document import Document
from app.services.vectorstore_versioning import (
    create_new_version,
    write_status,
    write_manifest,
    validate_version_integrity,
    update_active_pointer,
    cleanup_old_versions,
    get_active_version_path,
    _get_index_path,
    ManifestData,
    calculate_file_sha256,
)


# =========================================================
# VECTORSTORE (Chroma) - CON VERSIONADO
# =========================================================

def get_case_collection(case_id: str, version: Optional[str] = None):
    """
    Obtiene la colección de ChromaDB para un caso.
    
    Si version es None, intenta usar la versión ACTIVE.
    
    IMPORTANTE: Esta función ya NO crea automáticamente la estructura.
    Usa create_new_version() para crear una versión nueva.
    
    Args:
        case_id: ID del caso
        version: ID de la versión (opcional, usa ACTIVE si no se especifica)
        
    Returns:
        Colección de ChromaDB
        
    Raises:
        RuntimeError: Si no existe la versión o ACTIVE
    """
    if version is None:
        # Intentar usar versión ACTIVE
        version_path = get_active_version_path(case_id)
        if not version_path:
            raise RuntimeError(
                f"No existe versión ACTIVE para case_id={case_id}. "
                "Debes crear una versión nueva con build_embeddings_for_case()"
            )
    else:
        # Usar versión específica
        version_path = _get_index_path(case_id, version)
        if not version_path.exists():
            raise RuntimeError(
                f"No existe versión {version} para case_id={case_id}"
            )
    
    # Obtener ruta del índice
    if version:
        index_path = _get_index_path(case_id, version)
    else:
        # version_path ya apunta al directorio de la versión
        index_path = version_path / "index"
    
    logger.info(f"[EMBEDDINGS] Inicializando vectorstore (Chroma)")
    logger.info(f"[EMBEDDINGS] case_id: {case_id}")
    logger.info(f"[EMBEDDINGS] path: {index_path}")
    
    client = chromadb.PersistentClient(path=str(index_path))
    
    collection = client.get_or_create_collection(
        name="chunks",
        metadata={"case_id": case_id},
    )
    
    # Debug info
    try:
        count = collection.count()
        logger.info(f"[EMBEDDINGS] Embeddings actuales en colección: {count}")
    except Exception:
        logger.warning("[EMBEDDINGS] No se pudo obtener count() de Chroma")
    
    return collection


# =========================================================
# CHUNKS (SQL)
# =========================================================

def get_chunks_for_case(db: Session, case_id: str) -> list[DocumentChunk]:
    """
    Carga todos los chunks de un caso desde la base de datos.
    
    VALIDACIÓN CRÍTICA: Todos los chunks DEBEN tener case_id correcto.
    """
    logger.info("[EMBEDDINGS] Cargando chunks desde BBDD")
    logger.info(f"[EMBEDDINGS] case_id: {case_id}")
    
    q = (
        select(DocumentChunk)
        .where(DocumentChunk.case_id == case_id)
        .order_by(
            DocumentChunk.document_id.asc(),
            DocumentChunk.chunk_index.asc(),
        )
    )
    
    chunks = db.execute(q).scalars().all()
    
    # VALIDACIÓN: Todos los chunks DEBEN tener case_id correcto
    for chunk in chunks:
        if chunk.case_id != case_id:
            raise RuntimeError(
                f"VIOLACIÓN DE INTEGRIDAD: Chunk {chunk.chunk_id} tiene case_id={chunk.case_id}, "
                f"esperado case_id={case_id}. Abortando ingesta."
            )
    
    logger.info(f"[EMBEDDINGS] Chunks encontrados: {len(chunks)}")
    
    return chunks


# =========================================================
# EMBEDDINGS (OpenAI)
# =========================================================

def _embed_texts_openai(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Genera embeddings usando OpenAI."""
    resp = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in resp.data]


def _get_embedding_dimension(client: OpenAI) -> int:
    """Obtiene la dimensión del modelo de embeddings."""
    # Generar un embedding de prueba para obtener la dimensión
    resp = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=["test"],
    )
    return len(resp.data[0].embedding)


# =========================================================
# PIPELINE PRINCIPAL CON VERSIONADO
# =========================================================

def build_embeddings_for_case(
    db: Session,
    *,
    case_id: str,
    openai_client: Optional[OpenAI] = None,
    keep_versions: int = 3,
) -> str:
    """
    Crea una nueva versión del vectorstore para un caso.
    
    FLUJO ESTRICTO:
    1. Crear versión nueva con status=BUILDING
    2. Ejecutar ingesta y embeddings
    3. Generar manifest.json
    4. Validar integridad (BLOQUEANTE)
    5. Si OK → status=READY y actualizar ACTIVE
    6. Si KO → status=FAILED y NO tocar ACTIVE
    7. Limpiar versiones antiguas
    
    Args:
        db: Sesión de base de datos
        case_id: ID del caso
        openai_client: Cliente de OpenAI (opcional)
        keep_versions: Número de versiones a mantener (default=3)
        
    Returns:
        ID de la versión creada
        
    Raises:
        ValueError: Si case_id está vacío
        RuntimeError: Si falla la validación de integridad
    """
    if not case_id or not case_id.strip():
        raise ValueError("case_id no puede estar vacío")
    
    logger.info("=" * 60)
    logger.info("[EMBEDDINGS] Inicio pipeline embeddings con versionado")
    logger.info(f"[EMBEDDINGS] case_id: {case_id}")
    logger.info("=" * 60)
    
    # --------------------------------------------------
    # 1. Crear nueva versión con status=BUILDING
    # --------------------------------------------------
    try:
        version_id, version_path = create_new_version(case_id)
    except Exception as e:
        logger.error(f"[EMBEDDINGS] ❌ Error creando versión: {e}")
        raise RuntimeError(f"No se pudo crear versión para case_id={case_id}: {e}")
    
    # A partir de aquí, cualquier error debe marcar la versión como FAILED
    try:
        # --------------------------------------------------
        # 2. Inicializar cliente OpenAI
        # --------------------------------------------------
        if openai_client is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY no definida en entorno")
            openai_client = OpenAI(api_key=api_key)
        
        # --------------------------------------------------
        # 3. Obtener dimensión del modelo de embeddings
        # --------------------------------------------------
        embedding_dim = _get_embedding_dimension(openai_client)
        logger.info(f"[EMBEDDINGS] Modelo: {EMBEDDING_MODEL}, Dimensión: {embedding_dim}")
        
        # --------------------------------------------------
        # 4. Cargar chunks desde BD
        # --------------------------------------------------
        chunks = get_chunks_for_case(db, case_id)
        
        if not chunks:
            logger.warning("[EMBEDDINGS] ⚠️  No hay chunks para procesar")
            write_status(case_id, version_id, "FAILED")
            raise RuntimeError(f"No hay chunks para case_id={case_id}. Abortando ingesta.")
        
        # --------------------------------------------------
        # 5. Obtener información de documentos para manifest
        # --------------------------------------------------
        documents_info = []
        doc_ids = list(set(c.document_id for c in chunks))
        
        for doc_id in doc_ids:
            # Obtener documento de BD
            doc = db.query(Document).filter(Document.document_id == doc_id).first()
            if not doc:
                logger.warning(f"[EMBEDDINGS] ⚠️  Documento {doc_id} no encontrado en BD")
                continue
            
            # VALIDACIÓN: case_id debe coincidir
            if doc.case_id != case_id:
                write_status(case_id, version_id, "FAILED")
                raise RuntimeError(
                    f"VIOLACIÓN DE INTEGRIDAD: Documento {doc_id} tiene case_id={doc.case_id}, "
                    f"esperado case_id={case_id}. Abortando ingesta."
                )
            
            # Calcular SHA256 del archivo si existe
            sha256_hash = "NOT_AVAILABLE"
            if doc.storage_path and os.path.exists(doc.storage_path):
                try:
                    sha256_hash = calculate_file_sha256(Path(doc.storage_path))
                except Exception as e:
                    logger.warning(f"[EMBEDDINGS] ⚠️  No se pudo calcular SHA256 para {doc_id}: {e}")
            
            # Contar chunks de este documento
            doc_chunks_count = sum(1 for c in chunks if c.document_id == doc_id)
            
            documents_info.append({
                "doc_id": doc_id,
                "filename": doc.filename,
                "sha256": sha256_hash,
                "num_chunks": doc_chunks_count,
            })
        
        logger.info(f"[EMBEDDINGS] Documentos a procesar: {len(documents_info)}")
        
        # --------------------------------------------------
        # 6. Inicializar colección de ChromaDB en la nueva versión
        # --------------------------------------------------
        collection = get_case_collection(case_id, version_id)
        
        # --------------------------------------------------
        # 7. Generar embeddings por batches
        # --------------------------------------------------
        all_ids = [c.chunk_id for c in chunks]
        
        logger.info(f"[EMBEDDINGS] Total chunks a procesar: {len(chunks)}")
        
        for i in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[i : i + EMBEDDING_BATCH_SIZE]
            
            batch_ids = [c.chunk_id for c in batch]
            batch_texts = [c.content for c in batch]
            
            logger.info(f"[EMBEDDINGS] Procesando batch {i // EMBEDDING_BATCH_SIZE + 1}")
            logger.info(f"[EMBEDDINGS] Tamaño: {len(batch)}")
            
            # Generar embeddings
            vectors = _embed_texts_openai(openai_client, batch_texts)
            
            # VALIDACIÓN: Todos los chunks DEBEN tener case_id correcto
            metadatas = []
            for c in batch:
                if c.case_id != case_id:
                    write_status(case_id, version_id, "FAILED")
                    raise RuntimeError(
                        f"VIOLACIÓN DE INTEGRIDAD: Chunk {c.chunk_id} tiene case_id={c.case_id}, "
                        f"esperado case_id={case_id}. Abortando ingesta."
                    )
                
                metadatas.append({
                    "case_id": c.case_id,
                    "document_id": c.document_id,
                    "chunk_index": c.chunk_index,
                })
            
            # Insertar en ChromaDB
            collection.add(
                ids=batch_ids,
                embeddings=vectors,
                documents=batch_texts,
                metadatas=metadatas,
            )
            
            logger.info("[EMBEDDINGS] ✅ Batch insertado")
        
        logger.info("[EMBEDDINGS] ✅ Todos los embeddings generados")
        
        # --------------------------------------------------
        # 8. Generar manifest.json
        # --------------------------------------------------
        manifest_data = ManifestData(
            case_id=case_id,
            version=version_id,
            embedding_model=EMBEDDING_MODEL,
            embedding_dim=embedding_dim,
            chunking={
                "strategy": "recursive_text_splitter",
                "chunk_size": 2000,  # Valor por defecto del chunker
                "overlap": 200,  # Valor por defecto del chunker
            },
            documents=documents_info,
            total_chunks=len(chunks),
            created_at=version_path.stat().st_ctime if version_path.exists() else "",
        )
        
        # Convertir timestamp a ISO8601 si es necesario
        if isinstance(manifest_data.created_at, (int, float)):
            from datetime import datetime
            manifest_data.created_at = datetime.fromtimestamp(manifest_data.created_at).isoformat()
        
        write_manifest(case_id, version_id, manifest_data)
        logger.info("[EMBEDDINGS] ✅ Manifest generado")
        
        # --------------------------------------------------
        # 9. Validar integridad (BLOQUEANTE)
        # --------------------------------------------------
        logger.info("[EMBEDDINGS] Iniciando validación de integridad...")
        is_valid, errors = validate_version_integrity(case_id, version_id, collection)
        
        if not is_valid:
            # Marcar como FAILED
            write_status(case_id, version_id, "FAILED")
            logger.error("[EMBEDDINGS] ❌ Validación de integridad FALLÓ")
            for error in errors:
                logger.error(f"[EMBEDDINGS]   - {error}")
            raise RuntimeError(
                f"Validación de integridad falló para case_id={case_id}, version={version_id}. "
                f"Errores: {errors}"
            )
        
        logger.info("[EMBEDDINGS] ✅ Validación de integridad OK")
        
        # --------------------------------------------------
        # 10. Marcar como READY y actualizar ACTIVE
        # --------------------------------------------------
        write_status(case_id, version_id, "READY")
        logger.info("[EMBEDDINGS] ✅ Versión marcada como READY")
        
        update_active_pointer(case_id, version_id)
        logger.info("[EMBEDDINGS] ✅ Puntero ACTIVE actualizado")
        
        # --------------------------------------------------
        # 11. Limpiar versiones antiguas
        # --------------------------------------------------
        deleted_count = cleanup_old_versions(case_id, keep_last=keep_versions)
        logger.info(f"[EMBEDDINGS] ✅ Housekeeping completado: {deleted_count} versiones eliminadas")
        
        # --------------------------------------------------
        # FIN
        # --------------------------------------------------
        logger.info("=" * 60)
        logger.info(f"[EMBEDDINGS] ✅ Pipeline completado exitosamente")
        logger.info(f"[EMBEDDINGS] case_id: {case_id}")
        logger.info(f"[EMBEDDINGS] version: {version_id}")
        logger.info(f"[EMBEDDINGS] total_chunks: {len(chunks)}")
        logger.info("=" * 60)
        
        return version_id
        
    except Exception as e:
        # Marcar versión como FAILED si algo salió mal
        try:
            write_status(case_id, version_id, "FAILED")
            logger.error(f"[EMBEDDINGS] ❌ Pipeline falló. Versión marcada como FAILED: {version_id}")
        except Exception as e2:
            logger.error(f"[EMBEDDINGS] ❌ No se pudo marcar versión como FAILED: {e2}")
        
        # Re-lanzar la excepción original
        raise
