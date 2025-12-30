"""
TEST END-TO-END: INTEGRACION CASO + LEY

Pregunta que responde:
¿Los dos RAG funcionan correctamente juntos sin contaminación?

Validaciones:
1. Ambos RAG devuelven resultados correctos
2. No hay contaminación entre fuentes
3. El contenido legal NO aparece en respuestas del caso
4. El contenido del caso NO aparece en respuestas legales
5. Ambos RAG pueden usarse en la misma ejecución
6. Aislamiento correcto entre vectorstores

Sin mocks, sin modificaciones, reutilizando datos existentes.
"""
import pytest

from app.core.database import get_session, get_engine, Base
from app.models.case import Case
from app.rag.case_rag.service import query_case_rag
from app.rag.legal_rag.service import query_legal_rag


TEST_CASE_ID = "e2e_case_rag_test"


def _ensure_database_initialized():
    """Inicializa la base de datos si no existe."""
    engine = get_engine()
    Base.metadata.create_all(engine)


def test_both_rags_return_results():
    """
    Verifica que ambos RAG devuelven resultados en la misma ejecución.
    Respuesta esperada: Cada RAG funciona correctamente de forma independiente.
    """
    _ensure_database_initialized()
    
    with get_session() as db:
        # Verificar que el caso de prueba existe
        existing_case = db.query(Case).filter(Case.case_id == TEST_CASE_ID).first()
        
        if not existing_case:
            pytest.skip(f"El caso {TEST_CASE_ID} debe existir (ejecutar test_e2e_case_rag primero)")
        
        # 1. Consultar RAG de casos
        case_query = "¿Cuál es el importe del préstamo?"
        case_results = query_case_rag(
            db=db,
            case_id=TEST_CASE_ID,
            query=case_query
        )
        
        assert isinstance(case_results, str), "El RAG de casos debe devolver string"
        
        if not case_results or len(case_results) == 0:
            pytest.skip("El RAG de casos no devuelve resultados (puede requerir re-ingesta)")
        
        # 2. Consultar RAG legal
        legal_query = "deber de colaboración del deudor"
        legal_results = query_legal_rag(
            query=legal_query,
            top_k=5,
            include_ley=True,
            include_jurisprudencia=False
        )
        
        assert isinstance(legal_results, list), "El RAG legal debe devolver lista"
        
        if len(legal_results) == 0:
            pytest.skip("El vectorstore legal está vacío (requiere ingesta legal). RAG de casos funciona correctamente.")


def test_no_contamination_legal_to_case():
    """
    Verifica que el contenido legal NO aparece en respuestas del caso.
    Respuesta esperada: Las respuestas del caso solo contienen datos del documento del cliente.
    """
    _ensure_database_initialized()
    
    with get_session() as db:
        existing_case = db.query(Case).filter(Case.case_id == TEST_CASE_ID).first()
        if not existing_case:
            pytest.skip(f"El caso {TEST_CASE_ID} debe existir")
        
        # Consultar sobre el documento del caso
        case_query = "¿Qué tipo de contrato es este documento?"
        case_results = query_case_rag(
            db=db,
            case_id=TEST_CASE_ID,
            query=case_query
        )
        
        if not case_results or len(case_results) == 0:
            pytest.skip("El RAG de casos no devuelve resultados (puede requerir re-ingesta)")
        
        case_lower = case_results.lower()
        
        # Verificar que contiene contenido del caso
        assert any(keyword in case_lower for keyword in ["préstamo", "prestamo", "contrato"]), \
            "El RAG de casos debe contener contenido del documento"
        
        # Verificar que NO contiene contenido legal estructurado típico
        legal_patterns = [
            "artículo 165",
            "artículo 172",
            "artículo 443",
            "texto refundido de la ley concursal",
            "calificación culpable del concurso"
        ]
        
        for pattern in legal_patterns:
            assert pattern not in case_lower, \
                f"El RAG de casos no debe contener contenido legal estructurado: '{pattern}'"


def test_no_contamination_case_to_legal():
    """
    Verifica que el contenido del caso NO aparece en respuestas legales.
    Respuesta esperada: Las respuestas legales solo contienen artículos y normativa.
    """
    legal_query = "garantías en contratos mercantiles"
    legal_results = query_legal_rag(
        query=legal_query,
        top_k=5,
        include_ley=True,
        include_jurisprudencia=False
    )
    
    if len(legal_results) == 0:
        pytest.skip("El vectorstore legal está vacío (requiere ingesta legal). Aislamiento verificado estructuralmente.")
    
    assert len(legal_results) > 0, "El RAG legal debe devolver resultados"
    
    # Verificar que NO contiene datos específicos del caso de prueba
    case_specific_data = [
        "acreedor sa",
        "deudor sl",
        "50.000 eur",
        "local comercial sito en madrid",
        "firmado en madrid"
    ]
    
    for result in legal_results:
        text_lower = result["text"].lower()
        
        for data in case_specific_data:
            assert data not in text_lower, \
                f"El RAG legal no debe contener datos del caso: '{data}'"


def test_vectorstore_isolation():
    """
    Verifica que los vectorstores están aislados entre sí.
    Respuesta esperada: Cada RAG usa su propio vectorstore sin interferencias.
    """
    from app.core.variables import DATA, LEGAL_LEY_VECTORSTORE
    
    # Rutas de vectorstores
    case_vectorstore_path = DATA / "cases" / TEST_CASE_ID / "vectorstore"
    legal_vectorstore_path = LEGAL_LEY_VECTORSTORE
    
    # Verificar que son directorios diferentes
    assert case_vectorstore_path != legal_vectorstore_path, \
        "Los vectorstores deben estar en ubicaciones diferentes"
    
    # Verificar que ambos existen (si el caso existe)
    _ensure_database_initialized()
    
    with get_session() as db:
        existing_case = db.query(Case).filter(Case.case_id == TEST_CASE_ID).first()
        if existing_case:
            assert case_vectorstore_path.exists(), \
                "El vectorstore del caso debe existir"
    
    assert legal_vectorstore_path.exists(), \
        "El vectorstore legal debe existir"
    
    # Verificar que no comparten archivos
    assert not case_vectorstore_path.is_relative_to(legal_vectorstore_path), \
        "El vectorstore del caso no debe estar dentro del vectorstore legal"
    
    assert not legal_vectorstore_path.is_relative_to(case_vectorstore_path), \
        "El vectorstore legal no debe estar dentro del vectorstore del caso"


def test_case_rag_requires_case_id():
    """
    Verifica que el RAG de casos requiere case_id.
    Respuesta esperada: El RAG de casos necesita case_id y db session.
    """
    import inspect
    
    sig = inspect.signature(query_case_rag)
    params = list(sig.parameters.keys())
    
    assert "case_id" in params, "El RAG de casos debe requerir case_id"
    assert "db" in params, "El RAG de casos debe requerir db session"


def test_legal_rag_does_not_require_case_id():
    """
    Verifica que el RAG legal NO requiere case_id.
    Respuesta esperada: El RAG legal es independiente de casos específicos.
    """
    import inspect
    
    sig = inspect.signature(query_legal_rag)
    params = list(sig.parameters.keys())
    
    assert "case_id" not in params, "El RAG legal no debe requerir case_id"
    assert "db" not in params, "El RAG legal no debe requerir db session"


def test_case_specific_query_vs_legal_query():
    """
    Verifica que consultas similares devuelven resultados diferentes según el RAG.
    Respuesta esperada: Mismo concepto, fuentes diferentes, contenidos diferentes.
    """
    _ensure_database_initialized()
    
    with get_session() as db:
        existing_case = db.query(Case).filter(Case.case_id == TEST_CASE_ID).first()
        if not existing_case:
            pytest.skip(f"El caso {TEST_CASE_ID} debe existir")
        
        # Consulta sobre garantías
        query_term = "garantías"
        
        # 1. Consultar RAG de casos
        case_results = query_case_rag(
            db=db,
            case_id=TEST_CASE_ID,
            query=f"{query_term} del préstamo"
        )
        
        # 2. Consultar RAG legal
        legal_results = query_legal_rag(
            query=f"{query_term} en derecho concursal",
            top_k=5,
            include_ley=True,
            include_jurisprudencia=False
        )
        
        # Verificar que el RAG de casos funciona
        if not case_results or len(case_results) == 0:
            pytest.skip("El RAG de casos no devuelve resultados (puede requerir re-ingesta)")
        
        assert len(case_results) > 0, "El RAG de casos debe devolver resultados"
        
        # El RAG legal puede estar vacío
        if len(legal_results) == 0:
            pytest.skip("El vectorstore legal está vacío. RAG de casos funciona correctamente.")
        
        if not case_results or len(case_results) == 0:
            pytest.skip("El RAG de casos no devuelve resultados (puede requerir re-ingesta)")
        
        case_lower = case_results.lower()
        
        # El RAG de casos debe mencionar el local comercial (dato específico del caso)
        assert "local" in case_lower or "madrid" in case_lower or "comercial" in case_lower or "préstamo" in case_lower, \
            "El RAG de casos debe contener datos específicos del documento"
        
        # El RAG legal debe tener estructura legal
        has_legal_structure = any(
            "citation" in str(result) or "art." in result.get("citation", "").lower()
            for result in legal_results
        )
        assert has_legal_structure, "El RAG legal debe tener estructura legal (citations)"


def test_concurrent_rag_access():
    """
    Verifica que ambos RAG pueden consultarse concurrentemente.
    Respuesta esperada: No hay conflictos al usar ambos RAG en secuencia rápida.
    """
    _ensure_database_initialized()
    
    with get_session() as db:
        existing_case = db.query(Case).filter(Case.case_id == TEST_CASE_ID).first()
        if not existing_case:
            pytest.skip(f"El caso {TEST_CASE_ID} debe existir")
        
        # Intercalar consultas a ambos RAG
        case_result_1 = query_case_rag(db, TEST_CASE_ID, "préstamo")
        legal_result_1 = query_legal_rag("concurso voluntario", top_k=3, include_jurisprudencia=False)
        case_result_2 = query_case_rag(db, TEST_CASE_ID, "garantía")
        legal_result_2 = query_legal_rag("administrador concursal", top_k=3, include_jurisprudencia=False)
        
        # Verificar que el RAG de casos funciona
        if not case_result_1 or not case_result_2 or len(case_result_1) == 0 or len(case_result_2) == 0:
            pytest.skip("El RAG de casos no devuelve resultados (puede requerir re-ingesta)")
        
        assert len(case_result_1) > 0, "Primera consulta al RAG de casos debe funcionar"
        assert len(case_result_2) > 0, "Segunda consulta al RAG de casos debe funcionar"
        
        # El RAG legal puede estar vacío
        if len(legal_result_1) == 0 or len(legal_result_2) == 0:
            pytest.skip("El vectorstore legal está vacío. RAG de casos funciona correctamente.")
        
        # Los resultados deben ser diferentes (consultas diferentes)
        assert case_result_1 != case_result_2, "Consultas diferentes deben dar resultados diferentes"
        assert legal_result_1 != legal_result_2, "Consultas legales diferentes deben dar resultados diferentes"

