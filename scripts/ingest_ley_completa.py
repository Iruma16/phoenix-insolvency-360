"""
Script para ingerir la Ley Concursal COMPLETA en el vectorstore legal.

Lee el archivo TXT descargado del BOE y genera embeddings para TODO el texto,
usando chunks con solape para preservar contexto.
"""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Configuración
BASE_DIR = Path(__file__).parent.parent
LEGAL_DIR = BASE_DIR / "clients_data" / "legal" / "ley_concursal"
DOCS_DIR = LEGAL_DIR / "documents"
RAW_DIR = LEGAL_DIR / "raw"
VECTORSTORE_DIR = BASE_DIR / "clients_data" / "_vectorstore" / "legal" / "ley_concursal"
METADATA_FILE = LEGAL_DIR / "metadata.json"

EMBEDDING_MODEL = "text-embedding-3-large"
CHUNK_SIZE = 1000  # Caracteres por chunk
CHUNK_OVERLAP = 200  # Solape entre chunks


def find_latest_txt():
    """Encuentra el archivo TXT más reciente."""
    txt_files = sorted(DOCS_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not txt_files:
        raise FileNotFoundError(f"No se encontró archivo TXT en {DOCS_DIR}")
    return txt_files[0]


def chunk_text_with_overlap(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """
    Divide el texto en chunks con solape para preservar contexto.

    Intenta dividir por artículos cuando sea posible, sino por párrafos,
    y si no por tamaño con solape.
    """
    chunks = []

    # Intentar dividir por artículos primero
    import re

    article_pattern = r"(Artículo \d+\.?|Art\. \d+\.?)"
    parts = re.split(article_pattern, text)

    # Reconstruir artículos completos
    articles = []
    current_article = ""
    for i, part in enumerate(parts):
        if re.match(article_pattern, part):
            if current_article:
                articles.append(current_article.strip())
            current_article = part
        else:
            current_article += part

    if current_article:
        articles.append(current_article.strip())

    # Si tenemos artículos, usar esos como base
    if len(articles) > 50:  # Parece una estructura de artículos válida
        for article in articles:
            if len(article) < 50:  # Artículo muy corto, skip
                continue

            # Si el artículo es muy largo, dividirlo en sub-chunks
            if len(article) > chunk_size:
                sub_chunks = _chunk_by_size(article, chunk_size, overlap)
                chunks.extend(sub_chunks)
            else:
                chunks.append(article)
    else:
        # No hay estructura clara de artículos, dividir por tamaño con solape
        chunks = _chunk_by_size(text, chunk_size, overlap)

    return chunks


def _chunk_by_size(text, chunk_size, overlap):
    """Divide texto por tamaño con solape."""
    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size

        # Si no es el último chunk, intentar terminar en un punto o salto de línea
        if end < text_len:
            # Buscar el último punto o salto de línea en los últimos 100 chars
            search_end = min(end + 100, text_len)
            last_period = text.rfind(".", end - 100, search_end)
            last_newline = text.rfind("\n", end - 100, search_end)

            best_end = max(last_period, last_newline)
            if best_end > end - 100:
                end = best_end + 1

        chunk_text = text[start:end].strip()
        if len(chunk_text) >= 100:  # Mínimo 100 chars por chunk
            chunks.append(chunk_text)

        # Avanzar con solape
        start = end - overlap

        # Evitar loops infinitos
        if start >= text_len:
            break

    return chunks


def ingest_ley_completa(overwrite=True):
    """Ingiere la Ley Concursal completa."""

    print("=" * 70)
    print("INGESTA LEY CONCURSAL COMPLETA")
    print("=" * 70)

    # Buscar archivo TXT más reciente
    txt_path = find_latest_txt()
    print(f"\n📄 Archivo fuente: {txt_path.name}")

    # Leer texto
    with open(txt_path, encoding="utf-8") as f:
        text = f.read()

    print(f"   ✅ Leído: {len(text):,} caracteres")

    # Generar chunks
    print(f"\n🔪 Generando chunks (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})...")
    chunks = chunk_text_with_overlap(text, CHUNK_SIZE, CHUNK_OVERLAP)

    valid_chunks = [c for c in chunks if len(c) >= 100]
    print(f"   ✅ Chunks generados: {len(valid_chunks)}")

    if len(valid_chunks) < 100:
        raise ValueError(
            f"Solo {len(valid_chunks)} chunks generados. Esperado >100 para texto completo."
        )

    # Inicializar OpenAI y Chroma
    print("\n🔢 Generando embeddings...")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no definida")

    openai_client = OpenAI(api_key=api_key)

    # Crear/limpiar colección
    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    chroma_client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))

    if overwrite:
        try:
            chroma_client.delete_collection("chunks")
        except:
            pass

    collection = chroma_client.get_or_create_collection(
        name="chunks", metadata={"type": "legal", "source": "BOE"}
    )

    # Generar embeddings en batches
    batch_size = 50
    chunk_ids = []
    chunk_texts = []
    chunk_metadatas = []

    for i, chunk_text in enumerate(valid_chunks):
        chunk_id = f"LC-FULL-{i:05d}"
        chunk_ids.append(chunk_id)
        chunk_texts.append(chunk_text)

        # Metadata básico
        metadata = {
            "law": "Ley Concursal",
            "type": "ley",
            "chunk_index": i,
            "chunk_id": chunk_id,
            "source": "BOE",
            "ingestion_type": "full_text",
        }
        chunk_metadatas.append(metadata)

    print(f"   Procesando {len(chunk_texts)} chunks en batches de {batch_size}...")

    all_embeddings = []
    for i in range(0, len(chunk_texts), batch_size):
        batch = chunk_texts[i : i + batch_size]
        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

        print(f"   Batch {i//batch_size + 1}/{(len(chunk_texts)-1)//batch_size + 1} completado")

    # Guardar en Chroma
    print("\n💾 Guardando en vectorstore...")
    collection.add(
        ids=chunk_ids,
        documents=chunk_texts,
        metadatas=chunk_metadatas,
        embeddings=all_embeddings,
    )

    final_count = collection.count()
    print(f"   ✅ Embeddings guardados: {final_count}")

    # Actualizar metadata
    with open(METADATA_FILE, encoding="utf-8") as f:
        metadata = json.load(f)

    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    metadata.update(
        {
            "ingestion": {
                "hash": text_hash,
                "date": datetime.now().isoformat(),
                "type": "full_text",
                "total_chunks": final_count,
                "chunk_size": CHUNK_SIZE,
                "chunk_overlap": CHUNK_OVERLAP,
            }
        }
    )

    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Metadata actualizada: {METADATA_FILE}")

    print("\n" + "=" * 70)
    print("✅ INGESTA COMPLETA EXITOSA")
    print("=" * 70)
    print("\nEstadísticas:")
    print(f"  - Chunks totales: {final_count}")
    print(f"  - Vectorstore: {VECTORSTORE_DIR}")
    print(f"  - Hash texto: {text_hash[:16]}...")

    return {
        "status": "success",
        "chunks": final_count,
        "hash": text_hash,
    }


if __name__ == "__main__":
    try:
        result = ingest_ley_completa(overwrite=True)
        print("\n🎯 Siguiente paso: Ejecutar validación con:")
        print("   python scripts/validate_legal_corpus.py")
    except Exception as e:
        print(f"\n💥 Error en ingesta: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
