"""
Script de validación del corpus legal ingerido.

Verifica chunks, embeddings y hace queries de prueba al Legal RAG.
"""
from __future__ import annotations

import json

import chromadb

from app.core.variables import (
    DATA,
    LEGAL_JURISPRUDENCIA_VECTORSTORE,
    LEGAL_LEY_VECTORSTORE,
)
from app.rag.legal_rag.service import query_legal_rag

# =========================================================
# VALIDACIÓN
# =========================================================


def validate_ley_concursal() -> dict:
    """Valida Ley Concursal ingerida."""
    print("\n" + "=" * 60)
    print("VALIDACIÓN LEY CONCURSAL")
    print("=" * 60)

    results = {
        "chunks": 0,
        "embeddings": 0,
        "status": "ok",
    }

    try:
        client = chromadb.PersistentClient(path=str(LEGAL_LEY_VECTORSTORE))
        collection = client.get_collection("chunks")

        results["chunks"] = collection.count()
        results["embeddings"] = collection.count()

        print(f"✅ Chunks/Embeddings: {results['chunks']}")

        # Verificar formato de chunk_id (muestreo)
        if results["chunks"] > 0:
            sample = collection.get(limit=5, include=["metadatas"])
            if sample["metadatas"]:
                chunk_ids_found = [
                    m.get("chunk_id") for m in sample["metadatas"] if m.get("chunk_id")
                ]
                if chunk_ids_found:
                    print(
                        f"   ✅ Chunk IDs deterministas encontrados: {chunk_ids_found[0]} (ejemplo)"
                    )
                    results["has_deterministic_ids"] = True
                else:
                    print("   ⚠️  Algunos chunks no tienen chunk_id determinista")
                    results["has_deterministic_ids"] = False

        if results["chunks"] == 0:
            results["status"] = "empty"
            print("⚠️  No hay embeddings. Ejecuta ingest_legal.py --ley")

    except Exception as e:
        results["status"] = "error"
        results["error"] = str(e)
        print(f"❌ Error: {e}")

    return results


def validate_jurisprudencia() -> dict:
    """Valida Jurisprudencia ingerida."""
    print("\n" + "=" * 60)
    print("VALIDACIÓN JURISPRUDENCIA")
    print("=" * 60)

    results = {
        "chunks": 0,
        "embeddings": 0,
        "status": "ok",
    }

    try:
        client = chromadb.PersistentClient(path=str(LEGAL_JURISPRUDENCIA_VECTORSTORE))
        collection = client.get_collection("chunks")

        results["chunks"] = collection.count()
        results["embeddings"] = collection.count()

        print(f"✅ Chunks/Embeddings: {results['chunks']}")

        # Verificar formato de chunk_id (muestreo)
        if results["chunks"] > 0:
            sample = collection.get(limit=5, include=["metadatas"])
            if sample["metadatas"]:
                chunk_ids_found = [
                    m.get("chunk_id") for m in sample["metadatas"] if m.get("chunk_id")
                ]
                if chunk_ids_found:
                    print(
                        f"   ✅ Chunk IDs deterministas encontrados: {chunk_ids_found[0]} (ejemplo)"
                    )
                    results["has_deterministic_ids"] = True
                else:
                    print("   ⚠️  Algunos chunks no tienen chunk_id determinista")
                    results["has_deterministic_ids"] = False

        if results["chunks"] == 0:
            results["status"] = "empty"
            print("⚠️  No hay embeddings. Ejecuta ingest_legal.py --jurisprudencia")

    except Exception as e:
        results["status"] = "error"
        results["error"] = str(e)
        print(f"❌ Error: {e}")

    return results


def test_legal_rag_queries() -> dict:
    """Ejecuta queries de prueba al Legal RAG."""
    print("\n" + "=" * 60)
    print("QUERIES DE PRUEBA AL LEGAL RAG")
    print("=" * 60)

    test_queries = [
        "retraso concurso",
        "pagos preferentes",
        "alzamiento bienes",
        "calificación culpable",
    ]

    results = {}

    for query in test_queries:
        print(f"\n🔍 Query: '{query}'")
        try:
            rag_results = query_legal_rag(query=query, top_k=3)
            results[query] = {
                "count": len(rag_results),
                "status": "ok",
            }

            if rag_results:
                print(f"   ✅ {len(rag_results)} resultados encontrados")
                for i, result in enumerate(rag_results[:2], 1):
                    citation = result.get("citation", "N/A")
                    relevance = result.get("relevance", "N/A")
                    print(f"      {i}. {citation} (relevancia: {relevance})")
            else:
                print("   ⚠️  Sin resultados")
                results[query]["status"] = "empty"

        except Exception as e:
            print(f"   ❌ Error: {e}")
            results[query] = {
                "status": "error",
                "error": str(e),
            }

    return results


def validate_metadata() -> dict:
    """Valida que existan y sean válidos los metadata.json."""
    print("\n" + "=" * 60)
    print("VALIDACIÓN METADATA")
    print("=" * 60)

    results = {}

    # Ley Concursal
    ley_metadata_path = DATA / "legal" / "ley_concursal" / "metadata.json"
    if ley_metadata_path.exists():
        with open(ley_metadata_path) as f:
            ley_metadata = json.load(f)
        results["ley"] = {
            "exists": True,
            "has_hash": bool(ley_metadata.get("hash")),
            "has_reference": bool(ley_metadata.get("reference")),
            "has_version_label": bool(ley_metadata.get("version_label")),
        }
        print("✅ Ley Concursal metadata: OK")
        print(f"   Hash: {'✅' if results['ley']['has_hash'] else '⚠️'}")
        print(f"   Reference: {'✅' if results['ley']['has_reference'] else '⚠️'}")
        print(f"   Version Label: {'✅' if results['ley']['has_version_label'] else '⚠️'}")
        if results["ley"]["has_version_label"]:
            print(f"      '{ley_metadata.get('version_label')}'")
    else:
        results["ley"] = {"exists": False}
        print("⚠️  Ley Concursal metadata: No existe")

    # Jurisprudencia
    jur_metadata_path = DATA / "legal" / "jurisprudencia" / "metadata.json"
    if jur_metadata_path.exists():
        with open(jur_metadata_path) as f:
            jur_metadata = json.load(f)
        results["jurisprudencia"] = {
            "exists": True,
            "has_hash": bool(jur_metadata.get("hash")),
            "has_reference": bool(jur_metadata.get("reference")),
            "has_version_label": bool(jur_metadata.get("version_label")),
        }
        print("✅ Jurisprudencia metadata: OK")
        print(f"   Hash: {'✅' if results['jurisprudencia']['has_hash'] else '⚠️'}")
        print(f"   Reference: {'✅' if results['jurisprudencia']['has_reference'] else '⚠️'}")
        print(
            f"   Version Label: {'✅' if results['jurisprudencia']['has_version_label'] else '⚠️'}"
        )
        if results["jurisprudencia"]["has_version_label"]:
            print(f"      '{jur_metadata.get('version_label')}'")
    else:
        results["jurisprudencia"] = {"exists": False}
        print("⚠️  Jurisprudencia metadata: No existe")

    return results


def main():
    """Ejecuta validación completa."""
    print("=" * 60)
    print("VALIDACIÓN DEL CORPUS LEGAL")
    print("=" * 60)

    results = {}

    # Validar embeddings
    results["ley"] = validate_ley_concursal()
    results["jurisprudencia"] = validate_jurisprudencia()

    # Validar metadata
    results["metadata"] = validate_metadata()

    # Queries de prueba
    results["queries"] = test_legal_rag_queries()

    # Resumen final
    print("\n" + "=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)

    ley_ok = results["ley"].get("chunks", 0) > 0
    jur_ok = results["jurisprudencia"].get("chunks", 0) > 0
    queries_ok = all(
        q.get("count", 0) > 0 for q in results["queries"].values() if q.get("status") == "ok"
    )

    if ley_ok and jur_ok and queries_ok:
        print("✅ VALIDACIÓN EXITOSA")
        print("   - Ley Concursal: OK")
        print("   - Jurisprudencia: OK")
        print("   - Queries: OK")
    else:
        print("⚠️  VALIDACIÓN CON ADVERTENCIAS")
        if not ley_ok:
            print("   - Ley Concursal: Sin embeddings")
        if not jur_ok:
            print("   - Jurisprudencia: Sin embeddings")
        if not queries_ok:
            print("   - Queries: Algunas sin resultados")

    print("\n" + json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
