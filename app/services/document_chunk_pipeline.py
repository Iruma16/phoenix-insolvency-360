from __future__ import annotations

import os
from pathlib import Path
from sqlalchemy.orm import Session

# Modelos
from app.models.document import Document
from app.models.document_chunk import DocumentChunk

# Chunker "tonto": SOLO divide texto
from app.services.chunker import chunk_text

# Ingesta de archivos (PDF, DOCX, TXT)
from app.services.ingesta import ingerir_archivo


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
        # 2.1 Validar que el archivo existe
        # --------------------------------------------------
        if not doc.storage_path or not os.path.exists(doc.storage_path):
            print("[ERROR] El archivo no existe en disco. Se omite.")
            continue

        # --------------------------------------------------
        # 2.2 Comprobar si ya existen chunks
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
        # 2.3 Leer el archivo usando el sistema de ingesta
        # (detecta automáticamente PDF, DOCX, TXT, etc.)
        # --------------------------------------------------
        try:
            # Detectar formato del archivo
            file_extension = Path(doc.storage_path).suffix.lower()
            
            # Usar el sistema de ingesta para leer el archivo
            # ingerir_archivo puede recibir una ruta o un stream
            result = ingerir_archivo(doc.storage_path, doc.filename)
            
            if result is None:
                print("[ERROR] El sistema de ingesta no pudo procesar el archivo")
                continue
            
            # Si es un DataFrame (CSV/Excel), convertirlo a texto
            if isinstance(result, str):
                text = result
            else:
                # Para DataFrames, convertirlos a texto (tabla)
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
        # 2.4 Aplicar chunking
        # --------------------------------------------------
        chunks = chunk_text(text)

        print(f"[OK] Chunks generados: {len(chunks)}")

        # --------------------------------------------------
        # 2.5 Persistir chunks en BBDD
        # --------------------------------------------------
        for idx, chunk in enumerate(chunks):
            db.add(
                DocumentChunk(
                    document_id=doc.document_id,
                    case_id=case_id,
                    chunk_index=idx,
                    content=chunk,
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
