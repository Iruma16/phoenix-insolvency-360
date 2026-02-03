"""
Test end-to-end mínimo del flujo completo del Agente 1:
1. Subir documento
2. Ingesta
3. Crear chunks
4. Crear embeddings
5. Consulta RAG
6. Respuesta
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.agents.agent_1_auditor.runner import run_auditor
from app.core.database import get_session_factory
from app.rag.case_rag.service import query_case_rag
from app.services.document_chunk_pipeline import build_document_chunks_for_case
from app.services.embeddings_pipeline import build_embeddings_for_case
from app.services.folder_ingestion import ingest_file_from_path


def mock_openai_chat_completions(*args, **kwargs):
    """Mock para OpenAI chat completions."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[
        0
    ].message.content = (
        '{"summary": "Test summary", "risks": ["Test risk 1"], "next_actions": ["Test action 1"]}'
    )
    return mock_response


def mock_openai_embeddings(*args, **kwargs):
    """Mock para OpenAI embeddings."""
    mock_response = MagicMock()
    mock_response.data = [MagicMock()]
    mock_response.data[0].embedding = [0.1] * 1536
    return mock_response


def test_end_to_end_agent1():
    """
    Test end-to-end del flujo completo del Agente 1.
    """
    print("=" * 70)
    print("TEST END-TO-END AGENTE 1")
    print("=" * 70)
    print()

    SessionLocal = get_session_factory()
    db = SessionLocal()

    case_id = "case_e2e_test"
    test_doc_path = Path("clients_data/cases/case_e2e_test/test_doc.txt")

    try:
        # Crear documento de prueba
        test_doc_path.parent.mkdir(parents=True, exist_ok=True)
        test_doc_path.write_text(
            "Documento de prueba para test end-to-end. Contenido relevante del caso."
        )
        print(f"✅ Documento de prueba creado: {test_doc_path}")
        print()

        # Paso 1: Ingesta
        print("=" * 70)
        print("PASO 1: INGESTA")
        print("=" * 70)
        try:
            result = ingest_file_from_path(
                file_path=str(test_doc_path),
                case_id=case_id,
                db=db,
                doc_type="otros",
                source="test_e2e",
            )
            print("✅ Documento guardado en BD")
            print(f"   - Document ID: {result.document_id}")
            print(f"   - Filename: {result.filename}")
            db.commit()

            # Verificar en BD
            from app.models.document import Document

            doc_count = db.query(Document).filter(Document.case_id == case_id).count()
            print(f"   - Total documentos en BD para {case_id}: {doc_count}")
        except Exception as e:
            print(f"❌ Error en ingesta: {e}")
            import traceback

            traceback.print_exc()
            return
        print()

        # Paso 2: Crear chunks
        print("=" * 70)
        print("PASO 2: CREAR CHUNKS")
        print("=" * 70)
        try:
            chunks_created = build_document_chunks_for_case(db=db, case_id=case_id, overwrite=False)
            print(f"✅ Chunks creados: {chunks_created}")

            # Verificar en BD
            from app.models.document_chunk import DocumentChunk

            chunk_count = db.query(DocumentChunk).filter(DocumentChunk.case_id == case_id).count()
            print(f"   - Total chunks en BD: {chunk_count}")
        except Exception as e:
            print(f"❌ Error creando chunks: {e}")
            import traceback

            traceback.print_exc()
            return
        print()

        # Paso 3: Crear embeddings
        print("=" * 70)
        print("PASO 3: CREAR EMBEDDINGS")
        print("=" * 70)
        try:
            with patch("openai.OpenAI") as mock_openai_class:
                mock_client = MagicMock()
                mock_openai_class.return_value = mock_client
                mock_client.embeddings.create = MagicMock(side_effect=mock_openai_embeddings)

                embeddings_count = build_embeddings_for_case(db=db, case_id=case_id)
                print(f"✅ Embeddings generados: {embeddings_count}")

                # Verificar vectorstore
                from app.services.embeddings_pipeline import get_case_collection

                try:
                    collection = get_case_collection(case_id)
                    vectorstore_count = collection.count()
                    print(f"   - Embeddings en vectorstore: {vectorstore_count}")
                except Exception as e:
                    print(f"   ⚠️  No se pudo verificar vectorstore: {e}")
        except Exception as e:
            print(f"❌ Error creando embeddings: {e}")
            import traceback

            traceback.print_exc()
            return
        print()

        # Paso 4: Consulta RAG
        print("=" * 70)
        print("PASO 4: CONSULTA RAG")
        print("=" * 70)
        try:
            with patch("openai.OpenAI") as mock_openai_class:
                mock_client = MagicMock()
                mock_openai_class.return_value = mock_client
                mock_client.embeddings.create = MagicMock(side_effect=mock_openai_embeddings)

                context = query_case_rag(
                    db=db, case_id=case_id, query="¿Qué información hay sobre el caso?"
                )
                print("✅ Resultados recuperados")
                print(f"   - Longitud del contexto: {len(context)} caracteres")
                if context:
                    print(f"   - Primeros 100 caracteres: {context[:100]}...")
                else:
                    print("   ⚠️  Contexto vacío")
        except Exception as e:
            print(f"❌ Error en consulta RAG: {e}")
            import traceback

            traceback.print_exc()
            return
        print()

        # Paso 5: Ejecutar Auditor
        print("=" * 70)
        print("PASO 5: EJECUTAR AUDITOR")
        print("=" * 70)
        try:
            with patch("openai.OpenAI") as mock_openai_class:
                mock_client = MagicMock()
                mock_openai_class.return_value = mock_client
                mock_client.chat.completions.create = MagicMock(
                    side_effect=mock_openai_chat_completions
                )
                mock_client.embeddings.create = MagicMock(side_effect=mock_openai_embeddings)

                with patch(
                    "app.services.document_quality.get_document_quality_summary"
                ) as mock_quality:
                    mock_quality.return_value = {
                        "total_documents": 1,
                        "total_chunks": chunk_count,
                        "quality_score": 80,
                        "quality_level": "buena",
                        "legal_risks": [],
                        "critical_documents_missing": 0,
                    }

                    auditor_result, auditor_fallback = run_auditor(
                        case_id=case_id, question="Analiza los riesgos del caso", db=db
                    )
                    print("✅ Auditor ejecutado")
                    print(f"   - Fallback: {auditor_fallback}")
                    print(f"   - Summary: {auditor_result.summary[:100]}...")
                    print(f"   - Risks: {len(auditor_result.risks)}")
                    print(f"   - Actions: {len(auditor_result.next_actions)}")
        except Exception as e:
            print(f"❌ Error ejecutando Auditor: {e}")
            import traceback

            traceback.print_exc()
            return
        print()

        print("=" * 70)
        print("✅ TEST END-TO-END COMPLETADO EXITOSAMENTE")
        print("=" * 70)

    except Exception as e:
        print()
        print("=" * 70)
        print(f"❌ TEST FALLÓ: {e}")
        print("=" * 70)
        import traceback

        traceback.print_exc()
        raise

    finally:
        db.close()
        # Limpiar
        if test_doc_path.exists():
            test_doc_path.unlink()
            print("\n🧹 Documento de prueba eliminado")


if __name__ == "__main__":
    test_end_to_end_agent1()
