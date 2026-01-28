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

import hashlib
import io
import os
import tempfile
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import DocumentValidationError
from app.core.logger import logger
from app.core.variables import EMBEDDING_MODEL
from app.models.case import Case
from app.models.document import (
    Document,
    calculate_file_hash,
    store_document_file,
)
from app.models.document_chunk import DocumentChunk
from app.models.document_summary import (
    DocumentStatus,
    DocumentSummary,
)
from app.models.duplicate_action import (
    DuplicateActionRequest,
    DuplicateDecisionResponse,
    DuplicatePairSummary,
)
from app.models.duplicate_audit import create_audit_entry
from app.models.duplicate_pair import DuplicatePair
from app.services.document_chunk_pipeline import (
    build_document_chunks_for_single_document,
)
from app.services.duplicate_cascade import (
    check_transitive_duplicates,
    invalidate_pairs_for_document,
)
from app.services.duplicate_validation import validate_batch_action, validate_duplicate_decision
from app.services.ingesta import ingerir_archivo
from app.services.ingestion_failfast import ValidationMode

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
    normalized = normalized.replace("\n", " ").replace("\r", "")

    # Remover espacios múltiples
    normalized = " ".join(normalized.split())

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
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def validate_and_build_embedding_dict(vector: list[float], model: str) -> dict:
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
        text = text[: max_chars // 2] + " ... " + text[-max_chars // 2 :]

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


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
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

    # Implementación pura-Python (sin NumPy) para evitar crashes nativos.
    if len(vec1) != len(vec2):
        return 0.0

    dot_product = 0.0
    norm_a_sq = 0.0
    norm_b_sq = 0.0
    for x, y in zip(vec1, vec2):
        x = float(x)
        y = float(y)
        dot_product += x * y
        norm_a_sq += x * x
        norm_b_sq += y * y

    if norm_a_sq == 0.0 or norm_b_sq == 0.0:
        return 0.0

    import math

    similarity = dot_product / (math.sqrt(norm_a_sq) * math.sqrt(norm_b_sq))
    return float(max(0.0, min(1.0, similarity)))


def find_semantic_duplicates(
    db: Session,
    case_id: str,
    new_embedding: list[float],
    new_doc_type: str,
    threshold: float = 0.92,
    max_candidates: int = 50,
) -> list[tuple[Document, float]]:
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
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.document_id).count()
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
        original_doc = (
            db.query(Document)
            .filter(Document.document_id == document.duplicate_of_document_id)
            .first()
        )
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
    response_model=list[DocumentSummary],
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
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> list[DocumentSummary]:
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
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado"
        )

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No se proporcionaron archivos"
        )

    results: list[DocumentSummary] = []

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
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=os.path.splitext(file.filename)[1]
            ) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name

            # 2. Calcular hash SHA256 (integridad y deduplicación)
            sha256_hash = calculate_file_hash(temp_file_path)
            logger.info(f"Hash SHA256 calculado para {file.filename}: {sha256_hash}")

            # 3. DEDUPLICACIÓN BINARIA (ANTES de parsear/almacenar)
            existing_doc = (
                db.query(Document)
                .filter(
                    Document.case_id == case_id,  # Mismo caso
                    Document.sha256_hash == sha256_hash,
                )
                .first()
            )

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
                original_filename=file.filename,  # Preservar nombre original
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
                    retention_until=datetime.utcnow() + timedelta(days=365 * 6),  # 6 años
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
                content_duplicate = (
                    db.query(Document)
                    .filter(
                        Document.case_id == case_id,
                        Document.content_hash == content_hash,
                    )
                    .first()
                )

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
                                parsing_result.texto, openai_client
                            )

                            if doc_embedding:
                                # Ya es dict validado con contrato fijo
                                document_embedding_dict = doc_embedding
                                logger.info(
                                    f"Embedding generado: dim={doc_embedding.get('dim', 0)}"
                                )

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
                            logger.info(
                                "OPENAI_API_KEY no disponible, saltando verificación semántica"
                            )
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
                retention_until=datetime.utcnow() + timedelta(days=365 * 6),  # 6 años
                # Parsing
                parsing_status="pending",
                raw_text=parsing_result.texto,  # FASE 1: Single source of truth
                # FASE 2A: Métricas de parsing
                parsing_metrics={
                    "parser_used": parsing_result.tipo_documento,
                    "processing_time_ms": int((datetime.utcnow().timestamp() - start_time) * 1000),
                    "num_entities": len(parsing_result.structured_data)
                    if parsing_result.structured_data
                    else 0,
                    "has_structured_data": parsing_result.structured_data is not None,
                    "extraction_methods": list(parsing_result.structured_data.keys())
                    if parsing_result.structured_data
                    else [],
                },
                # FASE 2A: Metadata de OCR (trazabilidad)
                ocr_metadata={
                    "applied": parsing_result.ocr_applied,
                    "pages": parsing_result.ocr_pages,
                    "language": parsing_result.ocr_language,
                    "chars_detected": parsing_result.ocr_chars_detected,
                }
                if parsing_result.ocr_applied
                else None,
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
            if "storage_metadata" in locals() and storage_metadata:
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
                    retention_until=datetime.utcnow() + timedelta(days=365 * 6),
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
                    retention_until=datetime.utcnow() + timedelta(days=365 * 6),
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
            if "storage_metadata" in locals() and storage_metadata:
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
                    retention_until=datetime.utcnow() + timedelta(days=365 * 6),
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
                    retention_until=datetime.utcnow() + timedelta(days=365 * 6),
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
                    logger.warning(
                        f"No se pudo eliminar archivo temporal {temp_file_path}: {cleanup_error}"
                    )

    return results


@router.get(
    "",
    response_model=list[DocumentSummary],
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
) -> list[DocumentSummary]:
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
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado"
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
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado"
        )

    # Verificar que el documento existe y pertenece al caso
    document = (
        db.query(Document)
        .filter(Document.document_id == document_id, Document.case_id == case_id)
        .first()
    )

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento '{document_id}' no encontrado en el caso '{case_id}'",
        )

    # Recalcular hash del archivo original
    current_hash = None
    integrity_verified = False
    file_exists = os.path.exists(document.storage_path)

    if file_exists:
        try:
            current_hash = calculate_file_hash(document.storage_path)
            integrity_verified = current_hash == document.sha256_hash
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
        "retention_until": document.retention_until.isoformat()
        if document.retention_until
        else None,
    }


@router.patch(
    "/{document_id}/duplicate-action",
    response_model=DuplicateDecisionResponse,
    summary="Resolver acción sobre documento duplicado CON LOCK OPTIMISTA",
    description=(
        "Permite al abogado decidir qué hacer con un documento duplicado. "
        "CRÍTICO: Devuelve estado COMPLETO del par con decision_version. "
        "Acciones disponibles: keep_both, mark_duplicate, exclude_from_analysis."
    ),
)
async def resolve_duplicate_action(
    case_id: str,
    document_id: str,
    request: DuplicateActionRequest,
    expected_version: int = Query(0, description="Versión esperada para control optimista"),
    db: Session = Depends(get_db),
) -> DuplicateDecisionResponse:
    """
    Resuelve decisión sobre duplicado con blindaje completo.

    CRÍTICO: Backend soberano con:
    - Lock optimista (expected_version)
    - Validaciones DURAS
    - Auditoría append-only
    - Snapshot para rollback
    - Response con estado COMPLETO del par

    Args:
        case_id: ID del caso
        document_id: ID del documento
        request: Request con acción, razón y usuario
        expected_version: Versión esperada del par (control concurrencia)
        db: Sesión de base de datos

    Returns:
        DuplicateDecisionResponse con estado del par actualizado (incluye decision_version)

    Raises:
        404: Documento o par no encontrado
        409: Conflicto de concurrencia (otro usuario modificó el par)
        422: Validación falló
    """
    # 1. Buscar el par donde participa este documento
    pair = (
        db.query(DuplicatePair)
        .filter(
            DuplicatePair.case_id == case_id,
            (DuplicatePair.doc_a_id == document_id) | (DuplicatePair.doc_b_id == document_id),
        )
        .first()
    )

    if not pair:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró par de duplicados para documento {document_id}",
        )

    # 2. VALIDACIONES DURAS (backend soberano)
    try:
        validate_duplicate_decision(
            pair=pair,
            action=request.action.value,
            reason=request.reason or "",
            user=request.decided_by or "unknown",
            db=db,
            allow_override=False,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "VALIDATION_FAILED", "message": str(e)},
        )

    # 3. LOCK OPTIMISTA (control concurrencia)
    if pair.decision_version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "CONCURRENT_MODIFICATION",
                "message": "Otro usuario modificó este par. Recarga y reintenta.",
                "current_version": pair.decision_version,
                "expected_version": expected_version,
                "decided_by": pair.decided_by,
                "decided_at": pair.decided_at.isoformat() if pair.decided_at else None,
            },
        )

    # 4. SNAPSHOT antes de modificar (para auditoría)
    state_before = {
        "decision": pair.decision,
        "decision_version": pair.decision_version,
        "decided_by": pair.decided_by,
        "decided_at": pair.decided_at.isoformat() if pair.decided_at else None,
        "decision_reason": pair.decision_reason,
        "doc_a_id": pair.doc_a_id,
        "doc_b_id": pair.doc_b_id,
        "similarity": pair.similarity,
    }

    # 5. Aplicar cambio al PAR
    pair.snapshot_before_decision = state_before
    pair.decision = request.action.value
    pair.decided_by = request.decided_by or "unknown"
    pair.decided_at = datetime.utcnow()
    pair.decision_reason = request.reason
    pair.decision_version += 1  # ✅ INCREMENTAR VERSIÓN

    # 6. AUDITORÍA APPEND-ONLY (antes de commit)
    state_after = {
        "decision": pair.decision,
        "decision_version": pair.decision_version,
        "decided_by": pair.decided_by,
        "decided_at": pair.decided_at.isoformat(),
        "decision_reason": pair.decision_reason,
        "doc_a_id": pair.doc_a_id,
        "doc_b_id": pair.doc_b_id,
        "similarity": pair.similarity,
    }

    audit_entry = create_audit_entry(
        pair_id=pair.pair_id,
        case_id=case_id,
        state_before=state_before,
        state_after=state_after,
        decided_by=request.decided_by or "unknown",
        decision=request.action.value,
        reason=request.reason or "",
        pair_version=pair.decision_version,
        ip_address=None,  # TODO: extraer del request
        user_agent=None,
    )
    db.add(audit_entry)

    # 7. Sincronizar con Document (sistema legacy temporalmente)
    document = db.query(Document).filter(Document.document_id == document_id).first()

    if document:
        document.duplicate_action = request.action.value
        document.duplicate_action_reason = request.reason
        document.duplicate_action_by = request.decided_by
        document.duplicate_action_at = datetime.utcnow()

    # 8. Commit atómico
    try:
        db.commit()
        db.refresh(pair)
        if document:
            db.refresh(document)

        logger.info(
            f"[DUPLICATE] Decisión registrada: pair={pair.pair_id}, "
            f"doc={document_id}, action={request.action.value}, "
            f"by={request.decided_by}, version={pair.decision_version}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"[DUPLICATE] Error guardando decisión: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error guardando decisión: {str(e)}",
        )

    # ✅ NUEVO RETURN: Estado completo del par con decision_version
    return DuplicateDecisionResponse(
        pair_id=pair.pair_id,
        decision=pair.decision,
        decision_version=pair.decision_version,  # ✅ CRÍTICO para próxima operación
        decided_at=pair.decided_at,
        decided_by=pair.decided_by,
        decision_reason=pair.decision_reason or "",
        doc_a_id=pair.doc_a_id,
        doc_b_id=pair.doc_b_id,
        affected_documents=[pair.doc_a_id, pair.doc_b_id],
        similarity=pair.similarity,
        duplicate_type=pair.duplicate_type or "semantic",
        document_summary=_build_document_summary(document, db).__dict__ if document else None,
    )


@router.post(
    "/duplicates/simulate-batch",
    summary="SIMULAR batch action sin aplicar (seguro nuclear)",
    description=(
        "Simula el impacto de una acción batch sin aplicarla realmente. "
        "CRÍTICO: Muestra warnings, count de pares afectados, y decisiones previas que serían sobrescritas."
    ),
)
async def simulate_batch_action(
    case_id: str,
    action: str,
    reason: str,
    pair_ids: list[str],
    user: str,
    db: Session = Depends(get_db),
):
    """
    Endpoint de simulación para batch actions.

    CRÍTICO: NUNCA aplica cambios, solo simula.

    Args:
        case_id: ID del caso
        action: Acción a simular (keep_both/mark_duplicate/exclude_from_analysis)
        reason: Razón común
        pair_ids: Lista de pair_ids a afectar
        user: Usuario solicitante
        db: Sesión de base de datos

    Returns:
        Dict con:
        - total_pairs: Pares que se procesarían
        - warnings: Lista de warnings críticos
        - decisions_overwritten: Cuántas decisiones previas se sobrescribirían
        - safe_to_proceed: bool (false si hay warnings críticos)
        - impact_summary: Resumen humano del impacto
    """
    # Buscar pares
    pairs = (
        db.query(DuplicatePair)
        .filter(DuplicatePair.case_id == case_id, DuplicatePair.pair_id.in_(pair_ids))
        .all()
    )

    if not pairs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No se encontraron pares con esos IDs"
        )

    # Llamar validador batch (backend soberano)
    try:
        simulation = validate_batch_action(
            pairs=pairs, action=action, reason=reason, user=user, db=db
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "VALIDATION_FAILED", "message": str(e)},
        )

    logger.info(
        f"[BATCH SIMULATION] user={user}, case={case_id}, "
        f"pairs={len(pairs)}, action={action}, "
        f"safe={simulation['safe_to_proceed']}"
    )

    return simulation


@router.post(
    "/{document_id}/exclude",
    summary="Excluir documento del análisis (soft-delete + cascade)",
    description=(
        "CRÍTICO: Soft-delete del documento + invalidación de pares relacionados. "
        "Totalmente reversible con snapshot. PUNTO 3: Invalidación en cascada."
    ),
)
async def exclude_document_from_analysis(
    case_id: str,
    document_id: str,
    reason: str = Query(..., min_length=10, description="Razón obligatoria (auditoría legal)"),
    excluded_by: str = Query(..., description="Usuario que excluye"),
    db: Session = Depends(get_db),
):
    """
    Excluye documento y dispara invalidación en cascada.

    CRÍTICO: Auditoría completa de:
    - Soft-delete del documento
    - Invalidación de todos los pares relacionados (A-B, B-C → ambos invalidados)
    - Warnings de decisiones previas sobrescritas

    Escenario típico:
    - A ⇄ B
    - B ⇄ C
    - Usuario excluye B
    - Resultado: Pares A-B y B-C invalidados automáticamente

    Args:
        case_id: ID del caso
        document_id: ID del documento a excluir
        reason: Razón de la exclusión (mínimo 10 chars)
        excluded_by: Usuario que realiza la exclusión
        db: Sesión de base de datos

    Returns:
        Dict con:
        - status: "excluded"
        - document_id
        - excluded_at
        - cascade_result: pares invalidados, warnings, documentos afectados
        - snapshot: estado antes de excluir (para rollback)
    """
    # 1. Buscar documento
    document = (
        db.query(Document)
        .filter(Document.document_id == document_id, Document.case_id == case_id)
        .first()
    )

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Documento {document_id} no encontrado"
        )

    # Validar que no esté ya excluido
    if document.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Documento ya fue excluido el {document.deleted_at.isoformat()} por {document.deleted_by}",
        )

    # 2. Snapshot antes de excluir (para rollback)
    snapshot = {
        "document_id": document.document_id,
        "filename": document.filename,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "deleted_at": document.deleted_at.isoformat() if document.deleted_at else None,
        "is_duplicate": document.is_duplicate,
        "duplicate_action": document.duplicate_action,
        "duplicate_of_document_id": document.duplicate_of_document_id,
        "sha256_hash": document.sha256_hash,
        "content_hash": document.content_hash,
    }

    # 3. Soft-delete del documento
    document.deleted_at = datetime.utcnow()
    document.deleted_by = excluded_by
    document.deletion_reason = reason
    document.snapshot_before_deletion = snapshot

    # 4. INVALIDACIÓN EN CASCADA (PUNTO 3 CRÍTICO)
    cascade_result = invalidate_pairs_for_document(
        document_id=document_id, case_id=case_id, reason=reason, invalidated_by=excluded_by, db=db
    )

    # 5. Detectar transitivos potenciales (informativo)
    transitive = check_transitive_duplicates(document_id=document_id, case_id=case_id, db=db)

    # 6. Commit
    try:
        db.commit()

        logger.info(
            f"[EXCLUDE] Documento {document_id} excluido. "
            f"Pares invalidados: {len(cascade_result.invalidated_pairs)}, "
            f"Transitivos detectados: {len(transitive)}"
        )

        result = {
            "status": "excluded",
            "document_id": document_id,
            "filename": document.filename,
            "excluded_at": document.deleted_at.isoformat(),
            "excluded_by": excluded_by,
            "reason": reason,
            "cascade_result": cascade_result.to_dict(),
            "transitive_duplicates_detected": len(transitive),
            "snapshot": snapshot,
        }

        # Añadir warnings al response
        if cascade_result.warnings:
            result["warnings"] = cascade_result.warnings

        return result

    except Exception as e:
        db.rollback()
        logger.error(f"[EXCLUDE] Error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/duplicates",
    response_model=list[DuplicatePairSummary],
    summary="Lista todos los duplicados detectados del caso",
    description=(
        "Retorna lista de pares de documentos duplicados del caso. "
        "Para cada par incluye información de ambos documentos, "
        "tipo de duplicado, similitud y estado de la decisión del abogado."
    ),
)
async def list_duplicate_pairs(
    case_id: str,
    include_invalidated: bool = Query(False, description="Incluir pares invalidados por cascade"),
    db: Session = Depends(get_db),
) -> list[DuplicatePairSummary]:
    """
    Lista pares de duplicados desde tabla PERSISTENTE duplicate_pairs.

    CRÍTICO: Lee de duplicate_pairs, NO calcula dinámicamente.
    PUNTO 3: Por defecto EXCLUYE pares invalidados en cascada.

    Args:
        case_id: ID del caso
        include_invalidated: Si True, incluye pares invalidados (default: False)
        db: Sesión de base de datos

    Returns:
        Lista de pares con metadata enriquecida (sin invalidados por defecto)
    """
    # Verificar caso
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado"
        )

    # Query desde tabla persistente (EXCLUIR INVALIDADOS por defecto)
    query = db.query(DuplicatePair).filter(DuplicatePair.case_id == case_id)

    # ✅ PUNTO 3: Filtrar pares invalidados por defecto
    if not include_invalidated:
        query = query.filter(DuplicatePair.invalidated_at.is_(None))

    pairs_db = query.order_by(DuplicatePair.detected_at.desc()).all()

    result = []

    for pair in pairs_db:
        # Obtener documentos A y B
        doc_a = db.query(Document).filter(Document.document_id == pair.doc_a_id).first()
        doc_b = db.query(Document).filter(Document.document_id == pair.doc_b_id).first()

        if not doc_a or not doc_b:
            logger.warning(f"[DUPLICATE] Par {pair.pair_id} con docs faltantes")
            continue

        # Determinar tipo
        duplicate_type = pair.duplicate_type or (
            "exact" if pair.similarity >= 0.999 else "semantic"
        )

        result.append(
            DuplicatePairSummary(
                pair_id=pair.pair_id,
                original_id=doc_a.document_id,
                original_filename=doc_a.filename,
                original_date=doc_a.created_at,
                original_preview=(doc_a.raw_text or "")[:500],
                original_preview_offset=0,
                original_preview_location="start",
                original_total_length=len(doc_a.raw_text or ""),
                duplicate_id=doc_b.document_id,
                duplicate_filename=doc_b.filename,
                duplicate_date=doc_b.created_at,
                duplicate_preview=(doc_b.raw_text or "")[:500],
                duplicate_preview_offset=0,
                duplicate_preview_location="start",
                duplicate_total_length=len(doc_b.raw_text or ""),
                similarity=pair.similarity,
                similarity_method=pair.similarity_method,
                similarity_model=pair.similarity_model,
                duplicate_type=duplicate_type,
                action=pair.decision,
                action_reason=pair.decision_reason,
                action_by=pair.decided_by,
                action_at=pair.decided_at,
                expected_version=pair.decision_version,  # ✅ CRÍTICO para lock
            )
        )

    return result


@router.post(
    "/check-duplicates",
    summary="Verificar duplicados ANTES de subir",
    description=(
        "Verifica si los archivos a subir son duplicados de documentos existentes. "
        "Devuelve lista de archivos con información de duplicación. "
        "Permite al usuario decidir ANTES de subir si proceder o no."
    ),
)
async def check_duplicates_before_upload(
    case_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> list[dict]:
    """
    Verifica duplicados ANTES de subir archivos.

    Flujo:
    1. Calcula hash SHA256 de cada archivo
    2. Verifica duplicados binarios en BD
    3. Si no hay duplicado binario, parsea y verifica semántico (opcional)
    4. Retorna lista con info de duplicación para cada archivo

    Args:
        case_id: ID del caso
        files: Archivos a verificar
        db: Sesión de base de datos

    Returns:
        Lista de dicts con:
            - filename: Nombre original del archivo
            - file_size: Tamaño en bytes
            - is_duplicate: True si es duplicado
            - duplicate_type: "binary" o "semantic" o null
            - duplicate_of: Nombre del archivo original duplicado
            - duplicate_similarity: 1.0 para binario, <1.0 para semántico
            - should_upload: Recomendación (False si es duplicado)
    """
    # Verificar que el caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado"
        )

    results = []

    for file in files:
        temp_file_path = None
        try:
            # Leer contenido
            content = await file.read()

            if not content:
                results.append(
                    {
                        "filename": file.filename,
                        "file_size": 0,
                        "is_duplicate": False,
                        "duplicate_type": None,
                        "duplicate_of": None,
                        "duplicate_similarity": None,
                        "should_upload": False,
                        "error": "Archivo vacío",
                    }
                )
                continue

            # Guardar temporalmente para calcular hash
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=os.path.splitext(file.filename)[1]
            ) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name

            # Calcular hash SHA256
            sha256_hash = calculate_file_hash(temp_file_path)

            # Verificar duplicado BINARIO
            existing_doc = (
                db.query(Document)
                .filter(Document.case_id == case_id, Document.sha256_hash == sha256_hash)
                .first()
            )

            if existing_doc:
                # DUPLICADO BINARIO EXACTO
                results.append(
                    {
                        "filename": file.filename,
                        "file_size": len(content),
                        "is_duplicate": True,
                        "duplicate_type": "binary",
                        "duplicate_of": existing_doc.filename,
                        "duplicate_similarity": 1.0,
                        "should_upload": False,
                        "message": f"Este archivo es idéntico a '{existing_doc.filename}' ya subido.",
                    }
                )
            else:
                # No es duplicado binario
                results.append(
                    {
                        "filename": file.filename,
                        "file_size": len(content),
                        "is_duplicate": False,
                        "duplicate_type": None,
                        "duplicate_of": None,
                        "duplicate_similarity": None,
                        "should_upload": True,
                        "message": "Archivo nuevo, listo para subir.",
                    }
                )

        except Exception as e:
            logger.error(f"Error verificando duplicado de {file.filename}: {e}")
            results.append(
                {
                    "filename": file.filename,
                    "file_size": 0,
                    "is_duplicate": False,
                    "duplicate_type": None,
                    "duplicate_of": None,
                    "duplicate_similarity": None,
                    "should_upload": True,
                    "error": str(e),
                }
            )

        finally:
            # Limpiar archivo temporal
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(
                        f"No se pudo eliminar archivo temporal {temp_file_path}: {cleanup_error}"
                    )

            # IMPORTANTE: Resetear el cursor del archivo para que pueda leerse de nuevo
            await file.seek(0)

    return results


# =========================================================
# ENDPOINTS PROHIBIDOS (NO IMPLEMENTADOS)
# =========================================================

# PUT /cases/{case_id}/documents/{document_id} → PROHIBIDO (no se permite editar documentos)
# DELETE /cases/{case_id}/documents/{document_id} → PROHIBIDO (no se permite borrar documentos)
# POST /cases/{case_id}/documents/{document_id}/retry → PROHIBIDO (no reintentos automáticos)
