"""
Test para verificar que el refactor de separación RAG/LLM funciona correctamente.
"""

import sys
from pathlib import Path
from datetime import datetime

from app.core.database import get_db
from app.core.variables import DATA
from app.models.case import Case
from app.models.document import Document
from app.services.document_chunk_pipeline import build_document_chunks_for_case
from app.services.embeddings_pipeline import build_embeddings_for_case
from app.rag.case_rag.retrieve import rag_answer_internal
from app.agents.base.response_builder import build_llm_answer


def test_rag_retrieves_context_only():
    """Test 1: Verificar que RAG solo recupera contexto, no genera respuestas"""
    
    print("=" * 80)
    print("TEST 1: RAG solo recupera contexto (sin LLM)")
    print("=" * 80)
    
    db = next(get_db())
    
    try:
        # Crear caso de prueba
        case = Case(
            name="Test RAG Separation",
            client_ref="TEST_RAG_SEP",
            status="active",
        )
        db.add(case)
        db.flush()
        case_id = case.case_id
        print(f"\n✅ Caso creado: {case_id}")
        
        # Crear documento de prueba
        test_dir = DATA / "test_rag_separation" / "cases" / case_id / "documents"
        test_dir.mkdir(parents=True, exist_ok=True)
        
        test_file = test_dir / "test_doc.txt"
        test_content = """
        Este es un documento de prueba para verificar la separación RAG/LLM.
        Contiene información sobre un contrato de servicios.
        El contrato fue firmado el 1 de enero de 2024.
        El valor del contrato es de 100.000 euros.
        """
        test_file.write_text(test_content.strip())
        print(f"✅ Archivo creado: {test_file}")
        
        # Crear documento en BD
        document = Document(
            case_id=case_id,
            filename="test_doc.txt",
            doc_type="contrato",
            source="test",
            date_start=datetime(2024, 1, 1),
            date_end=datetime(2024, 12, 31),
            reliability="original",
            file_format="txt",
            storage_path=str(test_file),
        )
        db.add(document)
        db.commit()
        print(f"✅ Documento creado: {document.document_id}")
        
        # Generar chunks
        print("\n📦 Generando chunks...")
        build_document_chunks_for_case(db=db, case_id=case_id, overwrite=True)
        db.commit()
        print("✅ Chunks generados")
        
        # Generar embeddings
        print("\n🔢 Generando embeddings...")
        build_embeddings_for_case(db=db, case_id=case_id)
        print("✅ Embeddings generados")
        
        # Hacer query RAG
        print("\n🔍 Consultando RAG...")
        question = "¿Cuándo fue firmado el contrato?"
        
        result = rag_answer_internal(
            db=db,
            case_id=case_id,
            question=question,
            top_k=3,
        )
        
        print(f"\n📋 Resultado RAG:")
        print(f"   Status: {result.status}")
        print(f"   Confidence: {result.confidence}")
        print(f"   Fuentes encontradas: {len(result.sources)}")
        print(f"   Contexto disponible: {len(result.context_text) if result.context_text else 0} caracteres")
        print(f"   Warnings: {len(result.warnings)}")
        
        # Verificaciones
        assert result.status in ["OK", "PARTIAL_CONTEXT"], \
            f"Status debería ser OK o PARTIAL_CONTEXT, obtuvo: {result.status}"
        assert hasattr(result, 'context_text'), \
            "RAGInternalResult debe tener campo 'context_text'"
        assert not hasattr(result, 'answer'), \
            "RAGInternalResult NO debe tener campo 'answer' (fue eliminado)"
        assert result.context_text is not None, \
            "context_text no debe ser None"
        assert len(result.context_text) > 0, \
            "Debe haber contexto recuperado"
        assert len(result.sources) > 0, \
            "Debe haber al menos una fuente"
        
        print("\n✅ TEST 1 PASADO: RAG solo recupera contexto (sin LLM)")
        return result
        
    except Exception as e:
        print(f"\n❌ ERROR en TEST 1: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        db.close()


def test_response_builder_generates_answer():
    """Test 2: Verificar que response_builder puede generar respuestas con LLM"""
    
    print("\n" + "=" * 80)
    print("TEST 2: Response builder genera respuestas con LLM")
    print("=" * 80)
    
    try:
        question = "¿Cuándo fue firmado el contrato?"
        context_text = """
        [Documento doc123 | Chunk 0]
        Este es un documento de prueba para verificar la separación RAG/LLM.
        Contiene información sobre un contrato de servicios.
        El contrato fue firmado el 1 de enero de 2024.
        El valor del contrato es de 100.000 euros.
        """
        
        print(f"\n📝 Pregunta: {question}")
        print(f"📄 Contexto: {len(context_text)} caracteres")
        
        print("\n🤖 Generando respuesta con LLM...")
        answer = build_llm_answer(
            question=question,
            context_text=context_text,
        )
        
        print(f"\n✅ Respuesta generada:")
        print(f"   Longitud: {len(answer)} caracteres")
        print(f"   Primeros 150 chars: {answer[:150]}...")
        
        # Verificaciones
        assert answer is not None, "La respuesta no debe ser None"
        assert len(answer) > 0, "La respuesta no debe estar vacía"
        assert isinstance(answer, str), "La respuesta debe ser un string"
        
        print("\n✅ TEST 2 PASADO: Response builder genera respuestas correctamente")
        return answer
        
    except Exception as e:
        print(f"\n❌ ERROR en TEST 2: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_full_flow():
    """Test 3: Verificar flujo completo RAG + Response Builder"""
    
    print("\n" + "=" * 80)
    print("TEST 3: Flujo completo RAG → Response Builder")
    print("=" * 80)
    
    db = next(get_db())
    
    try:
        # Usar el mismo caso del test 1 (asumiendo que existe)
        # En producción, esto debería crear su propio caso
        case_id = "TEST_RAG_SEP"  # Esto debería ser el case_id real
        
        # Buscar caso existente o crear uno nuevo
        from app.models.case import Case
        case = db.query(Case).filter(Case.client_ref == case_id).first()
        
        if not case:
            print(f"\n⚠️  Caso no encontrado, ejecuta TEST 1 primero")
            return None
        
        case_id = case.case_id
        print(f"\n📁 Usando caso: {case_id}")
        
        # 1. Recuperar contexto con RAG
        print("\n1️⃣ Recuperando contexto con RAG...")
        question = "¿Cuál es el valor del contrato?"
        
        rag_result = rag_answer_internal(
            db=db,
            case_id=case_id,
            question=question,
            top_k=3,
        )
        
        assert rag_result.context_text, "Debe haber contexto recuperado"
        print(f"   ✅ Contexto recuperado: {len(rag_result.context_text)} caracteres")
        print(f"   ✅ Fuentes: {len(rag_result.sources)}")
        
        # 2. Generar respuesta con LLM
        print("\n2️⃣ Generando respuesta con LLM...")
        answer = build_llm_answer(
            question=question,
            context_text=rag_result.context_text,
        )
        
        assert answer, "Debe haber respuesta generada"
        print(f"   ✅ Respuesta generada: {len(answer)} caracteres")
        print(f"   ✅ Primeros 200 chars: {answer[:200]}...")
        
        # Verificar que la respuesta es coherente
        assert len(answer) > 50, "La respuesta debe tener contenido sustancial"
        
        print("\n✅ TEST 3 PASADO: Flujo completo funciona correctamente")
        return {"rag_result": rag_result, "answer": answer}
        
    except Exception as e:
        print(f"\n❌ ERROR en TEST 3: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        db.close()


def main():
    """Ejecuta todos los tests"""
    
    print("\n" + "=" * 80)
    print("SUITE DE TESTS: Verificación Refactor RAG/LLM")
    print("=" * 80)
    
    results = []
    
    # Test 1: RAG solo recupera
    rag_result = test_rag_retrieves_context_only()
    results.append(("RAG solo recupera contexto", rag_result is not None))
    
    # Test 2: Response builder genera respuestas
    answer = test_response_builder_generates_answer()
    results.append(("Response builder genera respuestas", answer is not None))
    
    # Test 3: Flujo completo
    full_flow = test_full_flow()
    results.append(("Flujo completo RAG → LLM", full_flow is not None))
    
    # Resumen
    print("\n" + "=" * 80)
    print("RESUMEN FINAL")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests pasados")
    
    if passed == total:
        print("\n🎉 ¡Todos los tests pasaron! El refactor funciona correctamente.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) fallaron")
        return 1


if __name__ == "__main__":
    sys.exit(main())

