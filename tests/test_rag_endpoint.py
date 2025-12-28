"""
Test rápido para verificar que el endpoint RAG funciona correctamente.
Requiere que el servidor esté corriendo en http://127.0.0.1:8000
"""

import requests
import json

def test_rag_endpoint():
    """Test del endpoint /rag/ask"""
    
    url = "http://127.0.0.1:8000/rag/ask"
    
    # Usar un case_id que ya existe (el del error anterior)
    # O puedes cambiarlo por el que uses
    payload = {
        "case_id": "0fac46d4-f2cb-4257-9df1-e8aa34019a83",
        "question": "¿Qué información hay sobre insolvencia?",
        "top_k": 3
    }
    
    print("=" * 60)
    print("TEST: Endpoint RAG /rag/ask")
    print("=" * 60)
    print(f"\nURL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    print("\nEnviando petición...")
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n✅ RESPUESTA EXITOSA")
            print("=" * 60)
            print(f"\nRespuesta ({len(result.get('answer', ''))} caracteres):")
            print(result.get('answer', '')[:200] + "..." if len(result.get('answer', '')) > 200 else result.get('answer', ''))
            print(f"\nConfianza: {result.get('confidence', 'N/A')}")
            print(f"Fuentes encontradas: {len(result.get('sources', []))}")
            print(f"Warnings: {result.get('warnings', [])}")
            
            # Verificar que los sources tienen content válido
            sources = result.get('sources', [])
            if sources:
                print(f"\nFuentes:")
                for i, source in enumerate(sources, 1):
                    content = source.get('content', '')
                    content_preview = content[:100] + "..." if len(content) > 100 else content
                    print(f"  {i}. Documento: {source.get('document_id')}, Chunk: {source.get('chunk_index')}")
                    print(f"     Content: {content_preview}")
                    # Verificar que content no es None
                    assert content is not None, f"❌ ERROR: Source {i} tiene content=None"
                    assert isinstance(content, str), f"❌ ERROR: Source {i} tiene content que no es string: {type(content)}"
                    assert content.strip() != "", f"❌ ERROR: Source {i} tiene content vacío"
                    print(f"     ✅ Content válido ({len(content)} caracteres)")
            
            print("\n" + "=" * 60)
            print("✅ TEST COMPLETADO EXITOSAMENTE")
            print("=" * 60)
            
        else:
            print(f"\n❌ ERROR: Status code {response.status_code}")
            print(f"Respuesta: {response.text}")
            raise Exception(f"Error en la petición: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: No se pudo conectar al servidor")
        print("Asegúrate de que el servidor esté corriendo en http://127.0.0.1:8000")
        print("Ejecuta: uvicorn app.main:app --reload")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    test_rag_endpoint()

