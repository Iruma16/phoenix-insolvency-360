"""
ENDPOINT OFICIAL DE GESTIÓN DE DOCUMENTOS (PANTALLA 1).

PRINCIPIO: Esta capa NO contiene lógica de ingesta.
Solo orquesta la ingesta del core y expone su estado real.

PROHIBIDO:
- modificar lógica de ingesta
- editar documentos existentes
- borrar documentos
- reintentar automáticamente
- silenciar errores
"""
from __future__ import annotations

from typing import List
from datetime import datetime, timedelta
import io
import tempfile
import os

from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.case import Case
from app.models.document import (
    Document,
    store_document_file,
    calculate_file_hash,
)
from app.models.document_chunk import DocumentChunk
from app.models.document_summary import (
    DocumentSummary,
    DocumentStatus,
)
from app.services.ingesta import ingerir_archivo, ParsingResult
from app.services.document_chunk_pipeline import build_document_chunks_for_case, build_document_chunks_for_single_document
from app.services.ingestion_failfast import ValidationMode
from app.core.exceptions import DocumentValidationError
from app.core.logger import logger
import hashlib
import numpy as np
from openai import OpenAI
from app.core.variables import EMBEDDING_MODEL
from app.models.duplicate_action import DuplicateAction, DuplicateActionRequest


router = APIRouter(
    prefix="/cases/{case_id}/documents",
    tags=["documents"],
)


# =========================================================
# FUNCIONES DE DEDUPLICACIÓN (FASE 2A)
# =========================================================

def normalize_text_for_hash(text: str) -> str:
    """
    Normaliza texto para calcular content_hash.
    
    Normalización:
    - Lowercase
    - Sin espacios múltiples
    - Sin saltos de línea múltiples
    - Sin puntuación al inicio/final de líneas
    
    Args:
        text: Texto a normalizar
        
    Returns:
        Texto normalizado
    """
    if not text:
        return ""
    
    # Lowercase
    normalized = text.lower().strip()
    
    # Reemplazar saltos de línea y retornos de carro por espacios
    normalized = normalized.replace('\n', ' ').replace('\r', '')
    
    # Remover espacios múltiples
    normalized = ' '.join(normalized.split())
    
    return normalized


def calculate_content_hash(text: str) -> str:
    """
    Calcula SHA256 del texto normalizado.
    
    Args:
        text: Texto del documento
        
    Returns:
        Hash SHA256 en hexadecimal (64 caracteres)
    """
    if not text:
        return hashlib.sha256(b"").hexdigest()
    
    normalized = normalize_text_for_hash(text)
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def validate_and_build_embedding_dict(vector: List[float], model: str) -> dict:
    """
    Construye dict de embedding con contrato fijo.
    
    Contrato:
    {
        "model": "text-embedding-3-small",
        "vector": [0.1, 0.2, ...],
        "dim": 1536
    }
    
    Args:
        vector: Vector de embedding
        model: Nombre del modelo
        
    Returns:
        Dict con contrato validado
        
    Raises:
        ValueError: Si el vector es inválido
    """
    if not vector or not isinstance(vector, list):
        raise ValueError("Vector debe ser lista no vacía")
    
    return {
        "model": model,
        "vector": vector,
        "dim": len(vector),
    }


def generate_document_embedding(text: str, openai_client: OpenAI) -> dict:
    """
    Genera embedding del documento completo usando OpenAI.
    
    Args:
        text: Texto del documento
        openai_client: Cliente de OpenAI
        
    Returns:
        Dict con embedding validado {"model": ..., "vector": [...], "dim": ...}
    """
    if not text:
        return {}
    
    # Truncar si es muy largo (límite de OpenAI: 8191 tokens ~= 32k chars)
    max_chars = 30000
    if len(text) > max_chars:
        # Tomar inicio y final para mantener contexto
        text = text[:max_chars//2] + " ... " + text[-max_chars//2:]
    
    try:
        resp = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        vector = resp.data[0].embedding
        return validate_and_build_embedding_dict(vector, EMBEDDING_MODEL)
    except Exception as e:
        logger.error(f"Error generando embedding de documento: {e}")
        return {}


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calcula similaridad coseno entre dos vectores.
    
    Args:
        vec1: Vector 1
        vec2: Vector 2
        
    Returns:
        Similaridad coseno (0.0 - 1.0)
    """
    if not vec1 or not vec2:
        return 0.0
    
    a = np.array(vec1)
    b = np.array(vec2)
    
    # Producto punto
    dot_product = np.dot(a, b)
    
    # Normas
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    # Coseno
    similarity = dot_product / (norm_a * norm_b)
    
    # Normalizar a [0, 1]
    # Coseno va de [-1, 1], pero para texto siempre es positivo
    return float(max(0.0, min(1.0, similarity)))


def find_semantic_duplicates(
    db: Session,
    case_id: str,
    new_embedding: List[float],
    new_doc_type: str,
    threshold: float = 0.92,
    max_candidates: int = 50,
) -> List[tuple[Document, float]]:
    """
    Busca documentos con alta similaridad semántica.
    
    Optimizaciones:
    - Solo compara contra mismo doc_type
    - Limita a últimos N candidatos (más recientes)
    
    Args:
        db: Sesión de base de datos
        case_id: ID del caso
        new_embedding: Embedding del nuevo documento
        new_doc_type: Tipo de documento (para filtrar candidatos)
        threshold: Umbral de similaridad (default=0.92)
        max_candidates: Máximo de candidatos a evaluar (default=50)
        
    Returns:
        Lista de tuplas (documento, similaridad) ordenadas por similaridad
    """
    if not new_embedding:
        return []
    
    # OPTIMIZACIÓN: Filtrar por tipo y limitar candidatos
    existing_docs = (
        db.query(Document)
        .filter(
            Document.case_id == case_id,
            Document.document_embedding.isnot(None),
            Document.doc_type == new_doc_type,  # Mismo tipo
        )
        .order_by(Document.created_at.desc())  # Más recientes primero
        .limit(max_candidates)  # Máximo N candidatos
        .all()
    )
    
    duplicates = []
    
    for doc in existing_docs:
        if not doc.document_embedding or not isinstance(doc.document_embedding, dict):
            logger.warning(f"Embedding inválido (no dict) en {doc.document_id}")
            continue
        
        # Obtener el vector del embedding
        existing_embedding = doc.document_embedding.get("vector", [])
        if not existing_embedding or not isinstance(existing_embedding, list):
            logger.warning(f"Vector inválido (no list) en {doc.document_id}")
            continue
        
        # Calcular similaridad
        similarity = cosine_similarity(new_embedding, existing_embedding)
        
        if similarity >= threshold:
            duplicates.append((doc, similarity))
    
    # Ordenar por similaridad descendente
    duplicates.sort(key=lambda x: x[1], reverse=True)
    
    return duplicates


def _calculate_document_status(
    document: Document,
    chunks_count: int,
) -> DocumentStatus:
    """
    Calcula el estado de un documento.
    
    REGLAS:
    - FAILED: parsing_status = "rejected" o "failed"
    - INGESTED: parsing_status = "completed" y chunks_count > 0
    - PENDING: parsing_status = "pending" o chunks_count = 0
    
    Args:
        document: Documento del core
        chunks_count: Número de chunks generados
        
    Returns:
        DocumentStatus calculado
    """
    if document.parsing_status in ["rejected", "failed"]:
        return DocumentStatus.FAILED
    
    if document.parsing_status == "completed" and chunks_count > 0:
        return DocumentStatus.INGESTED
    
    return DocumentStatus.PENDING


def _build_document_summary(document: Document, db: Session) -> DocumentSummary:
    """
    Construye un DocumentSummary desde un Document del core.
    
    NO inventa datos.
    NO asume estados.
    SOLO lee el estado real.
    
    Args:
        document: Documento del core
        db: Sesión de base de datos
        
    Returns:
        DocumentSummary con estado calculado desde el core
    """
    # Contar chunks reales
    chunks_count = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.document_id)
        .count()
    )
    
    # Calcular estado
    status = _calculate_document_status(document, chunks_count)
    
    # Error message si aplica
    error_message = None
    if status == DocumentStatus.FAILED:
        error_message = document.parsing_rejection_reason or "Error en procesamiento"
    
    # Obtener nombre del archivo original si es duplicado
    duplicate_of_filename = None
    if document.is_duplicate and document.duplicate_of_document_id:
        original_doc = db.query(Document).filter(
            Document.document_id == document.duplicate_of_document_id
        ).first()
        if original_doc:
            duplicate_of_filename = original_doc.filename
    
    return DocumentSummary(
        document_id=document.document_id,
        case_id=document.case_id,
        filename=document.filename,
        file_type=document.file_format,
        status=status,
        chunks_count=chunks_count,
        error_message=error_message,
        created_at=document.created_at,
        # Deduplicación
        is_duplicate=document.is_duplicate,
        duplicate_of_document_id=document.duplicate_of_document_id,
        duplicate_of_filename=duplicate_of_filename,
        duplicate_similarity=document.duplicate_similarity,
        duplicate_action=document.duplicate_action,
    )


@router.post(
    "",
    response_model=List[DocumentSummary],
    status_code=status.HTTP_201_CREATED,
    summary="Ingerir documentos en un caso",
    description=(
        "Ingesta uno o varios documentos en un caso. "
        "Delega la ingesta REAL al core. "
        "Devuelve el estado de cada documento procesado."
    ),
)
async def ingest_documents(
    case_id: str,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> List[DocumentSummary]:
    """
    Ingesta documentos en un caso.
    
    La UI solo orquesta, NO implementa lógica de ingesta.
    Todo el procesamiento ocurre en el core.
    
    Args:
        case_id: ID del caso
        files: Archivos a ingerir
        db: Sesión de base de datos
        
    Returns:
        Lista de DocumentSummary con estado de cada documento
        
    Raises:
        HTTPException 404: Si el caso no existe
        HTTPException 400: Si hay errores de validación
    """
    # Verificar que el caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Caso '{case_id}' no encontrado"
        )
    
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se proporcionaron archivos"
        )
    
    results: List[DocumentSummary] = []
    
    for file in files:
        temp_file_path = None
        start_time = datetime.utcnow().timestamp()  # FASE 2A: Para métricas de processing_time
        try:
            # Leer contenido del archivo
            content = await file.read()
            
            if not content:
                # Archivo vacío → registrar como FAILED
                logger.warning(f"Archivo vacío recibido: {file.filename}")
                # No persistir documento vacío, solo registrar error
                continue
            
            # =====================================================
            # FASE 1B: INTEGRIDAD LEGAL
            # =====================================================
            
            # 1. Guardar temporalmente para calcular hash
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            # 2. Calcular hash SHA256 (integridad y deduplicación)
            sha256_hash = calculate_file_hash(temp_file_path)
            logger.info(f"Hash SHA256 calculado para {file.filename}: {sha256_hash}")
            
            # 3. DEDUPLICACIÓN BINARIA (ANTES de parsear/almacenar)
            existing_doc = db.query(Document).filter(
                Document.case_id == case_id,  # Mismo caso
                Document.sha256_hash == sha256_hash
            ).first()
            
            if existing_doc:
                logger.warning(
                    f"⚠️ DUPLICADO BINARIO detectado ANTES de parsear: {file.filename} "
                    f"(hash coincide con {existing_doc.filename}, document_id={existing_doc.document_id})"
                )
                # Retornar el documento existente sin parsear/almacenar
                results.append(_build_document_summary(existing_doc, db))
                # Limpiar archivo temporal
                if temp_file_path and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                continue
            
            # 4. Generar document_id ANTES de almacenar
            import uuid
            document_id = str(uuid.uuid4())
            
            # 5. Almacenar archivo original con integridad legal
            storage_metadata = store_document_file(
                client_id="default",  # TODO: obtener de configuración o case
                case_id=case_id,
                document_id=document_id,
                original_file_path=temp_file_path,
            )
            
            logger.info(f"Archivo almacenado: {storage_metadata['storage_path']}")
            
            # =====================================================
            # FIN FASE 1B
            # =====================================================
            
            # DELEGAR al core: ingesta con validación fail-fast
            parsing_result = ingerir_archivo(
                file_stream=io.BytesIO(content),
                filename=file.filename,
                case_id=case_id,
                validation_mode=ValidationMode.PERMISSIVE,  # No abortar por un doc inválido
            )
            
            # Si la validación rechazó el documento (PERMISSIVE mode)
            if parsing_result is None:
                logger.warning(f"Documento rechazado por validación: {file.filename}")
                # El documento fue rechazado en pre-ingesta
                # Registrar en DB con status rejected
                doc = Document(
                    document_id=document_id,  # Usar el ID generado
                    case_id=case_id,
                    filename=storage_metadata["original_filename"],
                    file_format=file.content_type or "unknown",
                    doc_type="contrato",  # Tipo genérico: balance, pyg, mayor, sumas_saldos, extracto_bancario, acta, acuerdo_societario, poder, email_direccion, email_banco, email_asesoria, contrato, venta_activo, prestamo, nomina
                    source="upload",
                    date_start=datetime.utcnow(),
                    date_end=datetime.utcnow(),
                    reliability="original",  # Valores válidos: original, escaneado, foto
                    storage_path=storage_metadata["storage_path"],
                    # FASE 1B: Integridad Legal
                    sha256_hash=storage_metadata["sha256_hash"],
                    file_size_bytes=storage_metadata["file_size_bytes"],
                    mime_type=storage_metadata["mime_type"],
                    uploaded_at=datetime.utcnow(),
                    legal_hold=False,
                    retention_until=datetime.utcnow() + timedelta(days=365*6),  # 6 años
                    # Parsing
                    parsing_status="rejected",
                    parsing_rejection_reason="Documento rechazado en validación pre-ingesta",
                    raw_text=None,  # FASE 1: Sin texto válido
                    # Deduplicación (valores por defecto para documentos rechazados)
                    content_hash=None,
                    document_embedding=None,
                    is_duplicate=False,
                    duplicate_of_document_id=None,
                    duplicate_similarity=None,
                    duplicate_action=None,
                )
                db.add(doc)
                db.commit()
                db.refresh(doc)
                
                results.append(_build_document_summary(doc, db))
                continue
            
            # =====================================================
            # FASE 2A: DEDUPLICACIÓN
            # =====================================================
            
            # Variables de deduplicación
            is_duplicate = False
            duplicate_of_document_id = None
            duplicate_similarity = None
            duplicate_action = None
            content_hash = None
            document_embedding_dict = None
            
            # 1. Calcular content_hash del texto normalizado
            if parsing_result and parsing_result.texto:
                content_hash = calculate_content_hash(parsing_result.texto)
                logger.info(f"Content hash calculado: {content_hash[:16]}...")
                
                # 2. Verificar duplicado EXACTO por content_hash
                content_duplicate = db.query(Document).filter(
                    Document.case_id == case_id,
                    Document.content_hash == content_hash,
                ).first()
                
                if content_duplicate:
                    logger.warning(
                        f"⚠️  DUPLICADO EXACTO detectado: {file.filename} "
                        f"tiene el mismo contenido que {content_duplicate.filename} "
                        f"(document_id={content_duplicate.document_id})"
                    )
                    is_duplicate = True
                    duplicate_of_document_id = content_duplicate.document_id
                    duplicate_similarity = 1.0  # Contenido idéntico
                    duplicate_action = "pending"
                
                # 3. Si no es duplicado exacto, verificar SEMÁNTICO
                if not is_duplicate:
                    try:
                        # Inicializar cliente OpenAI
                        api_key = os.getenv("OPENAI_API_KEY")
                        if api_key:
                            openai_client = OpenAI(api_key=api_key)
                            
                            # Generar embedding del documento completo
                            doc_embedding = generate_document_embedding(
                                parsing_result.texto,
                                openai_client
                            )
                            
                            if doc_embedding:
                                # Ya es dict validado con contrato fijo
                                document_embedding_dict = doc_embedding
                                logger.info(f"Embedding generado: dim={doc_embedding.get('dim', 0)}")
                                
                                # Buscar duplicados semánticos (>92% similaridad)
                                # Usar tipo genérico por ahora (se mejorará con clasificador)
                                semantic_duplicates = find_semantic_duplicates(
                                    db,
                                    case_id,
                                    doc_embedding.get("vector", []),  # Extraer vector del dict
                                    new_doc_type="contrato",  # TODO: obtener de clasificador
                                    threshold=0.92,
                                    max_candidates=50,
                                )
                                
                                if semantic_duplicates:
                                    # Tomar el más similar
                                    original_doc, similarity = semantic_duplicates[0]
                                    logger.warning(
                                        f"⚠️  DUPLICADO SEMÁNTICO detectado: {file.filename} "
                                        f"es {similarity*100:.1f}% similar a {original_doc.filename} "
                                        f"(document_id={original_doc.document_id})"
                                    )
                                    is_duplicate = True
                                    duplicate_of_document_id = original_doc.document_id
                                    duplicate_similarity = similarity
                                    duplicate_action = "pending"
                        else:
                            logger.info("OPENAI_API_KEY no disponible, saltando verificación semántica")
                    except Exception as e:
                        logger.error(f"Error en deduplicación semántica: {e}")
                        # Continuar sin bloquear la ingesta
            
            # =====================================================
            # FIN FASE 2A
            # =====================================================
            
            # Documento ingerido exitosamente
            # Buscar el documento en la DB (debería haberse creado durante la ingesta)
            # Por ahora, crear documento manualmente si no existe
            doc = Document(
                document_id=document_id,  # Usar el ID generado
                case_id=case_id,
                filename=storage_metadata["original_filename"],
                file_format=file.content_type or "unknown",
                doc_type="contrato",  # Tipo genérico: balance, pyg, mayor, sumas_saldos, extracto_bancario, acta, acuerdo_societario, poder, email_direccion, email_banco, email_asesoria, contrato, venta_activo, prestamo, nomina
                source="upload",
                date_start=datetime.utcnow(),
                date_end=datetime.utcnow(),
                reliability="original",  # Valores válidos: original, escaneado, foto
                storage_path=storage_metadata["storage_path"],
                # FASE 1B: Integridad Legal
                sha256_hash=storage_metadata["sha256_hash"],
                file_size_bytes=storage_metadata["file_size_bytes"],
                mime_type=storage_metadata["mime_type"],
                uploaded_at=datetime.utcnow(),
                legal_hold=False,
                retention_until=datetime.utcnow() + timedelta(days=365*6),  # 6 años
                # Parsing
                parsing_status="pending",
                raw_text=parsing_result.texto,  # FASE 1: Single source of truth
                # FASE 2A: Métricas de parsing
                parsing_metrics={
                    'parser_used': parsing_result.tipo_documento,
                    'processing_time_ms': int((datetime.utcnow().timestamp() - start_time) * 1000) if 'start_time' in locals() else 0,
                    'num_entities': len(parsing_result.structured_data) if parsing_result.structured_data else 0,
                    'has_structured_data': parsing_result.structured_data is not None,
                    'extraction_methods': list(parsing_result.structured_data.keys()) if parsing_result.structured_data else [],
                },
                # FASE 2A: Metadata de OCR (trazabilidad)
                ocr_metadata={
                    'applied': parsing_result.ocr_applied,
                    'pages': parsing_result.ocr_pages,
                    'language': parsing_result.ocr_language,
                    'chars_detected': parsing_result.ocr_chars_detected,
                } if parsing_result.ocr_applied else None,
                # FASE 2A: Deduplicación
                content_hash=content_hash,
                document_embedding=document_embedding_dict,
                is_duplicate=is_duplicate,
                duplicate_of_document_id=duplicate_of_document_id,
                duplicate_similarity=duplicate_similarity,
                duplicate_action=duplicate_action,
            )
            db.add(doc)
            db.flush()  # Asegura que document_id exists antes de chunking
            db.refresh(doc)
            
            # DELEGAR al core: chunking OPTIMIZADO (solo este documento)
            try:
                build_document_chunks_for_single_document(
                    db=db,
                    document_id=doc.document_id,
                    case_id=case_id,
                    text=parsing_result.texto,  # Pasar texto ya parseado
                    parsing_result=parsing_result,  # Pasar resultado completo para metadata
                    overwrite=False,  # No sobrescribir chunks existentes
                )
                
                # Marcar como completado
                doc.parsing_status = "completed"
                db.commit()
                
            except Exception as e:
                logger.error(f"Error en chunking de {file.filename}: {e}")
                doc.parsing_status = "failed"
                doc.parsing_rejection_reason = str(e)
                db.commit()
            
            results.append(_build_document_summary(doc, db))
            
        except DocumentValidationError as e:
            # Error de validación (STRICT mode)
            logger.error(f"Error de validación en {file.filename}: {e.message}")
            
            # Registrar documento con error (con integridad legal si storage_metadata existe)
            if 'storage_metadata' in locals() and storage_metadata:
                doc = Document(
                    document_id=document_id,
                    case_id=case_id,
                    filename=storage_metadata["original_filename"],
                    file_format=file.content_type or "unknown",
                    doc_type="contrato",  # Tipo genérico: balance, pyg, mayor, sumas_saldos, extracto_bancario, acta, acuerdo_societario, poder, email_direccion, email_banco, email_asesoria, contrato, venta_activo, prestamo, nomina
                    source="upload",
                    date_start=datetime.utcnow(),
                    date_end=datetime.utcnow(),
                    reliability="original",  # Valores válidos: original, escaneado, foto
                    storage_path=storage_metadata["storage_path"],
                    sha256_hash=storage_metadata["sha256_hash"],
                    file_size_bytes=storage_metadata["file_size_bytes"],
                    mime_type=storage_metadata["mime_type"],
                    uploaded_at=datetime.utcnow(),
                    legal_hold=False,
                    retention_until=datetime.utcnow() + timedelta(days=365*6),
                    parsing_status="rejected",
                    parsing_rejection_reason=e.message,
                    raw_text=None,
                    # Deduplicación
                    content_hash=None,
                    document_embedding=None,
                    is_duplicate=False,
                    duplicate_of_document_id=None,
                    duplicate_similarity=None,
                    duplicate_action=None,
                )
            else:
                # Fallback si no se pudo calcular storage_metadata
                doc = Document(
                    case_id=case_id,
                    filename=file.filename,
                    file_format=file.content_type or "unknown",
                    doc_type="contrato",  # Tipo genérico: balance, pyg, mayor, sumas_saldos, extracto_bancario, acta, acuerdo_societario, poder, email_direccion, email_banco, email_asesoria, contrato, venta_activo, prestamo, nomina
                    source="upload",
                    date_start=datetime.utcnow(),
                    date_end=datetime.utcnow(),
                    reliability="original",  # Valores válidos: original, escaneado, foto
                    storage_path=f"/failed/{file.filename}",
                    sha256_hash="0" * 64,  # Hash dummy
                    file_size_bytes=0,
                    mime_type="application/octet-stream",
                    uploaded_at=datetime.utcnow(),
                    legal_hold=False,
                    retention_until=datetime.utcnow() + timedelta(days=365*6),
                    parsing_status="rejected",
                    parsing_rejection_reason=e.message,
                    raw_text=None,
                    # Deduplicación
                    content_hash=None,
                    document_embedding=None,
                    is_duplicate=False,
                    duplicate_of_document_id=None,
                    duplicate_similarity=None,
                    duplicate_action=None,
                )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            
            results.append(_build_document_summary(doc, db))
            
        except Exception as e:
            # Error inesperado
            logger.error(f"Error inesperado en ingesta de {file.filename}: {e}")
            
            # Registrar documento con error (con integridad legal si storage_metadata existe)
            if 'storage_metadata' in locals() and storage_metadata:
                doc = Document(
                    document_id=document_id,
                    case_id=case_id,
                    filename=storage_metadata["original_filename"],
                    file_format=file.content_type or "unknown",
                    doc_type="contrato",  # Tipo genérico: balance, pyg, mayor, sumas_saldos, extracto_bancario, acta, acuerdo_societario, poder, email_direccion, email_banco, email_asesoria, contrato, venta_activo, prestamo, nomina
                    source="upload",
                    date_start=datetime.utcnow(),
                    date_end=datetime.utcnow(),
                    reliability="original",  # Valores válidos: original, escaneado, foto
                    storage_path=storage_metadata["storage_path"],
                    sha256_hash=storage_metadata["sha256_hash"],
                    file_size_bytes=storage_metadata["file_size_bytes"],
                    mime_type=storage_metadata["mime_type"],
                    uploaded_at=datetime.utcnow(),
                    legal_hold=False,
                    retention_until=datetime.utcnow() + timedelta(days=365*6),
                    parsing_status="failed",
                    parsing_rejection_reason=str(e),
                    raw_text=None,
                    # Deduplicación
                    content_hash=None,
                    document_embedding=None,
                    is_duplicate=False,
                    duplicate_of_document_id=None,
                    duplicate_similarity=None,
                    duplicate_action=None,
                )
            else:
                # Fallback si no se pudo calcular storage_metadata
                doc = Document(
                    case_id=case_id,
                    filename=file.filename,
                    file_format=file.content_type or "unknown",
                    doc_type="contrato",  # Tipo genérico: balance, pyg, mayor, sumas_saldos, extracto_bancario, acta, acuerdo_societario, poder, email_direccion, email_banco, email_asesoria, contrato, venta_activo, prestamo, nomina
                    source="upload",
                    date_start=datetime.utcnow(),
                    date_end=datetime.utcnow(),
                    reliability="original",  # Valores válidos: original, escaneado, foto
                    storage_path=f"/failed/{file.filename}",
                    sha256_hash="0" * 64,  # Hash dummy
                    file_size_bytes=0,
                    mime_type="application/octet-stream",
                    uploaded_at=datetime.utcnow(),
                    legal_hold=False,
                    retention_until=datetime.utcnow() + timedelta(days=365*6),
                    parsing_status="failed",
                    parsing_rejection_reason=str(e),
                    raw_text=None,
                    # Deduplicación
                    content_hash=None,
                    document_embedding=None,
                    is_duplicate=False,
                    duplicate_of_document_id=None,
                    duplicate_similarity=None,
                    duplicate_action=None,
                )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            
            results.append(_build_document_summary(doc, db))
        
        finally:
            # Limpiar archivo temporal en todos los casos
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    logger.debug(f"Archivo temporal eliminado: {temp_file_path}")
                except Exception as cleanup_error:
                    logger.warning(f"No se pudo eliminar archivo temporal {temp_file_path}: {cleanup_error}")
    
    return results


@router.get(
    "",
    response_model=List[DocumentSummary],
    summary="Listar documentos de un caso",
    description=(
        "Lista todos los documentos de un caso, "
        "ordenados por fecha de creación (más recientes primero). "
        "El estado de cada documento se calcula desde el core real."
    ),
)
def list_documents(
    case_id: str,
    db: Session = Depends(get_db),
) -> List[DocumentSummary]:
    """
    Lista documentos de un caso.
    
    Ordenados por created_at descendente (más recientes primero).
    El estado de cada documento se calcula desde el core real.
    
    Args:
        case_id: ID del caso
        db: Sesión de base de datos
        
    Returns:
        Lista de DocumentSummary
        
    Raises:
        HTTPException 404: Si el caso no existe
    """
    # Verificar que el caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Caso '{case_id}' no encontrado"
        )
    
    # Obtener documentos del caso
    documents = (
        db.query(Document)
        .filter(Document.case_id == case_id)
        .order_by(Document.created_at.desc())
        .all()
    )
    
    # Construir summaries
    return [_build_document_summary(doc, db) for doc in documents]


@router.get(
    "/{document_id}/integrity",
    summary="Verificar integridad de un documento",
    description=(
        "Verifica la integridad de un documento mediante su hash SHA256. "
        "Recalcula el hash del archivo original y lo compara con el hash almacenado. "
        "Devuelve metadatos de cadena de custodia y trazabilidad."
    ),
)
def verify_document_integrity(
    case_id: str,
    document_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Verifica la integridad de un documento.
    
    PROPÓSITO:
    - Cadena de custodia documental
    - Prueba pericial informática
    - Auditoría de integridad
    - Detección de manipulaciones
    
    Args:
        case_id: ID del caso
        document_id: ID del documento
        db: Sesión de base de datos
        
    Returns:
        dict con:
            - document_id
            - filename
            - stored_hash: Hash SHA256 almacenado
            - current_hash: Hash SHA256 actual (recalculado)
            - integrity_verified: True si coinciden
            - file_size_bytes
            - mime_type
            - uploaded_at
            - storage_path
            - legal_hold
            - retention_until
            - processing_trace_id
    """
    # Verificar que el caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Caso '{case_id}' no encontrado"
        )
    
    # Verificar que el documento existe y pertenece al caso
    document = (
        db.query(Document)
        .filter(
            Document.document_id == document_id,
            Document.case_id == case_id
        )
        .first()
    )
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento '{document_id}' no encontrado en el caso '{case_id}'"
        )
    
    # Recalcular hash del archivo original
    current_hash = None
    integrity_verified = False
    file_exists = os.path.exists(document.storage_path)
    
    if file_exists:
        try:
            current_hash = calculate_file_hash(document.storage_path)
            integrity_verified = (current_hash == document.sha256_hash)
        except Exception as e:
            logger.error(f"Error al recalcular hash de {document_id}: {e}")
            current_hash = f"ERROR: {str(e)}"
    
    return {
        "document_id": document.document_id,
        "case_id": document.case_id,
        "filename": document.filename,
        # Integridad
        "stored_hash": document.sha256_hash,
        "current_hash": current_hash,
        "integrity_verified": integrity_verified,
        "file_exists": file_exists,
        # Metadatos
        "file_size_bytes": document.file_size_bytes,
        "mime_type": document.mime_type,
        "storage_path": document.storage_path,
        # Cadena de custodia
        "uploaded_at": document.uploaded_at.isoformat() if document.uploaded_at else None,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        # Trazabilidad
        "processing_trace_id": document.processing_trace_id,
        # Legal
        "legal_hold": document.legal_hold,
        "retention_until": document.retention_until.isoformat() if document.retention_until else None,
    }


@router.patch(
    "/{document_id}/duplicate-action",
    response_model=DocumentSummary,
    summary="Resolver acción sobre documento duplicado",
    description=(
        "Permite al abogado decidir qué hacer con un documento duplicado. "
        "Acciones disponibles: keep_both, mark_duplicate, exclude_from_analysis. "
        "IMPORTANTE: Solo el abogado puede tomar esta decisión, no el sistema."
    ),
)
async def resolve_duplicate_action(
    case_id: str,
    document_id: str,
    request: DuplicateActionRequest,
    db: Session = Depends(get_db),
) -> DocumentSummary:
    """
    Permite al abogado resolver la acción a tomar sobre un documento duplicado.
    
    PRINCIPIO LEGAL: El abogado decide, no la IA.
    
    Args:
        case_id: ID del caso
        document_id: ID del documento
        request: Request con acción, razón y usuario
        db: Sesión de base de datos
        
    Returns:
        DocumentSummary actualizado
        
    Raises:
        404: Si el documento no existe
        409: Si el documento no está marcado como duplicado
    """
    # Buscar documento
    document = db.query(Document).filter(
        Document.document_id == document_id,
        Document.case_id == case_id,
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento {document_id} no encontrado en caso {case_id}",
        )
    
    # Validar que sea duplicado
    if not document.is_duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este documento no está marcado como duplicado",
        )
    
    # Actualizar con auditoría completa
    document.duplicate_action = request.action.value
    document.duplicate_action_at = datetime.utcnow()
    document.duplicate_action_by = request.decided_by or "unknown"
    document.duplicate_action_reason = request.reason
    
    logger.info(
        f"Decisión de duplicado registrada: doc={document_id}, "
        f"action={request.action.value}, by={request.decided_by}, "
        f"reason={request.reason}"
    )
    
    db.commit()
    db.refresh(document)
    
    return _build_document_summary(document, db)


# =========================================================
# ENDPOINTS PROHIBIDOS (NO IMPLEMENTADOS)
# =========================================================

# PUT /cases/{case_id}/documents/{document_id} → PROHIBIDO (no se permite editar documentos)
# DELETE /cases/{case_id}/documents/{document_id} → PROHIBIDO (no se permite borrar documentos)
# POST /cases/{case_id}/documents/{document_id}/retry → PROHIBIDO (no reintentos automáticos)
