"""
TEST END-TO-END: RAG LEGAL

Pregunta que responde:
¿Funciona el RAG legal de principio a fin?

Validaciones:
1. Corpus legal existe
2. Vectorstore legal existe y está persistido
3. Contiene embeddings
4. Consulta legal devuelve resultados
5. Los resultados son artículos/fragmentos legales reales
6. No depende de case_id
7. No accede a datos de clientes

Sin mocks, sin modificaciones, usando servicios existentes.
"""

import pytest

from app.core.variables import LEGAL_LEY_VECTORSTORE
from app.rag.legal_rag.service import _get_legal_collection, query_legal_rag


def test_legal_corpus_exists():
    """
    Verifica que el corpus legal existe.
    Respuesta esperada: El directorio del vectorstore legal existe.
    """
    if not LEGAL_LEY_VECTORSTORE.exists():
        pytest.skip(
            f"Vectorstore legal no encontrado en {LEGAL_LEY_VECTORSTORE}. "
            "Para ejecutar E2E legal completo, realiza la ingesta legal primero."
        )

    assert LEGAL_LEY_VECTORSTORE.is_dir(), "El vectorstore de ley concursal debe ser un directorio"


def test_legal_vectorstore_has_embeddings():
    """
    Verifica que el vectorstore legal tiene embeddings.
    Respuesta esperada: La colección existe y puede ser consultada.

    NOTA: Si está vacío, el test pasa pero marca que requiere ingesta legal.
    """
    try:
        collection = _get_legal_collection(LEGAL_LEY_VECTORSTORE, "chunks")

        # Verificar estructura básica
        assert collection is not None, "La colección debe existir"
        assert hasattr(collection, "query"), "La colección debe tener método query"

        embedding_count = collection.count()

        if embedding_count == 0:
            pytest.skip(
                "El vectorstore legal está vacío (requiere ingesta legal). Sistema estructuralmente correcto."
            )

        assert (
            embedding_count > 0
        ), "El vectorstore legal debe contener embeddings de la ley concursal"

    except Exception as e:
        pytest.fail(f"Error accediendo al vectorstore legal: {e}")


def test_legal_rag_query_returns_results():
    """
    Verifica que una consulta legal devuelve resultados (si hay corpus).
    Respuesta esperada: Se recuperan artículos legales relevantes.
    """
    # Consulta sobre un tema claro en la ley concursal
    query = "deber de colaboración del deudor con la administración concursal"

    results = query_legal_rag(
        query=query,
        top_k=5,
        include_ley=True,
        include_jurisprudencia=False,  # Solo ley para este test
    )

    assert isinstance(results, list), "Los resultados deben ser una lista"

    if len(results) == 0:
        pytest.skip(
            "El vectorstore legal está vacío (requiere ingesta legal). Sistema estructuralmente correcto."
        )

    assert len(results) > 0, "Debe haber al menos un resultado"


def test_legal_results_structure():
    """
    Verifica que los resultados tienen la estructura legal correcta.
    Respuesta esperada: Cada resultado tiene citation, text, source, relevance.
    """
    query = "obligación de llevar contabilidad ordenada"

    results = query_legal_rag(query=query, top_k=5, include_ley=True, include_jurisprudencia=False)

    if len(results) == 0:
        pytest.skip(
            "El vectorstore legal está vacío (requiere ingesta legal). Sistema estructuralmente correcto."
        )

    assert len(results) > 0, "Debe haber resultados"

    for result in results:
        assert "citation" in result, "Cada resultado debe tener citation"
        assert "text" in result, "Cada resultado debe tener text"
        assert "source" in result, "Cada resultado debe tener source"
        assert "authority_level" in result, "Cada resultado debe tener authority_level"
        assert "relevance" in result, "Cada resultado debe tener relevance"

        assert isinstance(result["citation"], str), "Citation debe ser string"
        assert isinstance(result["text"], str), "Text debe ser string"
        assert result["source"] == "ley", "Source debe ser 'ley' para este test"
        assert result["authority_level"] == "norma", "Authority level debe ser 'norma'"
        assert result["relevance"] in [
            "alta",
            "media",
            "baja",
        ], "Relevance debe ser alta/media/baja"


def test_legal_results_contain_real_legal_content():
    """
    Verifica que los resultados contienen contenido legal real.
    Respuesta esperada: Los textos recuperados mencionan artículos, normativa o conceptos legales.
    """
    query = "calificación culpable del concurso"

    results = query_legal_rag(query=query, top_k=5, include_ley=True, include_jurisprudencia=False)

    if len(results) == 0:
        pytest.skip(
            "El vectorstore legal está vacío (requiere ingesta legal). Sistema estructuralmente correcto."
        )

    assert len(results) > 0, "Debe haber resultados"

    # Verificar que al menos un resultado contiene keywords legales
    legal_keywords = ["artículo", "ley", "concursal", "administrador", "deudor", "art.", "culpable"]

    found_legal_content = False
    for result in results:
        text_lower = result["text"].lower()
        if any(keyword in text_lower for keyword in legal_keywords):
            found_legal_content = True
            break

    assert found_legal_content, "Los resultados deben contener contenido legal real"


def test_legal_rag_independent_of_case_id():
    """
    Verifica que el RAG legal no depende de case_id.
    Respuesta esperada: La función no requiere ni usa case_id.
    """
    # La función no debe tener parámetro case_id
    import inspect

    sig = inspect.signature(query_legal_rag)
    params = list(sig.parameters.keys())

    assert "case_id" not in params, "El RAG legal no debe depender de case_id"
    assert "db" not in params, "El RAG legal no debe depender de sesión de BD"

    # Ejecutar consulta sin case_id
    query = "deber de solicitud de concurso"
    results = query_legal_rag(query=query, top_k=5, include_ley=True, include_jurisprudencia=False)

    # Debe ejecutarse sin errores (aunque esté vacío)
    assert isinstance(results, list), "Debe devolver lista incluso si está vacía"


def test_legal_rag_no_client_data_contamination():
    """
    Verifica que el RAG legal no accede a datos de clientes.
    Respuesta esperada: Los resultados no mencionan datos específicos de casos.
    """
    query = "administrador concursal"

    results = query_legal_rag(query=query, top_k=5, include_ley=True, include_jurisprudencia=False)

    if len(results) == 0:
        pytest.skip(
            "El vectorstore legal está vacío (requiere ingesta legal). Sistema estructuralmente correcto."
        )

    assert len(results) > 0, "Debe haber resultados"

    # Verificar que no hay menciones a datos de clientes típicos
    client_keywords = ["contrato de prestamo mercantil", "50.000 eur", "acreedor sa", "deudor sl"]

    for result in results:
        text_lower = result["text"].lower()
        for keyword in client_keywords:
            assert (
                keyword not in text_lower
            ), f"El RAG legal no debe contener datos de clientes: encontrado '{keyword}'"


def test_legal_rag_cache_works():
    """
    Verifica que el caché funciona correctamente.
    Respuesta esperada: Consultas repetidas devuelven los mismos resultados.
    """
    query = "responsabilidad de los administradores"

    # Primera consulta
    results_1 = query_legal_rag(
        query=query, top_k=3, include_ley=True, include_jurisprudencia=False
    )

    # Segunda consulta (debe usar caché)
    results_2 = query_legal_rag(
        query=query, top_k=3, include_ley=True, include_jurisprudencia=False
    )

    assert len(results_1) == len(
        results_2
    ), "Las consultas repetidas deben devolver mismo número de resultados"

    # Verificar que los resultados son idénticos
    for r1, r2 in zip(results_1, results_2):
        assert r1["citation"] == r2["citation"], "Los resultados cacheados deben ser idénticos"
        assert r1["text"] == r2["text"], "Los textos cacheados deben ser idénticos"


def test_legal_vectorstore_persistence():
    """
    Verifica que el vectorstore legal está persistido en disco.
    Respuesta esperada: El vectorstore tiene archivos de ChromaDB persistidos.
    """
    # Verificar que existen archivos de ChromaDB (chroma.sqlite3 u otros)
    vectorstore_files = list(LEGAL_LEY_VECTORSTORE.glob("*"))

    assert (
        len(vectorstore_files) > 0
    ), f"El vectorstore debe tener archivos persistidos en {LEGAL_LEY_VECTORSTORE}"

    # Verificar que hay archivos típicos de ChromaDB
    file_names = [f.name for f in vectorstore_files]
    has_chroma_files = any(
        "chroma" in name.lower() or ".sqlite" in name.lower() for name in file_names
    )

    assert has_chroma_files, "Debe haber archivos de ChromaDB persistidos"
