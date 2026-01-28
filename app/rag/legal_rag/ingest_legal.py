"""
Script de ingesta controlada del corpus legal.

Genera chunks y embeddings para Ley Concursal y Jurisprudencia.

⚠️ ADVERTENCIA: Este script requiere acción manual explícita.
NO se ejecuta automáticamente ni actualiza datos sin intervención humana.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import chromadb
from openai import OpenAI

from app.core.variables import (
    DATA,
    EMBEDDING_MODEL,
    LEGAL_JURISPRUDENCIA_VECTORSTORE,
    LEGAL_LEY_VECTORSTORE,
)

# =========================================================
# CONFIGURACIÓN
# =========================================================

LEGAL_LEY_RAW = DATA / "legal" / "ley_concursal" / "raw"
LEGAL_LEY_METADATA = DATA / "legal" / "ley_concursal" / "metadata.json"
LEGAL_JUR_RAW = DATA / "legal" / "jurisprudencia" / "raw"
LEGAL_JUR_METADATA = DATA / "legal" / "jurisprudencia" / "metadata.json"


# =========================================================
# UTILIDADES
# =========================================================


def _get_text_hash(text: str) -> str:
    """Calcula hash SHA256 del texto."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _get_openai_client() -> OpenAI:
    """Obtiene cliente OpenAI."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no definida en entorno")
    return OpenAI(api_key=api_key)


def _get_legal_collection(vectorstore_path: Path, collection_name: str = "chunks"):
    """Obtiene o crea una colección de ChromaDB para contenido legal."""
    vectorstore_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(vectorstore_path))
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"type": "legal"},
    )
    return collection


def _load_metadata(metadata_path: Path) -> dict[str, Any]:
    """Carga metadata.json."""
    if metadata_path.exists():
        with open(metadata_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_metadata(metadata_path: Path, metadata: dict[str, Any]) -> None:
    """Guarda metadata.json."""
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


# =========================================================
# CHUNKING LEY CONCURSAL
# =========================================================


def chunk_ley_concursal(text: str) -> list[dict[str, Any]]:
    """
    Divide el texto COMPLETO de la Ley Concursal por tamaño con solape.

    ESTRATEGIA COMPLETA (no por artículo):
    - Chunk size: 1000-1500 caracteres
    - Overlap: 150 caracteres
    - Un artículo puede generar varios chunks
    - Un chunk puede contener varios artículos
    - Se incluyen TODOS los libros, títulos, disposiciones, anexos

    Metadata por chunk:
    - law: "Ley Concursal"
    - type: "ley"
    - chunk_id: "LC-FULL-{índice}" (determinista)
    - chunk_index: posición en el texto
    """
    chunks: list[dict[str, Any]] = []

    # Configuración de chunking
    CHUNK_SIZE = 1200  # caracteres
    OVERLAP = 150  # caracteres
    MIN_CHUNK_SIZE = 200  # mínimo para considerar un chunk válido

    text_length = len(text)
    chunk_index = 0
    start = 0

    while start < text_length:
        # Calcular fin del chunk
        end = start + CHUNK_SIZE

        # Si no es el último chunk, buscar un punto de corte natural
        if end < text_length:
            # Buscar el último punto, salto de línea o espacio en los últimos 200 chars
            search_start = max(start + CHUNK_SIZE - 200, start)
            search_end = min(end + 100, text_length)

            # Prioridad: doble salto de línea (párrafo)
            last_paragraph = text.rfind("\n\n", search_start, search_end)
            if last_paragraph > search_start:
                end = last_paragraph + 2
            else:
                # Si no hay párrafo, buscar salto de línea simple
                last_newline = text.rfind("\n", search_start, search_end)
                if last_newline > search_start:
                    end = last_newline + 1
                else:
                    # Si no hay salto, buscar punto
                    last_period = text.rfind(". ", search_start, search_end)
                    if last_period > search_start:
                        end = last_period + 2
                    else:
                        # Si no hay nada, buscar espacio
                        last_space = text.rfind(" ", search_start, search_end)
                        if last_space > search_start:
                            end = last_space + 1

        # Extraer chunk
        chunk_text = text[start:end].strip()

        # Validar tamaño mínimo
        if len(chunk_text) >= MIN_CHUNK_SIZE:
            # Intentar detectar artículos en este chunk para metadata
            import re

            articles_in_chunk = re.findall(r"Art(?:ículo|\.)\s+(\d+)", chunk_text)
            article_ref = None
            if articles_in_chunk:
                # Si hay artículos, usar el primero como referencia
                article_ref = articles_in_chunk[0]

            metadata = {
                "law": "Ley Concursal",
                "type": "ley",
                "chunk_id": f"LC-FULL-{chunk_index:04d}",
                "chunk_index": str(chunk_index),
                "char_start": str(start),
                "char_end": str(end),
                "ingestion_type": "full_text_overlap",
            }

            # Añadir article_ref solo si existe
            if article_ref:
                metadata["article_ref"] = article_ref

            chunks.append(
                {
                    "text": chunk_text,
                    "metadata": metadata,
                }
            )
            chunk_index += 1
        elif len(chunk_text) > 0:
            print(
                f"⚠️  [WARN] Chunk {chunk_index} demasiado corto ({len(chunk_text)} chars), omitido"
            )

        # Avanzar con solape
        start = end - OVERLAP

        # Evitar loops infinitos
        if start >= text_length or (end >= text_length and start + MIN_CHUNK_SIZE >= text_length):
            break

    return chunks


# =========================================================
# CHUNKING JURISPRUDENCIA
# =========================================================


def chunk_jurisprudencia(text: str, filename: str) -> list[dict[str, Any]]:
    """
    Divide el texto de jurisprudencia por fundamentos jurídicos.

    Extrae metadata del nombre del archivo: ts_2023_01_15.txt
    o del contenido si está disponible.

    Cada fundamento relevante se convierte en un chunk con metadata:
    - court: "TS", "AP Madrid", etc.
    - date: "2023-01-15"
    - case_ref: Referencia del caso (si disponible)
    - type: "jurisprudencia"
    - chunk_id: "TS-2023-01-15-FJ-3" (determinista y estable)
    """
    chunks: list[dict[str, Any]] = []

    # Extraer metadata del nombre de archivo
    parts = filename.replace(".txt", "").split("_")
    court = parts[0].upper() if parts else "TRIBUNAL"
    date = ""
    if len(parts) >= 4:
        date = f"{parts[1]}-{parts[2]}-{parts[3]}"

    case_ref = f"{court}_{date}" if date else court

    # Detectar fundamentos jurídicos (secciones que empiezan con números romanos, etc.)
    # Por ahora, dividir por párrafos largos (>200 caracteres) como aproximación
    paragraphs = text.split("\n\n")

    fj_index = 1  # Índice de fundamento jurídico
    for i, para in enumerate(paragraphs):
        para = para.strip()
        # Validación mínima pre-embedding: longitud mínima 200 caracteres
        if len(para) >= 200:
            chunk_id = f"{court}-{date}-FJ-{fj_index}" if date else f"{court}-FJ-{fj_index}"
            chunks.append(
                {
                    "text": para,
                    "metadata": {
                        "court": court,
                        "date": date,
                        "case_ref": case_ref,
                        "type": "jurisprudencia",
                        "chunk_index": i,
                        "chunk_id": chunk_id,  # Determinista
                    },
                }
            )
            fj_index += 1
        elif len(para) > 0:
            # Párrafo demasiado corto, warning pero no fatal
            print(
                f"⚠️  [WARN] Párrafo {i} en {filename} demasiado corto ({len(para)} chars), omitido"
            )

    # Si no hay párrafos largos, usar el texto completo si es suficientemente largo
    if not chunks and text.strip():
        chunk_text = text.strip()
        if len(chunk_text) >= 200:  # Validación mínima
            chunk_id = f"{court}-{date}-FJ-1" if date else f"{court}-FJ-1"
            chunks.append(
                {
                    "text": chunk_text,
                    "metadata": {
                        "court": court,
                        "date": date,
                        "case_ref": case_ref,
                        "type": "jurisprudencia",
                        "chunk_id": chunk_id,  # Determinista
                    },
                }
            )
        else:
            print(
                f"⚠️  [WARN] Texto completo de {filename} demasiado corto ({len(chunk_text)} chars)"
            )

    return chunks


# =========================================================
# INGESTA LEY CONCURSAL
# =========================================================


def ingest_ley_concursal(overwrite: bool = False) -> dict[str, Any]:
    """
    Ingiere TRLC COMPLETO desde documents/ (texto descargado del BOE).

    Busca el archivo más reciente con patrón ley_concursal_boe_consolidado_trlc_*.txt

    Returns:
        Dict con estadísticas de ingesta
    """
    # Buscar archivo TRLC más reciente en documents/
    docs_dir = DATA / "legal" / "ley_concursal" / "documents"

    if not docs_dir.exists():
        raise FileNotFoundError(
            f"Directorio documents no encontrado: {docs_dir}\n"
            "Ejecuta primero: python scripts/download_trlc_completo.py"
        )

    # Buscar archivos TXT del TRLC
    trlc_files = sorted(
        docs_dir.glob("ley_concursal_boe_consolidado_trlc_*.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not trlc_files:
        raise FileNotFoundError(
            f"No se encontró archivo TRLC en: {docs_dir}\n"
            "Ejecuta primero: python scripts/download_trlc_completo.py"
        )

    raw_file = trlc_files[0]
    print(f"📄 Usando archivo: {raw_file.name}")

    # Leer texto
    with open(raw_file, encoding="utf-8") as f:
        text = f.read()

    # Calcular hash
    text_hash = _get_text_hash(text)

    # Cargar metadata
    metadata = _load_metadata(LEGAL_LEY_METADATA)

    # Verificar si ya se procesó este hash
    if metadata.get("hash") == text_hash and not overwrite:
        print(f"⚠️  Ley Concursal ya procesada (hash: {text_hash[:8]}...)")
        print("   Usa overwrite=True para reprocesar")
        return {"status": "already_processed", "hash": text_hash}

    # Chunkear
    print("📄 Chunking Ley Concursal por artículo...")
    chunks = chunk_ley_concursal(text)

    # Validación adicional: verificar que hay chunks válidos
    valid_chunks = [c for c in chunks if c.get("text") and len(c.get("text", "")) >= 50]
    if len(valid_chunks) < len(chunks):
        print(f"   ⚠️  {len(chunks) - len(valid_chunks)} chunks omitidos por validación")

    chunks = valid_chunks
    print(f"   ✅ {len(chunks)} artículos válidos encontrados")

    # Generar embeddings y guardar
    print("🔢 Generando embeddings...")
    openai_client = _get_openai_client()
    collection = _get_legal_collection(LEGAL_LEY_VECTORSTORE, "chunks")

    # Limpiar colección si overwrite
    if overwrite:
        try:
            collection.delete()
            collection = _get_legal_collection(LEGAL_LEY_VECTORSTORE, "chunks")
        except Exception:
            pass

    chunk_ids = []
    chunk_texts = []
    chunk_metadatas = []

    for i, chunk_data in enumerate(chunks):
        # Usar chunk_id determinista del metadata si existe, sino generar uno
        metadata = chunk_data["metadata"]
        chunk_id = metadata.get("chunk_id") or f"ley_{metadata.get('article', 'unknown')}_{i}"
        chunk_ids.append(chunk_id)
        chunk_texts.append(chunk_data["text"])
        chunk_metadatas.append(metadata)

    # Generar embeddings en batch
    batch_size = 50
    all_embeddings = []
    for i in range(0, len(chunk_texts), batch_size):
        batch = chunk_texts[i : i + batch_size]
        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

    # Guardar en ChromaDB
    collection.add(
        ids=chunk_ids,
        documents=chunk_texts,
        metadatas=chunk_metadatas,
        embeddings=all_embeddings,
    )

    print(f"   ✅ {len(chunk_ids)} embeddings guardados")

    # Actualizar metadata (preservar version_label si existe)
    metadata.update(
        {
            "hash": text_hash,
            "last_update": datetime.now().strftime("%Y-%m-%d"),
            "ingestion_date": datetime.now().isoformat(),
            "total_articles": len(chunks),
        }
    )
    # Si no existe version_label, usar un valor por defecto basado en fecha
    if "version_label" not in metadata or not metadata.get("version_label"):
        metadata["version_label"] = f"LC consolidada BOE {metadata['last_update']}"
    _save_metadata(LEGAL_LEY_METADATA, metadata)

    return {
        "status": "success",
        "chunks": len(chunks),
        "embeddings": len(chunk_ids),
        "hash": text_hash,
    }


# =========================================================
# INGESTA JURISPRUDENCIA
# =========================================================


def ingest_jurisprudencia(overwrite: bool = False) -> dict[str, Any]:
    """
    Ingiere jurisprudencia desde raw/*.txt.

    Returns:
        Dict con estadísticas de ingesta
    """
    if not LEGAL_JUR_RAW.exists():
        raise FileNotFoundError(
            f"Directorio raw no encontrado: {LEGAL_JUR_RAW}\n"
            "Por favor, crea el directorio y coloca archivos .txt de sentencias"
        )

    # Encontrar archivos .txt
    txt_files = list(LEGAL_JUR_RAW.glob("*.txt"))

    if not txt_files:
        raise FileNotFoundError(
            f"No se encontraron archivos .txt en: {LEGAL_JUR_RAW}\n"
            "Por favor, coloca archivos de sentencias en formato: court_YYYY_MM_DD.txt"
        )

    print(f"📄 Procesando {len(txt_files)} archivos de jurisprudencia...")

    all_chunks = []
    all_hashes = []

    for txt_file in txt_files:
        with open(txt_file, encoding="utf-8") as f:
            text = f.read()

        all_hashes.append(_get_text_hash(text))
        chunks = chunk_jurisprudencia(text, txt_file.name)
        all_chunks.extend(chunks)

    # Validación adicional: verificar que hay chunks válidos
    valid_chunks = [c for c in all_chunks if c.get("text") and len(c.get("text", "")) >= 200]
    if len(valid_chunks) < len(all_chunks):
        print(f"   ⚠️  {len(all_chunks) - len(valid_chunks)} chunks omitidos por validación")

    all_chunks = valid_chunks
    print(f"   ✅ {len(all_chunks)} chunks válidos generados")

    # Calcular hash conjunto
    combined_hash = _get_text_hash("".join(all_hashes))

    # Cargar metadata
    metadata = _load_metadata(LEGAL_JUR_METADATA)

    # Verificar si ya se procesó
    if metadata.get("hash") == combined_hash and not overwrite:
        print(f"⚠️  Jurisprudencia ya procesada (hash: {combined_hash[:8]}...)")
        print("   Usa overwrite=True para reprocesar")
        return {"status": "already_processed", "hash": combined_hash}

    # Generar embeddings y guardar
    print("🔢 Generando embeddings...")
    openai_client = _get_openai_client()
    collection = _get_legal_collection(LEGAL_JURISPRUDENCIA_VECTORSTORE, "chunks")

    # Limpiar colección si overwrite
    if overwrite:
        try:
            collection.delete()
            collection = _get_legal_collection(LEGAL_JURISPRUDENCIA_VECTORSTORE, "chunks")
        except Exception:
            pass

    chunk_ids = []
    chunk_texts = []
    chunk_metadatas = []

    for i, chunk_data in enumerate(all_chunks):
        metadata_item = chunk_data["metadata"]
        # Usar chunk_id determinista del metadata si existe, sino generar uno
        chunk_id = (
            metadata_item.get("chunk_id") or f"jur_{metadata_item.get('case_ref', 'unknown')}_{i}"
        )
        chunk_ids.append(chunk_id)
        chunk_texts.append(chunk_data["text"])
        chunk_metadatas.append(metadata_item)

    # Generar embeddings en batch
    batch_size = 50
    all_embeddings = []
    for i in range(0, len(chunk_texts), batch_size):
        batch = chunk_texts[i : i + batch_size]
        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

    # Guardar en ChromaDB
    collection.add(
        ids=chunk_ids,
        documents=chunk_texts,
        metadatas=chunk_metadatas,
        embeddings=all_embeddings,
    )

    print(f"   ✅ {len(chunk_ids)} embeddings guardados")

    # Actualizar metadata (preservar version_label si existe)
    metadata.update(
        {
            "hash": combined_hash,
            "last_update": datetime.now().strftime("%Y-%m-%d"),
            "ingestion_date": datetime.now().isoformat(),
            "total_sentences": len(txt_files),
        }
    )
    # Si no existe version_label, usar un valor por defecto
    if "version_label" not in metadata or not metadata.get("version_label"):
        metadata["version_label"] = f"Jurisprudencia seleccionada {metadata['last_update']}"
    _save_metadata(LEGAL_JUR_METADATA, metadata)

    return {
        "status": "success",
        "files": len(txt_files),
        "chunks": len(all_chunks),
        "embeddings": len(chunk_ids),
        "hash": combined_hash,
    }


# =========================================================
# MAIN
# =========================================================


def main():
    """Ejecuta la ingesta completa."""
    import argparse

    parser = argparse.ArgumentParser(description="Ingesta controlada del corpus legal")
    parser.add_argument(
        "--ley",
        action="store_true",
        help="Ingerir Ley Concursal",
    )
    parser.add_argument(
        "--jurisprudencia",
        action="store_true",
        help="Ingerir Jurisprudencia",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Ingerir todo",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Sobrescribir embeddings existentes",
    )

    args = parser.parse_args()

    if not (args.ley or args.jurisprudencia or args.all):
        parser.print_help()
        return

    results = {}

    if args.all or args.ley:
        print("\n" + "=" * 60)
        print("INGESTA LEY CONCURSAL")
        print("=" * 60)
        try:
            results["ley"] = ingest_ley_concursal(overwrite=args.overwrite)
        except Exception as e:
            print(f"❌ Error: {e}")
            results["ley"] = {"status": "error", "error": str(e)}

    if args.all or args.jurisprudencia:
        print("\n" + "=" * 60)
        print("INGESTA JURISPRUDENCIA")
        print("=" * 60)
        try:
            results["jurisprudencia"] = ingest_jurisprudencia(overwrite=args.overwrite)
        except Exception as e:
            print(f"❌ Error: {e}")
            results["jurisprudencia"] = {"status": "error", "error": str(e)}

    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
