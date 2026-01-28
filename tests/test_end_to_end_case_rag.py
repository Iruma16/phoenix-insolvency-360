"""
Test end-to-end del sistema Phoenix Legal.

Valida el flujo completo:
1. Ingesta de documento
2. Chunking
3. Generación de embeddings
4. Consulta RAG

Este test responde de forma inequívoca:
"¿El sistema Phoenix Legal funciona end-to-end?"
"""
import pytest
import tempfile
from pathlib import Path
from datetime import datetime

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


# Asegurar que las tablas existan
def _ensure_database_initialized():
    """Inicializa la base de datos si no existe."""
    engine = get_engine()
    Base.metadata.create_all(engine)


# Test case ID único
TEST_CASE_ID = "case_e2e_test"

# Documento de prueba realista
SAMPLE_LEGAL_DOC = """
CONTRATO DE PRESTAMO MERCANTIL

Entre:
- ACREEDOR SA (prestamista)
- DEUDOR SL (prestatario)

Se acuerda:

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


@pytest.fixture(scope="module")
def test_document_path():
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
    
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


def test_end_to_end_flow(test_document_path):
    """
    Test end-to-end del sistema completo.
    
    PASO 1: Ingesta de documento
    PASO 2: Verificación de almacenamiento físico
    PASO 3: Generación de chunks
    PASO 4: Generación de embeddings
    PASO 5: Consulta RAG
    PASO 6: Validación de respuesta
    """
    
    print("\n" + "=" * 80)
    print("TEST END-TO-END: Phoenix Legal System")
    print("=" * 80)
    
    # Asegurar que la base de datos está inicializada
    _ensure_database_initialized()
    
    with get_session() as db:
        
        # ================================================================
        # PASO 0: CREAR CASO SI NO EXISTE
        # ================================================================
        print("\n[PASO 0] Preparación del caso...")
        existing_case = db.query(Case).filter(Case.case_id == TEST_CASE_ID).first()
        if not existing_case:
            test_case = Case(
                case_id=TEST_CASE_ID,
                name="Test Company E2E"
            )
            db.add(test_case)
            db.commit()
            print(f"  ✅ Caso creado: {TEST_CASE_ID}")
        else:
            print(f"  ✅ Caso ya existe: {TEST_CASE_ID}")
        
        # ================================================================
        # PASO 1: INGESTA DE DOCUMENTO
        # ================================================================
        print("\n[PASO 1] Ingesta de documento...")
        print(f"  - Case ID: {TEST_CASE_ID}")
        print(f"  - Documento: {test_document_path.name}")
        
        document, warnings = ingest_file_from_path(
            db=db,
            file_path=test_document_path,
            case_id=TEST_CASE_ID,
            doc_type="contrato",
            source="e2e_test"
        )
        
        # Commit explícito después de ingesta
        db.commit()
        
        # VALIDACION 1: Documento creado
        assert document is not None, "El documento debe haberse creado"
        assert document.case_id == TEST_CASE_ID, "El case_id debe coincidir"
        assert document.doc_type == "contrato", "El doc_type debe ser 'contrato'"
        
        print(f"  ✅ Documento creado: ID={document.document_id}")
        
        # ================================================================
        # PASO 2: VERIFICACION DE ALMACENAMIENTO FISICO
        # ================================================================
        print("\n[PASO 2] Verificación de almacenamiento físico...")
        
        # Verificar que el documento existe en disco
        storage_path = Path(document.storage_path)
        assert storage_path.exists(), f"El documento debe existir en {storage_path}"
        
        # Verificar estructura de directorios
        expected_dir = DATA / "cases" / TEST_CASE_ID / "documents"
        assert storage_path.parent == expected_dir, "El documento debe estar en la carpeta correcta"
        
        # Verificar que el archivo contiene el texto
        with open(storage_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        assert len(file_content) > 100, "El archivo debe tener contenido"
        assert "CONTRATO DE PRESTAMO" in file_content, "El archivo debe contener contenido del documento original"
        
        print(f"  ✅ Documento almacenado en: {storage_path}")
        print(f"  ✅ Archivo verificado: {len(file_content)} caracteres")
        
        # ================================================================
        # PASO 3: GENERACION DE CHUNKS
        # ================================================================
        print("\n[PASO 3] Generación de chunks...")
        
        build_document_chunks_for_case(
            db=db,
            case_id=TEST_CASE_ID,
            overwrite=True
        )
        
        # Commit después de crear chunks
        db.commit()
        
        # VALIDACION 3: Chunks creados
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.case_id == TEST_CASE_ID
        ).all()
        
        assert len(chunks) > 0, "Deben haberse creado chunks"
        assert all(chunk.content for chunk in chunks), "Los chunks no deben estar vacíos"
        
        print(f"  ✅ Chunks creados: {len(chunks)}")
        print(f"  ✅ Contenido total: {sum(len(c.content) for c in chunks)} caracteres")
        
        # ================================================================
        # PASO 4: GENERACION DE EMBEDDINGS
        # ================================================================
        print("\n[PASO 4] Generación de embeddings...")
        
        # Generar embeddings
        build_embeddings_for_case(
            db=db,
            case_id=TEST_CASE_ID
        )
        
        # VALIDACION 4: Vectorstore existe y tiene embeddings
        vectorstore_path = DATA / "cases" / TEST_CASE_ID / "vectorstore"
        assert vectorstore_path.exists(), f"El vectorstore debe existir en {vectorstore_path}"
        assert vectorstore_path.is_dir(), "El vectorstore debe ser un directorio"
        
        # Verificar que la colección tiene embeddings
        collection = get_case_collection(TEST_CASE_ID)
        embedding_count = collection.count()
        
        assert embedding_count > 0, "La colección debe contener embeddings"
        assert embedding_count >= len(chunks), "Debe haber al menos un embedding por chunk"
        
        print(f"  ✅ Vectorstore creado en: {vectorstore_path}")
        print(f"  ✅ Embeddings generados: {embedding_count}")
        
        # ================================================================
        # PASO 5: CONSULTA RAG
        # ================================================================
        print("\n[PASO 5] Consulta RAG...")
        
        query = "¿Cuál es el importe del préstamo?"
        
        response = query_case_rag(
            db=db,
            case_id=TEST_CASE_ID,
            query=query
        )
        
        # VALIDACION 5: Respuesta RAG válida
        assert response, "La respuesta RAG no debe estar vacía"
        assert isinstance(response, str), "La respuesta debe ser un string"
        assert len(response) > 0, "La respuesta debe tener contenido"
        
        print(f"  ✅ Consulta ejecutada: '{query}'")
        print(f"  ✅ Respuesta obtenida: {len(response)} caracteres")
        
        # ================================================================
        # PASO 6: VALIDACION DE RESPUESTA
        # ================================================================
        print("\n[PASO 6] Validación de respuesta...")
        
        # Verificar que la respuesta contiene contenido del documento
        # La respuesta debe mencionar el importe del préstamo
        response_lower = response.lower()
        
        assert "50.000" in response or "50000" in response or "cincuenta mil" in response_lower, \
            "La respuesta debe mencionar el importe del préstamo (50.000 EUR)"
        
        # Verificar que hay contenido relevante del documento
        assert any(keyword in response_lower for keyword in ["préstamo", "prestamo", "importe", "eur", "euro"]), \
            "La respuesta debe contener términos relacionados con el préstamo"
        
        print(f"  ✅ La respuesta contiene contenido del documento ingerido")
        print(f"\n  Extracto de respuesta:")
        print(f"  {response[:200]}...")
        
        # ================================================================
        # VERIFICACIONES FINALES
        # ================================================================
        print("\n[VERIFICACIONES FINALES]")
        
        # Verificar integridad de datos
        db_chunks = get_chunks_for_case(db, TEST_CASE_ID)
        assert len(db_chunks) == len(chunks), "Los chunks en DB deben coincidir"
        
        print(f"  ✅ Integridad de datos verificada")
        print(f"  ✅ Sin errores en el flujo completo")
        
    print("\n" + "=" * 80)
    print("✅ TEST END-TO-END COMPLETADO EXITOSAMENTE")
    print("=" * 80)
    print("\nRESUMEN:")
    print(f"  • Case ID: {TEST_CASE_ID}")
    print(f"  • Documento ingerido: ✓")
    print(f"  • Chunks generados: {len(chunks)}")
    print(f"  • Embeddings creados: {embedding_count}")
    print(f"  • Consulta RAG: ✓")
    print(f"  • Respuesta válida: ✓")
    print("\n🎉 El sistema Phoenix Legal funciona end-to-end")
    print("=" * 80 + "\n")


def test_cleanup():
    """
    Test opcional: Limpieza de datos de prueba.
    
    NOTA: Este test se ejecuta al final para limpiar los datos de prueba.
    Puedes comentarlo si quieres inspeccionar los datos generados.
    """
    print("\n[CLEANUP] Limpiando datos de prueba...")
    
    _ensure_database_initialized()
    
    with get_session() as db:
        # Eliminar chunks
        chunks_deleted = db.query(DocumentChunk).filter(
            DocumentChunk.case_id == TEST_CASE_ID
        ).delete()
        
        # Eliminar documentos
        docs_deleted = db.query(Document).filter(
            Document.case_id == TEST_CASE_ID
        ).delete()
        
        db.commit()
        
        print(f"  ✅ Eliminados {docs_deleted} documentos")
        print(f"  ✅ Eliminados {chunks_deleted} chunks")
    
    # Nota: El vectorstore y los archivos físicos se pueden eliminar manualmente
    # si se desea una limpieza completa:
    # import shutil
    # storage_dir = DATA / "cases" / TEST_CASE_ID
    # if storage_dir.exists():
    #     shutil.rmtree(storage_dir)
    
    print(f"  ℹ️  Vectorstore y archivos físicos conservados en: clients_data/cases/{TEST_CASE_ID}")
    print(f"  ℹ️  Eliminarlos manualmente si es necesario")


if __name__ == "__main__":
    """
    Ejecución directa del test.
    
    Uso:
        python tests/test_end_to_end_case_rag.py
    
    O con pytest:
        pytest tests/test_end_to_end_case_rag.py -v -s
    """
    # Crear fixture manualmente
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.txt',
        delete=False,
        encoding='utf-8'
    ) as f:
        f.write(SAMPLE_LEGAL_DOC)
        temp_path = Path(f.name)
    
    try:
        test_end_to_end_flow(temp_path)
        test_cleanup()
    finally:
        if temp_path.exists():
            temp_path.unlink()

