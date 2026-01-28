"""
Script para inspeccionar la respuesta exacta del RAG.
Muestra: answer, cantidad de sources, y contenido real de cada chunk.
"""

import requests
import json
import sys

def inspect_rag_response(case_id: str, question: str, top_k: int = 5):
    """Inspecciona la respuesta completa del RAG"""
    
    url = "http://127.0.0.1:8000/rag/ask"
    
    payload = {
        "case_id": case_id,
        "question": question,
        "top_k": top_k
    }
    
    print("=" * 80)
    print("INSPECCIÓN DE RESPUESTA RAG")
    print("=" * 80)
    print(f"\n📋 Parámetros:")
    print(f"   case_id: {case_id}")
    print(f"   question: {question}")
    print(f"   top_k: {top_k}")
    print(f"\n🔍 Enviando petición...\n")
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        
        if response.status_code != 200:
            print(f"❌ ERROR: Status code {response.status_code}")
            print(f"Respuesta: {response.text}")
            return
        
        result = response.json()
        
        # ============================================================
        # 1. ANSWER
        # ============================================================
        print("=" * 80)
        print("📝 ANSWER (Respuesta completa)")
        print("=" * 80)
        answer = result.get('answer', '')
        print(f"\n{answer}\n")
        print(f"📊 Longitud: {len(answer)} caracteres\n")
        
        # ============================================================
        # 2. SOURCES (Cantidad)
        # ============================================================
        sources = result.get('sources', [])
        print("=" * 80)
        print(f"📚 SOURCES (Cantidad: {len(sources)})")
        print("=" * 80)
        
        # ============================================================
        # 3. CONTENIDO REAL DE CADA CHUNK
        # ============================================================
        if sources:
            print("\n" + "-" * 80)
            print("📄 CONTENIDO REAL DE CADA CHUNK")
            print("-" * 80)
            
            for i, source in enumerate(sources, 1):
                print(f"\n{'='*80}")
                print(f"CHUNK #{i}")
                print(f"{'='*80}")
                print(f"📄 Document ID: {source.get('document_id', 'N/A')}")
                print(f"🔢 Chunk Index: {source.get('chunk_index', 'N/A')}")
                print(f"📏 Longitud: {len(source.get('content', ''))} caracteres")
                print(f"\n📝 CONTENIDO:")
                print("-" * 80)
                content = source.get('content', '')
                print(content)
                print("-" * 80)
        else:
            print("\n⚠️  No se encontraron sources")
        
        # ============================================================
        # 4. METADATOS ADICIONALES
        # ============================================================
        print("\n" + "=" * 80)
        print("📊 METADATOS ADICIONALES")
        print("=" * 80)
        print(f"🎯 Confianza: {result.get('confidence', 'N/A')}")
        print(f"⚠️  Warnings: {result.get('warnings', [])}")
        
        # ============================================================
        # 5. RESUMEN
        # ============================================================
        print("\n" + "=" * 80)
        print("📋 RESUMEN")
        print("=" * 80)
        print(f"✅ Answer generada: {'Sí' if answer else 'No'} ({len(answer)} chars)")
        print(f"📚 Sources encontrados: {len(sources)}")
        total_content_chars = sum(len(s.get('content', '')) for s in sources)
        print(f"📏 Total caracteres en chunks: {total_content_chars}")
        print("=" * 80)
        
        # Guardar respuesta completa en archivo JSON
        output_file = f"rag_response_{case_id[:8]}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Respuesta completa guardada en: {output_file}")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: No se pudo conectar al servidor")
        print("Asegúrate de que el servidor esté corriendo en http://127.0.0.1:8000")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python inspect_rag_response.py <case_id> <question> [top_k]")
        print("\nEjemplo:")
        print("  python inspect_rag_response.py 0fac46d4-f2cb-4257-9df1-e8aa34019a83 '¿Qué información hay?' 5")
        sys.exit(1)
    
    case_id = sys.argv[1]
    question = sys.argv[2]
    top_k = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    
    inspect_rag_response(case_id, question, top_k)

