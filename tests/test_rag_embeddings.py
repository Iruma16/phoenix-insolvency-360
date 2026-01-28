"""
Test para verificar que el sistema RAG funciona correctamente
con las dimensiones de embeddings correctas.
"""

from dotenv import load_dotenv

from app.core.database import get_db
from app.core.variables import DATA
from app.models.case import Case
from app.models.document import Document
from app.rag.case_rag.retrieve import rag_answer_internal
from app.services.document_chunk_pipeline import build_document_chunks_for_case
from app.services.embeddings_pipeline import build_embeddings_for_case, get_case_collection

# Cargar variables de entorno
load_dotenv()


def test_rag_embeddings():
    """Test que verifica que el RAG funciona con dimensiones correctas de embeddings."""

    print("=" * 60)
    print("TEST: Verificación de RAG con dimensiones correctas")
    print("=" * 60)

    db = next(get_db())

    try:
        # --------------------------------------------------
        # 1️⃣ Crear caso de prueba
        # --------------------------------------------------
        print("\n[1/6] Creando caso de prueba...")
        case = Case(
            name="Test RAG Embeddings",
            client_ref="TEST_RAG",
            status="active",
        )
        db.add(case)
        db.flush()
        case_id = case.case_id
        print(f"✅ Caso creado: {case_id}")

        # --------------------------------------------------
        # 2️⃣ Crear archivo de prueba con contenido relevante
        # --------------------------------------------------
        print("\n[2/6] Creando archivo de prueba...")
        test_dir = DATA / "test_rag" / "cases" / case_id / "documents"
        test_dir.mkdir(parents=True, exist_ok=True)

        test_file_path = test_dir / "test_rag_doc.txt"
        test_content = """
        Este es un documento de prueba para el sistema RAG.
        Contiene información sobre insolvencia y administración concursal.
        El administrador tiene responsabilidades legales específicas.
        La documentación debe ser analizada cuidadosamente para detectar posibles fraudes.
        Los contratos deben revisarse en detalle para identificar riesgos legales.
        """
        test_file_path.write_text(test_content.strip())
        print(f"✅ Archivo creado: {test_file_path}")

        # --------------------------------------------------
        # 3️⃣ Crear documento en la base de datos
        # --------------------------------------------------
        print("\n[3/6] Creando documento en BD...")
        from datetime import datetime

        document = Document(
            case_id=case_id,
            filename="test_rag_doc.txt",
            doc_type="contrato",
            source="test",
            date_start=datetime(2024, 1, 1),
            date_end=datetime(2024, 12, 31),
            reliability="original",
            file_format="txt",
            storage_path=str(test_file_path),
        )
        db.add(document)
        db.commit()
        print(f"✅ Documento creado: {document.document_id}")

        # --------------------------------------------------
        # 4️⃣ Generar chunks
        # --------------------------------------------------
        print("\n[4/6] Generando chunks...")
        build_document_chunks_for_case(
            db=db,
            case_id=case_id,
            overwrite=True,
        )
        db.commit()

        from app.models.document_chunk import DocumentChunk

        chunks_count = db.query(DocumentChunk).filter(DocumentChunk.case_id == case_id).count()
        print(f"✅ Chunks generados: {chunks_count}")

        # --------------------------------------------------
        # 5️⃣ Generar embeddings
        # --------------------------------------------------
        print("\n[5/6] Generando embeddings...")
        build_embeddings_for_case(db=db, case_id=case_id)

        # Verificar que la colección tiene embeddings
        collection = get_case_collection(case_id)
        embeddings_count = collection.count()
        print(f"✅ Embeddings en vectorstore: {embeddings_count}")

        # Verificar dimensiones de la colección
        # (ChromaDB infiere las dimensiones del primer embedding insertado)
        from app.core.variables import EMBEDDING_MODEL

        expected_dim = (
            3072 if "3-large" in EMBEDDING_MODEL else 1536 if "3-small" in EMBEDDING_MODEL else None
        )

        if embeddings_count > 0:
            # Obtener embeddings explícitamente para verificar dimensiones
            sample_result = collection.get(limit=1, include=["embeddings"])
            if sample_result.get("embeddings") and len(sample_result["embeddings"]) > 0:
                dim = len(sample_result["embeddings"][0])
                print(f"✅ Dimensiones de embeddings en vectorstore: {dim}")

                if expected_dim:
                    assert (
                        dim == expected_dim
                    ), f"❌ ERROR: Dimensiones incorrectas. Esperadas: {expected_dim}, Obtenidas: {dim}"
                    print(f"✅ Dimensiones correctas ({dim}) para {EMBEDDING_MODEL}")
                else:
                    print(f"ℹ️  Modelo: {EMBEDDING_MODEL}, dimensiones: {dim}")
            else:
                print("ℹ️  No se pudieron obtener las dimensiones directamente de ChromaDB")
                print(f"ℹ️  Modelo configurado: {EMBEDDING_MODEL}")
                if expected_dim:
                    print(f"ℹ️  Dimensiones esperadas: {expected_dim}")

        # --------------------------------------------------
        # 6️⃣ Hacer query RAG (esto es donde fallaba antes)
        # --------------------------------------------------
        print("\n[6/6] Probando query RAG...")
        question = "¿Qué responsabilidades tiene el administrador?"

        result = rag_answer_internal(
            db=db,
            case_id=case_id,
            question=question,
            top_k=3,
        )

        print("✅ Query completada exitosamente")
        print(f"   Status: {result.status}")
        print(f"   Confianza: {result.confidence}")
        print(f"   Fuentes encontradas: {len(result.sources)}")
        print(
            f"   Contexto disponible: {len(result.context_text) if result.context_text else 0} caracteres"
        )
        print(f"   Warnings: {result.warnings}")

        # Verificar que no hubo errores de dimensiones (esto es lo crítico)
        assert (
            result.status in ["OK", "PARTIAL_CONTEXT", "NO_RELEVANT_CONTEXT"]
        ), f"❌ ERROR: Status inesperado: {result.status}. Posible error de dimensiones de embeddings."
        assert result.context_text is not None, "❌ ERROR: El contexto está vacío"

        # Nota: no llamamos a LLM en tests (debe ser determinista y offline).
        # Basta con verificar que existe contexto cuando procede.
        if result.context_text:
            assert result.context_text.strip(), "❌ ERROR: El contexto está vacío"

        # Verificar que la query se completó sin errores de dimensiones
        # Si llegamos aquí, significa que las dimensiones coincidieron correctamente
        print("✅ Verificación crítica: No hubo errores de dimensiones de embeddings")
        print(
            "   (El error 'Collection expecting embedding with dimension of X, got Y' no ocurrió)"
        )

        print("\n" + "=" * 60)
        print("✅ TEST COMPLETADO EXITOSAMENTE")
        print("=" * 60)
        print(f"\nCaso de prueba creado: {case_id}")
        print("Para limpiar, puedes eliminar:")
        from app.core.variables import CASES_VECTORSTORE_BASE

        print(f"  - Vectorstore: {CASES_VECTORSTORE_BASE / case_id / 'vectorstore'}")
        print(f"  - Archivos: {DATA / 'test_rag' / 'cases' / case_id}")
        print(f"  - Y eliminar el caso de la BD con case_id: {case_id}")

        return case_id

    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ TEST FALLÓ")
        print("=" * 60)
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    test_rag_embeddings()
