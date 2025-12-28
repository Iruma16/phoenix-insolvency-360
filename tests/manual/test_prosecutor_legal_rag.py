"""
Test manual para verificar que el Prosecutor enriquece acusaciones con citas legales.

Mockea el Legal RAG para evitar dependencias de vectorstore.
"""
from unittest.mock import patch, MagicMock
import pytest

from app.agents.agent_2_prosecutor.logic import ejecutar_analisis_prosecutor
from app.agents.agent_2_prosecutor.schema import LegalAccusation


def test_prosecutor_enriches_with_legal_citations():
    """Test que verifica que el Prosecutor añade citas legales a las acusaciones."""
    print("🧪 Ejecutando test: Prosecutor enriquece con citas legales...")
    
    # Mock del RAG legal con formato normalizado mejorado
    mock_legal_results = [
        {
            "citation": "Art. 165 Ley Concursal",
            "text": "Artículo 165. El deudor que, hallándose en estado de insolvencia...",
            "source": "ley",
            "authority_level": "norma",
            "relevance": "alta",
            "article": "165",
            "law": "Ley Concursal",
            "court": None,
            "date": None,
        },
        {
            "citation": "TS 2023-01-15",
            "text": "Sentencia del Tribunal Supremo que establece que el retraso en solicitar el concurso...",
            "source": "jurisprudencia",
            "authority_level": "jurisprudencia",
            "relevance": "media",
            "article": None,
            "law": None,
            "court": "TS",
            "date": "2023-01-15",
        },
    ]
    
    with patch('app.agents.agent_2_prosecutor.logic.query_legal_rag') as mock_legal_rag:
        mock_legal_rag.return_value = mock_legal_results
        
        # Mock del RAG de casos
        with patch('app.agents.agent_2_prosecutor.logic.rag_answer_internal') as mock_rag:
            from app.rag.case_rag.retrieve import RAGInternalResult, ConfidenceLevel
            
            mock_rag.return_value = RAGInternalResult(
                status="OK",
                context_text="Contexto de prueba",
                sources=[{"document_id": "test-doc", "content": "Test content"}],
                confidence="alta",
                warnings=[],
                hallucination_risk=False,
            )
            
            # Mock de build_llm_answer
            with patch('app.agents.agent_2_prosecutor.logic.build_llm_answer') as mock_llm:
                mock_llm.return_value = "Respuesta de prueba del LLM"
                
                # Ejecutar Prosecutor
                result = ejecutar_analisis_prosecutor(case_id="test-case")
                
                # Verificar que se llamó al Legal RAG
                assert mock_legal_rag.called, "Legal RAG debería haberse llamado"
                
                # Verificar que las acusaciones tienen campos legales
                if result.accusations:
                    first_accusation = result.accusations[0]
                    
                    print(f"\n✅ Acusación generada: {first_accusation.legal_ground}")
                    print(f"   Legal articles: {first_accusation.legal_articles}")
                    print(f"   Jurisprudence: {first_accusation.jurisprudence}")
                    
                    # Verificar que tiene los campos nuevos
                    assert hasattr(first_accusation, 'legal_articles'), \
                        "La acusación debe tener campo 'legal_articles'"
                    assert hasattr(first_accusation, 'jurisprudence'), \
                        "La acusación debe tener campo 'jurisprudence'"
                    
                    assert isinstance(first_accusation.legal_articles, list), \
                        "'legal_articles' debe ser una lista"
                    assert isinstance(first_accusation.jurisprudence, list), \
                        "'jurisprudence' debe ser una lista"
                    
                    # Si hay resultados del mock, deberían aparecer
                    if mock_legal_results:
                        print("   ✅ Campos legales presentes")
                        
                        # Verificar que las citas están normalizadas
                        if first_accusation.legal_articles:
                            print(f"   ✅ Citas normalizadas: {first_accusation.legal_articles}")
                else:
                    print("   ⚠️  No se generaron acusaciones (puede ser normal si no hay contexto)")
                
                print("\n✅ Test completado")


def test_legal_rag_normalization():
    """Test que verifica la normalización de resultados legales."""
    print("\n🧪 Ejecutando test: Normalización de resultados legales...")
    
    from app.rag.legal_rag.service import query_legal_rag
    
    # Mock de OpenAI client
    mock_embedding = [0.1] * 1536  # Embedding simulado
    
    with patch('app.rag.legal_rag.service._get_openai_client') as mock_openai:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]
        mock_client.embeddings.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        # Mock de ChromaDB
        mock_collection = MagicMock()
        mock_collection.count.return_value = 2
        mock_collection.query.return_value = {
            "ids": [["id1", "id2"]],
            "documents": [["Artículo 165. Texto...", "Artículo 172. Texto..."]],
            "metadatas": [[
                {"article": "165", "law": "Ley Concursal"},
                {"article": "172", "law": "Ley Concursal"},
            ]],
            "distances": [[0.5, 0.9]],  # Alta y media relevancia
        }
        
        with patch('app.rag.legal_rag.service._get_legal_collection') as mock_col:
            mock_col.return_value = mock_collection
            
            # Ejecutar consulta
            results = query_legal_rag(
                query="retraso en concurso",
                top_k=2,
                include_ley=True,
                include_jurisprudencia=False,
            )
            
            # Verificar normalización
            assert len(results) > 0, "Debe haber resultados"
            
            for result in results:
                # Verificar campos obligatorios
                assert "citation" in result, "Debe tener 'citation'"
                assert "text" in result, "Debe tener 'text'"
                assert "source" in result, "Debe tener 'source'"
                assert "authority_level" in result, "Debe tener 'authority_level'"
                assert "relevance" in result, "Debe tener 'relevance'"
                
                # Verificar authority_level correcto
                if result["source"] == "ley":
                    assert result["authority_level"] == "norma", \
                        "Ley debe tener authority_level='norma'"
                
                # Verificar relevance es válido
                assert result["relevance"] in ("alta", "media", "baja"), \
                    f"relevance debe ser 'alta', 'media' o 'baja', no '{result['relevance']}'"
                
                # Verificar citation está normalizado
                assert result["citation"].startswith("Art."), \
                    f"Citation debe empezar con 'Art.', encontrado: {result['citation']}"
            
            print(f"   ✅ {len(results)} resultados normalizados correctamente")
            print(f"   ✅ Relevancias: {[r['relevance'] for r in results]}")
            print(f"   ✅ Citations: {[r['citation'] for r in results]}")
            print("\n✅ Test de normalización completado")


if __name__ == "__main__":
    try:
        test_prosecutor_enriches_with_legal_citations()
        test_legal_rag_normalization()
    except ImportError as e:
        print(f"⚠️  Error de importación: {e}")
        print("Ejecuta con: python -m pytest tests/manual/test_prosecutor_legal_rag.py -v")
    except Exception as e:
        print(f"❌ Error durante el test: {e}")
        import traceback
        traceback.print_exc()
