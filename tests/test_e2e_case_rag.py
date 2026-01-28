"""
TEST END-TO-END: RAG DE CASOS

Pregunta que responde:
¿Funciona el RAG de casos de principio a fin?

Validaciones:
1. Ingesta de documento
2. Almacenamiento físico
3. Generación de chunks
4. Generación de embeddings y vectorstore
5. Consulta RAG sobre el caso
6. Respuesta válida con contenido del documento

Sin mocks, sin modificaciones, usando servicios existentes.
"""
import pytest
import tempfile
from pathlib import Path

from app.core.database import get_session, get_engine, Base
from app.models.case import Case
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.folder_ingestion import ingest_file_from_path
from app.services.document_chunk_pipeline import build_document_chunks_for_case
from app.services.embeddings_pipeline import (
    get_chunks_for_case,
    get_case_collection,
    build_embeddings_for_case
)
from app.rag.case_rag.service import query_case_rag
from app.core.variables import DATA


TEST_CASE_ID = "e2e_case_rag_test"

SAMPLE_LEGAL_DOC = """
CONTRATO DE PRESTAMO MERCANTIL

Entre ACREEDOR SA (prestamista) y DEUDOR SL (prestatario) se acuerda:

Artículo 1. OBJETO
El prestamista concede al prestatario un préstamo por importe de 50.000 EUR.

Artículo 2. PLAZO
El préstamo se amortizará en 12 meses desde la fecha de firma.

Artículo 3. INTERES
Se aplicará un tipo de interés del 5% anual.

Artículo 4. GARANTIAS
El prestatario ofrece como garantía real el local comercial sito en Madrid.

Firmado en Madrid, a 15 de enero de 2024.
"""


def _ensure_database_initialized():
    """Inicializa la base de datos si no existe."""
    engine = get_engine()
    Base.metadata.create_all(engine)


@pytest.fixture(scope="module")
def test_document():
    """Crea un documento de prueba temporal."""
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.txt',
        delete=False,
        encoding='utf-8'
    ) as f:
        f.write(SAMPLE_LEGAL_DOC)
        temp_path = Path(f.name)
    
    yield temp_path
    
    if temp_path.exists():
        temp_path.unlink()


def test_case_rag_end_to_end(test_document):
    """
    Test end-to-end del RAG de casos.
    Responde: ¿Funciona el RAG de casos de principio a fin?
    """
    _ensure_database_initialized()
    
    with get_session() as db:
        
        # Preparar caso
        existing_case = db.query(Case).filter(Case.case_id == TEST_CASE_ID).first()
        if not existing_case:
            test_case = Case(case_id=TEST_CASE_ID, name="E2E Case RAG Test")
            db.add(test_case)
            db.commit()
        
        # 1. INGESTA
        document, warnings = ingest_file_from_path(
            db=db,
            file_path=test_document,
            case_id=TEST_CASE_ID,
            doc_type="contrato",
            source="e2e_test"
        )
        db.commit()
        
        assert document is not None, "El documento debe haberse creado"
        assert document.case_id == TEST_CASE_ID, "El case_id debe coincidir"
        
        # 2. ALMACENAMIENTO FISICO
        storage_path = Path(document.storage_path)
        assert storage_path.exists(), f"El documento debe existir en {storage_path}"
        
        expected_dir = DATA / "cases" / TEST_CASE_ID / "documents"
        assert storage_path.parent == expected_dir, "El documento debe estar en la carpeta correcta"
        
        with open(storage_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        assert len(file_content) > 100, "El archivo debe tener contenido"
        assert "CONTRATO DE PRESTAMO" in file_content, "El archivo debe contener el contenido original"
        
        # 3. CHUNKS
        build_document_chunks_for_case(
            db=db,
            case_id=TEST_CASE_ID,
            overwrite=True
        )
        db.commit()
        
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.case_id == TEST_CASE_ID
        ).all()
        
        assert len(chunks) > 0, "Deben haberse creado chunks"
        assert all(chunk.content for chunk in chunks), "Los chunks no deben estar vacíos"
        
        # 4. EMBEDDINGS Y VECTORSTORE
        build_embeddings_for_case(
            db=db,
            case_id=TEST_CASE_ID
        )
        
        vectorstore_path = DATA / "cases" / TEST_CASE_ID / "vectorstore"
        assert vectorstore_path.exists(), f"El vectorstore debe existir en {vectorstore_path}"
        assert vectorstore_path.is_dir(), "El vectorstore debe ser un directorio"
        
        collection = get_case_collection(TEST_CASE_ID)
        embedding_count = collection.count()
        
        assert embedding_count > 0, "La colección debe contener embeddings"
        assert embedding_count >= len(chunks), "Debe haber al menos un embedding por chunk"
        
        # 5. CONSULTA RAG
        query = "¿Cuál es el importe del préstamo?"
        
        response = query_case_rag(
            db=db,
            case_id=TEST_CASE_ID,
            query=query
        )
        
        assert response, "La respuesta RAG no debe estar vacía"
        assert isinstance(response, str), "La respuesta debe ser un string"
        assert len(response) > 0, "La respuesta debe tener contenido"
        
        # 6. VALIDACION DE RESPUESTA
        response_lower = response.lower()
        
        assert "50.000" in response or "50000" in response or "cincuenta mil" in response_lower, \
            "La respuesta debe mencionar el importe del préstamo (50.000 EUR)"
        
        assert any(keyword in response_lower for keyword in ["préstamo", "prestamo", "importe", "eur", "euro"]), \
            "La respuesta debe contener términos relacionados con el préstamo"
        
        # Verificar integridad
        db_chunks = get_chunks_for_case(db, TEST_CASE_ID)
        assert len(db_chunks) == len(chunks), "Los chunks en DB deben coincidir"


def test_cleanup_case_rag():
    """Limpieza de datos de prueba del RAG de casos."""
    _ensure_database_initialized()
    
    with get_session() as db:
        chunks_deleted = db.query(DocumentChunk).filter(
            DocumentChunk.case_id == TEST_CASE_ID
        ).delete()
        
        docs_deleted = db.query(Document).filter(
            Document.case_id == TEST_CASE_ID
        ).delete()
        
        db.commit()
        
        assert chunks_deleted >= 0, "Cleanup debe ejecutarse sin errores"
        assert docs_deleted >= 0, "Cleanup debe ejecutarse sin errores"

