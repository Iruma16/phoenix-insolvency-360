from __future__ import annotations

import os

from sqlalchemy.orm import Session

# Logger
from app.core.logger import logger

# Modelos
from app.models.document import Document
from app.models.document_chunk import DocumentChunk, ExtractionMethod

# Chunker con metadata completa de trazabilidad
from app.services.chunker import chunk_text_with_metadata

# Validación de parsing
from app.services.document_parsing_validation import ParsingStatus

# Ingesta de archivos (PDF, DOCX, TXT)
from app.services.ingesta import ParsingResult, ingerir_archivo

# =========================================================
# PASO 2 — PIPELINE DE CREACIÓN DE DOCUMENT CHUNKS
# =========================================================
#
# Este pipeline se encarga EXCLUSIVAMENTE de:
# - Leer documentos desde disco (storage_path)
# - Convertirlos en texto
# - Dividir el texto en chunks
# - Guardar esos chunks en la tabla DocumentChunk
#
# NO:
# - Genera embeddings
# - Hace RAG
# - Llama a LLMs
#
# Es el puente entre:
#   Document  →  DocumentChunk
#
# =========================================================

MIN_CHUNKABLE_TEXT_LEN = 100  # docs muy cortos: 1 chunk mínimo vs ruido

def build_document_chunks_for_case(
    db: Session,
    *,
    case_id: str,
    overwrite: bool = False,
) -> None:
    """
    Ejecuta el PASO 2 del pipeline completo.

    Parámetros
    ----------
    db : Session
        Sesión activa de SQLAlchemy.
    case_id : str
        Identificador del caso a procesar.
    overwrite : bool
        - False (default): NO reprocesa documentos que ya tengan chunks.
        - True           : Borra los chunks existentes y los regenera.
    """

    print("--------------------------------------------------")
    print("[PUNTO 2] Inicio creación de DocumentChunks")
    print(f"[INFO] case_id   : {case_id}")
    print(f"[INFO] overwrite : {overwrite}")

    # --------------------------------------------------
    # 1️⃣ Cargar documentos del caso
    # --------------------------------------------------
    from sqlalchemy import or_

    documents = (
        db.query(Document)
        .filter(
            Document.case_id == case_id,
            # FASE 2A: Excluir documentos duplicados marcados para exclusión
            or_(
                Document.duplicate_action.is_(None),
                Document.duplicate_action == "pending",
                Document.duplicate_action == "keep_both",
            ),
        )
        .all()
    )

    if not documents:
        print("[PUNTO 2] No hay documentos para este caso (o todos excluidos)")
        return

    print(f"[INFO] Documentos encontrados (incluidos): {len(documents)}")

    # --------------------------------------------------
    # 2️⃣ Procesar documento a documento
    # --------------------------------------------------
    for doc in documents:
        print("==================================================")
        print(f"[DOCUMENTO] document_id={doc.document_id}")
        print(f"[INFO] Ruta archivo: {doc.storage_path}")

        # --------------------------------------------------
        # 2.1 VALIDACIÓN BLOQUEANTE: Solo procesar docs PARSED_OK
        # --------------------------------------------------
        # REGLA: NO chunk, NO embeddings para documentos PARSED_INVALID
        if doc.parsing_status == ParsingStatus.PARSED_INVALID.value:
            logger.warning(
                f"[CHUNKING] ❌ Documento omitido (PARSED_INVALID): {doc.filename}. "
                f"Motivo: {doc.parsing_rejection_reason or 'UNKNOWN'}"
            )
            print(f"[SKIP] Documento PARSED_INVALID omitido: {doc.filename}")
            continue

        # Si no tiene parsing_status, advertir pero continuar (compatibilidad con docs antiguos)
        if not doc.parsing_status:
            logger.warning(
                f"[CHUNKING] ⚠️  Documento sin parsing_status: {doc.filename}. "
                "Esto indica un documento antiguo o ingesta sin validación. "
                "Continuando por compatibilidad."
            )

        # --------------------------------------------------
        # 2.2 Validar que el archivo existe
        # --------------------------------------------------
        if not doc.storage_path or not os.path.exists(doc.storage_path):
            print("[ERROR] El archivo no existe en disco. Se omite.")
            continue

        # --------------------------------------------------
        # 2.3 Comprobar si ya existen chunks
        # --------------------------------------------------
        existing_count = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.case_id == case_id,
                DocumentChunk.document_id == doc.document_id,
            )
            .count()
        )

        if existing_count > 0 and not overwrite:
            print(f"[SKIP] Documento ya procesado " f"({existing_count} chunks existentes)")
            continue

        # Si overwrite=True, borramos los chunks antiguos
        if existing_count > 0 and overwrite:
            print(f"[INFO] Eliminando {existing_count} chunks antiguos")
            (
                db.query(DocumentChunk)
                .filter(
                    DocumentChunk.case_id == case_id,
                    DocumentChunk.document_id == doc.document_id,
                )
                .delete()
            )
            db.commit()

        # --------------------------------------------------
        # 2.4 Leer el archivo usando el sistema de ingesta
        # (detecta automáticamente PDF, DOCX, TXT, etc.)
        # --------------------------------------------------
        try:
            # Usar el sistema de ingesta para leer el archivo
            result = ingerir_archivo(doc.storage_path, doc.filename)

            if result is None:
                print("[ERROR] El sistema de ingesta no pudo procesar el archivo")
                continue

            # Procesar resultado según el tipo
            if isinstance(result, ParsingResult):
                # Archivo de texto (PDF, DOCX, TXT, DOC)
                text = result.texto
            else:
                # DataFrame (CSV/Excel) - convertir a texto

                text = result.to_string()
                print(f"[INFO] Archivo CSV/Excel convertido a texto ({len(text)} caracteres)")

        except Exception as e:
            print("[ERROR] No se pudo leer el archivo")
            print(f"[ERROR] Detalle: {e}")
            import traceback

            traceback.print_exc()
            continue

        if not text or not text.strip():
            print("[WARN] El documento está vacío tras la lectura")
            continue

        # --------------------------------------------------
        # 2.5 Aplicar chunking con metadata completa
        # --------------------------------------------------
        # REGLA 3: Chunking consciente del tipo de documento
        tipo_doc = result.tipo_documento if isinstance(result, ParsingResult) else "txt"

        # CORRECCIÓN: Pasar page_offsets para PDFs
        page_mapping = None
        if isinstance(result, ParsingResult) and result.page_offsets:
            page_mapping = result.page_offsets
            print(f"[INFO] Usando mapeo de páginas: {len(page_mapping)} páginas")

        chunks_with_meta = chunk_text_with_metadata(
            text=text,
            tipo_documento=tipo_doc,
            page_mapping=page_mapping,
        )

        print(f"[OK] Chunks generados: {len(chunks_with_meta)}")
        print(
            f"[INFO] Estrategia de chunking: {chunks_with_meta[0].chunking_strategy if chunks_with_meta else 'N/A'}"
        )

        # --------------------------------------------------
        # 2.6 Persistir chunks en BBDD con metadata OBLIGATORIA
        # --------------------------------------------------
        # REGLA 1: Metadata obligatoria por chunk (BLOQUEANTE)
        from app.models.document_chunk import generate_deterministic_chunk_id

        for idx, chunk_meta in enumerate(chunks_with_meta):
            # VALIDACIÓN 1: Offsets obligatorios
            if chunk_meta.start_char is None or chunk_meta.end_char is None:
                logger.error(f"[CHUNKING] Chunk {idx} sin offsets. doc_id={doc.document_id}")
                raise RuntimeError(
                    f"Chunk sin offsets: doc_id={doc.document_id}, chunk_index={idx}"
                )

            # VALIDACIÓN 2: start_char debe ser >= 0
            if chunk_meta.start_char < 0:
                logger.error(
                    f"[CHUNKING] Chunk {idx} con start_char negativo. "
                    f"start_char={chunk_meta.start_char}, doc_id={doc.document_id}"
                )
                raise RuntimeError(
                    f"start_char negativo: doc_id={doc.document_id}, chunk_index={idx}"
                )

            # VALIDACIÓN 3: Contenido no vacío
            if not chunk_meta.content or not chunk_meta.content.strip():
                logger.error(f"[CHUNKING] Chunk {idx} vacío. doc_id={doc.document_id}")
                raise RuntimeError(f"Chunk vacío: doc_id={doc.document_id}, chunk_index={idx}")

            # VALIDACIÓN 4: Offsets consistentes
            if chunk_meta.start_char >= chunk_meta.end_char:
                logger.error(
                    f"[CHUNKING] Offsets inconsistentes en chunk {idx}. "
                    f"start={chunk_meta.start_char}, end={chunk_meta.end_char}"
                )
                raise RuntimeError(
                    f"Offsets inconsistentes: doc_id={doc.document_id}, chunk_index={idx}"
                )

            # VALIDACIÓN 5: Offsets dentro del rango del texto
            if chunk_meta.end_char > len(text):
                logger.error(
                    f"[CHUNKING] Offset fuera de rango en chunk {idx}. "
                    f"end_char={chunk_meta.end_char}, len(text)={len(text)}"
                )
                raise RuntimeError(
                    f"Offset fuera de rango: doc_id={doc.document_id}, chunk_index={idx}"
                )

            # Generar chunk_id DETERMINISTA (CORRECCIÓN)
            chunk_id = generate_deterministic_chunk_id(
                case_id=case_id,
                doc_id=doc.document_id,
                chunk_index=idx,
                start_char=chunk_meta.start_char,
                end_char=chunk_meta.end_char,
            )

            # Validar extraction_method
            if chunk_meta.extraction_method == ExtractionMethod.UNKNOWN:
                logger.error(
                    f"[CHUNKING] Chunk {idx} con extraction_method=UNKNOWN. "
                    f"doc_id={doc.document_id}"
                )
                raise RuntimeError(
                    f"extraction_method=UNKNOWN en chunk: "
                    f"doc_id={doc.document_id}, chunk_index={idx}"
                )

            db.add(
                DocumentChunk(
                    chunk_id=chunk_id,  # DETERMINISTA
                    document_id=doc.document_id,
                    case_id=case_id,
                    chunk_index=idx,
                    content=chunk_meta.content,
                    # Offsets en texto original
                    start_char=chunk_meta.start_char,
                    end_char=chunk_meta.end_char,
                    # extraction_method
                    extraction_method=chunk_meta.extraction_method.value,
                    # page_start/page_end (obligatorio para PDFs)
                    page_start=chunk_meta.page_start,
                    page_end=chunk_meta.page_end,
                    # content_hash (opcional)
                    content_hash=chunk_meta.content_hash,
                    # REGLA 4: section_hint puede ser NULL
                    section_hint=chunk_meta.section_hint,
                    # REGLA 3: Estrategia aplicada
                    chunking_strategy=chunk_meta.chunking_strategy,
                    # Tipo de contenido detectado
                    content_type=chunk_meta.content_type,
                )
            )

        try:
            db.commit()
            print("[OK] Chunks guardados correctamente")
        except Exception as e:
            db.rollback()
            print("[ERROR] Fallo al guardar chunks")
            print(f"[ERROR] Detalle: {e}")

    print("--------------------------------------------------")
    print("[PUNTO 2] Finalizado correctamente")


def build_document_chunks_for_single_document(
    db: Session,
    *,
    document_id: str,
    case_id: str,
    text: str = None,
    parsing_result: ParsingResult = None,
    overwrite: bool = False,
) -> None:
    """
    Versión OPTIMIZADA del PASO 2 que procesa UN SOLO DOCUMENTO.

    Usado durante el upload para evitar reprocesar todos los documentos del caso.

    Parámetros
    ----------
    db : Session
        Sesión activa de SQLAlchemy.
    document_id : str
        Identificador del documento a procesar.
    case_id : str
        Identificador del caso (para validación).
    text : str, optional
        Texto ya parseado (evita re-parsear desde disco).
    parsing_result : ParsingResult, optional
        Resultado del parsing original (para metadata).
    overwrite : bool
        - False (default): NO reprocesa si ya tiene chunks.
        - True           : Borra los chunks existentes y los regenera.
    """
    from app.models.document_chunk import generate_deterministic_chunk_id
    from app.services.document_parsing_validation import ParsingStatus

    print("--------------------------------------------------")
    print(f"[CHUNKING OPTIMIZADO] Procesando documento {document_id}")

    # Cargar el documento específico
    doc = (
        db.query(Document)
        .filter(
            Document.document_id == document_id,
            Document.case_id == case_id,
        )
        .first()
    )

    if not doc:
        print(f"[ERROR] Documento {document_id} no encontrado")
        return

    # Validación: Solo procesar docs PARSED_OK o sin parsing_status
    if doc.parsing_status == ParsingStatus.PARSED_INVALID.value:
        logger.warning(
            f"[CHUNKING] ❌ Documento omitido (PARSED_INVALID): {doc.filename}. "
            f"Motivo: {doc.parsing_rejection_reason or 'UNKNOWN'}"
        )
        print(f"[SKIP] Documento PARSED_INVALID omitido: {doc.filename}")
        return

    # Validar que el archivo existe
    if not doc.storage_path or not os.path.exists(doc.storage_path):
        print("[ERROR] El archivo no existe en disco. Se omite.")
        return

    # Comprobar si ya existen chunks
    existing_count = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.case_id == case_id,
            DocumentChunk.document_id == doc.document_id,
        )
        .count()
    )

    if existing_count > 0 and not overwrite:
        print(f"[SKIP] Documento ya procesado ({existing_count} chunks existentes)")
        return

    # Si overwrite=True, borramos los chunks antiguos
    if existing_count > 0 and overwrite:
        print(f"[INFO] Eliminando {existing_count} chunks antiguos")
        (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.case_id == case_id,
                DocumentChunk.document_id == doc.document_id,
            )
            .delete()
        )
        db.commit()

    # Leer el archivo usando el sistema de ingesta (solo si no tenemos texto pre-parseado)
    if text is None:
        try:
            result = ingerir_archivo(doc.storage_path, doc.filename)

            if result is None:
                print("[ERROR] El sistema de ingesta no pudo procesar el archivo")
                return

            # Procesar resultado según el tipo
            if isinstance(result, ParsingResult):
                text = result.texto
            else:
                # DataFrame (CSV/Excel) - convertir a texto

                text = result.to_string()
                print(f"[INFO] Archivo CSV/Excel convertido a texto ({len(text)} caracteres)")

        except Exception as e:
            print(f"[ERROR] No se pudo leer el archivo: {e}")
            import traceback

            traceback.print_exc()
            return
    else:
        print(f"[INFO] Usando texto pre-parseado ({len(text)} caracteres)")
        # Si tenemos parsing_result, usarlo; si no, asumir que es resultado del parsing original
        if parsing_result is None:
            # Crear un resultado básico para compatibilidad
            result = type(
                "obj", (object,), {"texto": text, "tipo_documento": "txt", "page_offsets": None}
            )()
        else:
            result = parsing_result

    if not text or not text.strip():
        print("[WARN] El documento está vacío tras la lectura")
        return

    # Aplicar chunking con metadata completa
    tipo_doc = result.tipo_documento if isinstance(result, ParsingResult) else "txt"

    # Skip documentos muy cortos (ruido) SOLO para tipos donde el chunking aporta poco.
    # Para email/imagen (OCR) queremos 1 chunk mínimo aunque el texto sea corto,
    # para que el documento no quede en pending con chunks_count=0.
    if len(text) < MIN_CHUNKABLE_TEXT_LEN and tipo_doc not in ("email", "image"):
        print(f"[SKIP] Documento muy corto ({len(text)} chars), omitiendo chunking")
        doc.parsing_status = "completed"
        db.commit()
        return

    page_mapping = None
    if isinstance(result, ParsingResult) and result.page_offsets:
        page_mapping = result.page_offsets
        print(f"[INFO] Usando mapeo de páginas: {len(page_mapping)} páginas")

    chunks_with_meta = chunk_text_with_metadata(
        text=text,
        tipo_documento=tipo_doc,
        page_mapping=page_mapping,
    )

    print(f"[OK] Chunks generados: {len(chunks_with_meta)}")

    # Persistir chunks en BBDD (OPTIMIZADO: batch insert)
    from datetime import datetime

    chunks_to_insert = []

    for idx, chunk_meta in enumerate(chunks_with_meta):
        # Validaciones
        if chunk_meta.start_char is None or chunk_meta.end_char is None:
            logger.error(f"[CHUNKING] Chunk {idx} sin offsets. doc_id={doc.document_id}")
            raise RuntimeError(f"Chunk sin offsets: doc_id={doc.document_id}, chunk_index={idx}")

        if chunk_meta.start_char < 0:
            logger.error(
                f"[CHUNKING] Chunk {idx} con start_char negativo. start_char={chunk_meta.start_char}"
            )
            raise RuntimeError(f"start_char negativo: doc_id={doc.document_id}, chunk_index={idx}")

        if not chunk_meta.content or not chunk_meta.content.strip():
            logger.error(f"[CHUNKING] Chunk {idx} vacío. doc_id={doc.document_id}")
            raise RuntimeError(f"Chunk vacío: doc_id={doc.document_id}, chunk_index={idx}")

        if chunk_meta.start_char >= chunk_meta.end_char:
            logger.error(
                f"[CHUNKING] Offsets inconsistentes en chunk {idx}. start={chunk_meta.start_char}, end={chunk_meta.end_char}"
            )
            raise RuntimeError(
                f"Offsets inconsistentes: doc_id={doc.document_id}, chunk_index={idx}"
            )

        if chunk_meta.end_char > len(text):
            logger.error(
                f"[CHUNKING] Offset fuera de rango en chunk {idx}. end_char={chunk_meta.end_char}, len(text)={len(text)}"
            )
            raise RuntimeError(
                f"Offset fuera de rango: doc_id={doc.document_id}, chunk_index={idx}"
            )

        # Generar chunk_id DETERMINISTA
        chunk_id = generate_deterministic_chunk_id(
            case_id=case_id,
            doc_id=doc.document_id,
            chunk_index=idx,
            start_char=chunk_meta.start_char,
            end_char=chunk_meta.end_char,
        )

        # Validar extraction_method
        if chunk_meta.extraction_method == ExtractionMethod.UNKNOWN:
            logger.error(
                f"[CHUNKING] Chunk {idx} con extraction_method=UNKNOWN. doc_id={doc.document_id}"
            )
            raise RuntimeError(
                f"extraction_method=UNKNOWN en chunk: doc_id={doc.document_id}, chunk_index={idx}"
            )

        # Añadir a lista para batch insert
        chunks_to_insert.append(
            DocumentChunk(
                chunk_id=chunk_id,
                document_id=doc.document_id,
                case_id=case_id,
                chunk_index=idx,
                content=chunk_meta.content,
                start_char=chunk_meta.start_char,
                end_char=chunk_meta.end_char,
                extraction_method=chunk_meta.extraction_method.value,
                page_start=chunk_meta.page_start,
                page_end=chunk_meta.page_end,
                content_hash=chunk_meta.content_hash,
                section_hint=chunk_meta.section_hint,
                chunking_strategy=chunk_meta.chunking_strategy,
                content_type=chunk_meta.content_type,
                created_at=datetime.utcnow(),  # Manual para bulk_save_objects
            )
        )

    # Inserción masiva (batch insert)
    try:
        db.bulk_save_objects(chunks_to_insert)
        db.commit()
        print(f"[OK] {len(chunks_to_insert)} chunks guardados correctamente (batch insert)")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Fallo al guardar chunks: {e}")
        raise

    print("--------------------------------------------------")
