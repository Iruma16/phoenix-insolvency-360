from __future__ import annotations

import os
from pathlib import Path
from sqlalchemy.orm import Session

# Modelos
from app.models.document import Document
from app.models.document_chunk import DocumentChunk

# Chunker con metadata completa de trazabilidad
from app.services.chunker import chunk_text_with_metadata

# Ingesta de archivos (PDF, DOCX, TXT)
from app.services.ingesta import ingerir_archivo, ParsingResult

# Validación de parsing
from app.services.document_parsing_validation import ParsingStatus

# Logger
from app.core.logger import logger


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
    documents = (
        db.query(Document)
        .filter(Document.case_id == case_id)
        .all()
    )

    if not documents:
        print("[PUNTO 2] No hay documentos para este caso")
        return

    print(f"[INFO] Documentos encontrados: {len(documents)}")

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
            print(
                f"[SKIP] Documento ya procesado "
                f"({existing_count} chunks existentes)"
            )
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
                import pandas as pd
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
        tipo_doc = parsing_result.tipo_documento if isinstance(result, ParsingResult) else "txt"
        
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
        print(f"[INFO] Estrategia de chunking: {chunks_with_meta[0].chunking_strategy if chunks_with_meta else 'N/A'}")

        # --------------------------------------------------
        # 2.6 Persistir chunks en BBDD con metadata OBLIGATORIA
        # --------------------------------------------------
        # REGLA 1: Metadata obligatoria por chunk (BLOQUEANTE)
        from app.models.document_chunk import generate_deterministic_chunk_id
        
        for idx, chunk_meta in enumerate(chunks_with_meta):
            # VALIDACIÓN BLOQUEANTE 1: Offsets obligatorios
            if chunk_meta.start_char is None or chunk_meta.end_char is None:
                logger.error(
                    f"[CHUNKING] ❌ ERROR BLOQUEANTE: Chunk {idx} sin offsets. "
                    f"doc_id={doc.document_id}"
                )
                raise RuntimeError(
                    f"REGLA 1 VIOLADA: Chunk sin offsets obligatorios. "
                    f"doc_id={doc.document_id}, chunk_index={idx}"
                )
            
            # VALIDACIÓN BLOQUEANTE 2: Contenido no vacío
            if not chunk_meta.content or not chunk_meta.content.strip():
                logger.error(
                    f"[CHUNKING] ❌ ERROR BLOQUEANTE: Chunk {idx} vacío. "
                    f"doc_id={doc.document_id}"
                )
                raise RuntimeError(
                    f"REGLA 1 VIOLADA: Chunk con contenido vacío. "
                    f"doc_id={doc.document_id}, chunk_index={idx}"
                )
            
            # VALIDACIÓN BLOQUEANTE 3: Offsets consistentes
            if chunk_meta.start_char >= chunk_meta.end_char:
                logger.error(
                    f"[CHUNKING] ❌ ERROR BLOQUEANTE: Offsets inconsistentes en chunk {idx}. "
                    f"start={chunk_meta.start_char}, end={chunk_meta.end_char}"
                )
                raise RuntimeError(
                    f"REGLA 2 VIOLADA: start_char >= end_char. "
                    f"doc_id={doc.document_id}, chunk_index={idx}"
                )
            
            # VALIDACIÓN BLOQUEANTE 4: Offsets dentro del rango del texto
            if chunk_meta.end_char > len(text):
                logger.error(
                    f"[CHUNKING] ❌ ERROR BLOQUEANTE: Offset fuera de rango en chunk {idx}. "
                    f"end_char={chunk_meta.end_char}, len(text)={len(text)}"
                )
                raise RuntimeError(
                    f"REGLA 2 VIOLADA: Offset fuera de rango del texto original. "
                    f"doc_id={doc.document_id}, chunk_index={idx}"
                )
            
            # VALIDACIÓN BLOQUEANTE 5: Verificar que offsets mapean correctamente
            reconstructed = text[chunk_meta.start_char:chunk_meta.end_char]
            if reconstructed != chunk_meta.content:
                logger.error(
                    f"[CHUNKING] ❌ ERROR BLOQUEANTE: Offsets no mapean al contenido en chunk {idx}. "
                    f"Esperado: {len(chunk_meta.content)} chars, "
                    f"Reconstruido: {len(reconstructed)} chars"
                )
                raise RuntimeError(
                    f"REGLA 2 VIOLADA: texto_original[start:end] != chunk.content. "
                    f"doc_id={doc.document_id}, chunk_index={idx}. "
                    f"Offsets NO trazables al texto original."
                )
            
            # Generar chunk_id DETERMINISTA (CORRECCIÓN)
            chunk_id = generate_deterministic_chunk_id(
                case_id=case_id,
                doc_id=doc.document_id,
                chunk_index=idx,
                start_char=chunk_meta.start_char,
                end_char=chunk_meta.end_char,
            )
            
            db.add(
                DocumentChunk(
                    chunk_id=chunk_id,  # DETERMINISTA
                    document_id=doc.document_id,
                    case_id=case_id,
                    chunk_index=idx,
                    content=chunk_meta.content,
                    # REGLA 2: Offsets reales en texto original (VALIDADOS)
                    start_char=chunk_meta.start_char,
                    end_char=chunk_meta.end_char,
                    # REGLA 4: Page y section_hint pueden ser NULL
                    page=chunk_meta.page,
                    section_hint=chunk_meta.section_hint,
                    # REGLA 3: Estrategia aplicada
                    chunking_strategy=chunk_meta.chunking_strategy,
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
