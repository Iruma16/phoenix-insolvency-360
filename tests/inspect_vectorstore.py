"""
Script para inspeccionar qué hay realmente en el vectorstore de ChromaDB.
"""

import sys
from pathlib import Path
import chromadb

from app.services.embeddings_pipeline import get_case_collection

def inspect_vectorstore(case_id: str):
    """Inspecciona el contenido del vectorstore"""
    
    print("=" * 80)
    print("INSPECCIÓN DE VECTORSTORE")
    print("=" * 80)
    print(f"\n📋 case_id: {case_id}\n")
    
    try:
        collection = get_case_collection(case_id)
        
        count = collection.count()
        print(f"📊 Total embeddings en colección: {count}\n")
        
        if count == 0:
            print("⚠️  La colección está vacía")
            return
        
        # Obtener todos los datos
        print("=" * 80)
        print("📄 CONTENIDO COMPLETO")
        print("=" * 80)
        
        results = collection.get(include=["documents", "metadatas"])
        
        ids = results.get("ids", [])
        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])
        
        print(f"\n🔢 Elementos encontrados: {len(ids)}\n")
        
        for i, (doc_id, doc, meta) in enumerate(zip(ids, documents, metadatas), 1):
            print(f"\n{'='*80}")
            print(f"ELEMENTO #{i}")
            print(f"{'='*80}")
            print(f"🆔 ID: {doc_id}")
            print(f"📄 Documento (tipo: {type(doc).__name__}, longitud: {len(str(doc)) if doc else 0}):")
            print(f"   {repr(doc)[:200]}..." if doc and len(str(doc)) > 200 else f"   {repr(doc)}")
            print(f"\n📋 Metadatos (tipo: {type(meta).__name__}):")
            if meta:
                for key, value in meta.items():
                    print(f"   {key}: {value} (tipo: {type(value).__name__})")
            else:
                print("   None o vacío")
        
        # Hacer una query de prueba
        print("\n" + "=" * 80)
        print("🔍 QUERY DE PRUEBA")
        print("=" * 80)
        print("\nProbando query con texto de prueba...")
        
        from openai import OpenAI
        from app.core.variables import EMBEDDING_MODEL
        
        client = OpenAI()
        test_question = "insolvencia"
        test_embedding = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[test_question],
        ).data[0].embedding
        
        query_results = collection.query(
            query_embeddings=[test_embedding],
            n_results=min(5, count),
            include=["documents", "metadatas", "distances"],
        )
        
        query_docs = query_results.get("documents", [[]])[0]
        query_metas = query_results.get("metadatas", [[]])[0]
        query_distances = query_results.get("distances", [[]])[0]
        
        print(f"\n📊 Resultados de query: {len(query_docs)} documentos encontrados\n")
        
        for i, (doc, meta, distance) in enumerate(zip(query_docs, query_metas, query_distances), 1):
            print(f"\n{'='*80}")
            print(f"RESULTADO QUERY #{i} (distancia: {distance:.4f})")
            print(f"{'='*80}")
            print(f"📄 Documento (tipo: {type(doc).__name__}, longitud: {len(str(doc)) if doc else 0}):")
            print(f"   {repr(doc)[:200]}..." if doc and len(str(doc)) > 200 else f"   {repr(doc)}")
            print(f"\n📋 Metadatos:")
            if meta:
                for key, value in meta.items():
                    print(f"   {key}: {value} (tipo: {type(value).__name__})")
            else:
                print("   None o vacío")
        
        print("\n" + "=" * 80)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python inspect_vectorstore.py <case_id>")
        print("\nEjemplo:")
        print("  python inspect_vectorstore.py 0fac46d4-f2cb-4257-9df1-e8aa34019a83")
        sys.exit(1)
    
    case_id = sys.argv[1]
    inspect_vectorstore(case_id)

