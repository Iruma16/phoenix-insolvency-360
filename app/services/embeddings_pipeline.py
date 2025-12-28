from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import chromadb
from sqlalchemy import select
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from openai import OpenAI

from app.core.variables import CASES_VECTORSTORE_BASE, EMBEDDING_MODEL, EMBEDDING_BATCH_SIZE
from app.models.document_chunk import DocumentChunk


# =========================================================
# INIT — cargar entorno SIEMPRE
# =========================================================

load_dotenv()


# =========================================================
# VECTORSTORE (Chroma)
# =========================================================

def _case_vectorstore_path(case_id: str) -> Path:
    return CASES_VECTORSTORE_BASE / case_id / "vectorstore"


def get_case_collection(case_id: str):
    path = _case_vectorstore_path(case_id)
    path.mkdir(parents=True, exist_ok=True)

    print("--------------------------------------------------")
    print("[PUNTO 3] Inicializando vectorstore (Chroma)")
    print(f"[INFO] case_id: {case_id}")
    print(f"[INFO] path  : {path}")

    client = chromadb.PersistentClient(path=str(path))

    collection = client.get_or_create_collection(
        name="chunks",
        metadata={"case_id": case_id},
    )

    # 🔍 DEBUG REAL
    try:
        count = collection.count()
        print(f"[INFO] Embeddings actuales en colección: {count}")
    except Exception:
        print("[WARN] No se pudo obtener count() de Chroma")

    return collection


def _existing_ids(collection, ids: List[str]) -> set[str]:
    if not ids:
        return set()

    try:
        res = collection.get(ids=ids, include=[])
        return set(res.get("ids", []))
    except Exception as e:
        print("[ERROR] Fallo comprobando ids existentes en Chroma")
        print(f"[ERROR] Detalle: {e}")
        return set()


# =========================================================
# CHUNKS (SQL)
# =========================================================

def get_chunks_for_case(db: Session, case_id: str) -> list[DocumentChunk]:
    print("--------------------------------------------------")
    print("[PUNTO 3] Cargando chunks desde BBDD")
    print(f"[INFO] case_id: {case_id}")

    q = (
        select(DocumentChunk)
        .where(DocumentChunk.case_id == case_id)
        .order_by(
            DocumentChunk.document_id.asc(),
            DocumentChunk.chunk_index.asc(),
        )
    )

    chunks = db.execute(q).scalars().all()
    print(f"[RESULTADO] Chunks encontrados: {len(chunks)}")

    return chunks


# =========================================================
# EMBEDDINGS (OpenAI)
# =========================================================

def _embed_texts_openai(client: OpenAI, texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in resp.data]


# =========================================================
# PIPELINE PRINCIPAL
# =========================================================

def build_embeddings_for_case(
    db: Session,
    *,
    case_id: str,
    openai_client: Optional[OpenAI] = None,
) -> None:

    print("--------------------------------------------------")
    print("[PUNTO 3] Inicio pipeline embeddings")

    if openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY no definida en entorno")

        openai_client = OpenAI(api_key=api_key)

    collection = get_case_collection(case_id)
    chunks = get_chunks_for_case(db, case_id)

    if not chunks:
        print("[PUNTO 3] No hay chunks. Abortando.")
        return

    all_ids = [c.chunk_id for c in chunks]
    existing = _existing_ids(collection, all_ids)
    pending = [c for c in chunks if c.chunk_id not in existing]

    print("--------------------------------------------------")
    print("[PUNTO 3] Estado")
    print(f"[INFO] Total chunks     : {len(chunks)}")
    print(f"[INFO] Ya indexados     : {len(existing)}")
    print(f"[INFO] Pendientes       : {len(pending)}")

    if not pending:
        print("[PUNTO 3] Nada que hacer. Todo indexado.")
        return

    for i in range(0, len(pending), EMBEDDING_BATCH_SIZE):
        batch = pending[i : i + EMBEDDING_BATCH_SIZE]

        batch_ids = [c.chunk_id for c in batch]
        batch_texts = [c.content for c in batch]

        print("--------------------------------------------------")
        print("[PUNTO 3] Procesando batch")
        print(f"[INFO] Batch nº: {i // EMBEDDING_BATCH_SIZE + 1}")
        print(f"[INFO] Tamaño : {len(batch)}")

        vectors = _embed_texts_openai(openai_client, batch_texts)

        metadatas = [
            {
                "case_id": c.case_id,
                "document_id": c.document_id,
                "chunk_index": c.chunk_index,
            }
            for c in batch
        ]

        collection.add(
            ids=batch_ids,
            embeddings=vectors,
            documents=batch_texts,  # ✅ CRÍTICO: Guardar los textos para poder recuperarlos
            metadatas=metadatas,
        )

        print("[OK] Batch insertado")

    print("--------------------------------------------------")
    print("[PUNTO 3] Embeddings completados")
    print(f"[OK] case_id={case_id}")
