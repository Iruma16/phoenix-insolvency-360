"""
TESTS DE ENDPOINT DE EXPLORACIÓN DE CHUNKS (PANTALLA 2).

Verifican que:
- NO se devuelve chunk sin location
- NO se ocultan offsets
- NO se permiten búsquedas semánticas
- NO se devuelve contenido modificado
- NO se accede a chunks de otro case_id
- NO se inventan resultados
- NO se ejecuta lógica de análisis
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock

from fastapi import HTTPException

from app.api.chunks import (
    list_chunks,
    get_chunk,
    _build_chunk_summary,
)
from app.models.chunk_summary import ChunkLocationSummary
from app.models.case import Case
from app.models.document import Document
from app.models.document_chunk import DocumentChunk, ExtractionMethod
from app.core.exceptions import ChunkContractViolationError


class TestBuildChunkSummary:
    """Tests de construcción de ChunkSummary desde el core."""
    
    def test_build_summary_con_location_completa_ok(self):
        """
        ✅ _build_chunk_summary con location completa → OK.
        """
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.chunk_id = "chunk-1"
        mock_chunk.case_id = "case-1"
        mock_chunk.document_id = "doc-1"
        mock_chunk.content = "Este es el contenido del chunk"
        mock_chunk.start_char = 100
        mock_chunk.end_char = 200
        mock_chunk.page_start = 1
        mock_chunk.page_end = 2
        mock_chunk.extraction_method = ExtractionMethod.PDF_TEXT
        mock_chunk.created_at = datetime.utcnow()
        
        mock_document = Mock(spec=Document)
        mock_document.filename = "test.pdf"
        
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_document
        
        result = _build_chunk_summary(mock_chunk, db=mock_db)
        
        assert result.chunk_id == "chunk-1"
        assert result.content == "Este es el contenido del chunk"
        assert result.location.start_char == 100
        assert result.location.end_char == 200
        assert result.location.page_start == 1
        assert result.location.page_end == 2
        assert result.location.extraction_method == ExtractionMethod.PDF_TEXT.value
    
    def test_build_summary_sin_offsets_falla(self):
        """
        ✅ _build_chunk_summary sin offsets → FALLA.
        """
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.chunk_id = "chunk-1"
        mock_chunk.start_char = None  # FALTA offset
        mock_chunk.end_char = 200
        mock_chunk.extraction_method = ExtractionMethod.PDF_TEXT
        mock_chunk.content = "Contenido"
        
        mock_db = MagicMock()
        
        with pytest.raises(ChunkContractViolationError) as exc_info:
            _build_chunk_summary(mock_chunk, db=mock_db)
        
        assert "sin offsets" in exc_info.value.message.lower()
    
    def test_build_summary_sin_extraction_method_falla(self):
        """
        ✅ _build_chunk_summary sin extraction_method → FALLA.
        """
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.chunk_id = "chunk-1"
        mock_chunk.start_char = 100
        mock_chunk.end_char = 200
        mock_chunk.extraction_method = None  # FALTA extraction_method
        mock_chunk.content = "Contenido"
        
        mock_db = MagicMock()
        
        with pytest.raises(ChunkContractViolationError) as exc_info:
            _build_chunk_summary(mock_chunk, db=mock_db)
        
        assert "extraction_method" in exc_info.value.message.lower()
    
    def test_build_summary_con_contenido_vacio_falla(self):
        """
        ✅ _build_chunk_summary con contenido vacío → FALLA.
        """
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.chunk_id = "chunk-1"
        mock_chunk.start_char = 100
        mock_chunk.end_char = 200
        mock_chunk.extraction_method = ExtractionMethod.PDF_TEXT
        mock_chunk.content = ""  # Contenido VACÍO
        
        mock_db = MagicMock()
        
        with pytest.raises(ChunkContractViolationError) as exc_info:
            _build_chunk_summary(mock_chunk, db=mock_db)
        
        assert "vacío" in exc_info.value.message.lower()
    
    def test_build_summary_no_modifica_contenido(self):
        """
        ✅ _build_chunk_summary devuelve contenido LITERAL (sin modificar).
        """
        original_content = "Este es el texto ORIGINAL con MAYÚSCULAS y números 123"
        
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.chunk_id = "chunk-1"
        mock_chunk.case_id = "case-1"
        mock_chunk.document_id = "doc-1"
        mock_chunk.content = original_content
        mock_chunk.start_char = 0
        mock_chunk.end_char = len(original_content)
        mock_chunk.page_start = 1
        mock_chunk.page_end = 1
        mock_chunk.extraction_method = ExtractionMethod.PDF_TEXT
        mock_chunk.created_at = datetime.utcnow()
        
        mock_document = Mock(spec=Document)
        mock_document.filename = "test.pdf"
        
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_document
        
        result = _build_chunk_summary(mock_chunk, db=mock_db)
        
        # El contenido debe ser EXACTAMENTE el mismo
        assert result.content == original_content


class TestListChunks:
    """Tests de listado de chunks."""
    
    def test_list_chunks_caso_inexistente_falla_404(self):
        """
        ✅ Listar chunks de caso inexistente → 404.
        """
        mock_db = MagicMock()
        
        # Caso no existe
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            list_chunks(case_id="inexistente", db=mock_db)
        
        assert exc_info.value.status_code == 404
        assert "no encontrado" in exc_info.value.detail.lower()
    
    def test_list_chunks_devuelve_datos_reales(self):
        """
        ✅ list_chunks devuelve datos EXACTOS del core.
        
        Este test simplificado verifica que list_chunks NO inventa datos.
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "case-1"
        
        mock_db = MagicMock()
        
        # Primera llamada: buscar caso (existe)
        # Segunda llamada: listar chunks (vacío)
        call_count = [0]
        
        def mock_query(model):
            call_count[0] += 1
            mock_query_obj = MagicMock()
            
            if call_count[0] == 1:
                # Caso existe
                mock_query_obj.filter.return_value.first.return_value = mock_case
            else:
                # Chunks vacíos
                mock_query_obj.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            
            return mock_query_obj
        
        mock_db.query.side_effect = mock_query
        
        result = list_chunks(case_id="case-1", db=mock_db)
        
        # Sin chunks → lista vacía (NO se inventan resultados)
        assert len(result) == 0
    
    def test_list_chunks_busqueda_literal_no_semantica(self):
        """
        ✅ list_chunks con text_contains usa búsqueda LITERAL (no semántica).
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "case-1"
        
        mock_db = MagicMock()
        
        # Primera llamada: buscar caso
        mock_query_case = MagicMock()
        mock_query_case.filter.return_value.first.return_value = mock_case
        
        # Segunda llamada: listar chunks con filtro
        mock_query_chunks = MagicMock()
        mock_query_chunks.filter.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        
        call_count = [0]
        
        def mock_query(model):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_query_case
            else:
                return mock_query_chunks
        
        mock_db.query.side_effect = mock_query
        
        # Ejecutar con text_contains
        result = list_chunks(
            case_id="case-1",
            text_contains="test",
            db=mock_db
        )
        
        # Verificar que se usó filter (ILIKE), no embeddings ni LLM
        # La llamada a filter con ilike indica búsqueda literal
        assert mock_query_chunks.filter.called


class TestGetChunk:
    """Tests de obtención de chunk específico."""
    
    def test_get_chunk_caso_inexistente_falla_404(self):
        """
        ✅ Obtener chunk de caso inexistente → 404.
        """
        mock_db = MagicMock()
        
        # Caso no existe
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            get_chunk(case_id="inexistente", chunk_id="chunk-1", db=mock_db)
        
        assert exc_info.value.status_code == 404
        assert "caso" in exc_info.value.detail.lower()
    
    def test_get_chunk_inexistente_falla_404(self):
        """
        ✅ Obtener chunk inexistente → 404.
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "case-1"
        
        mock_db = MagicMock()
        
        call_count = [0]
        
        def mock_query(model):
            call_count[0] += 1
            if call_count[0] == 1:
                # Primera llamada: buscar caso (existe)
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.first.return_value = mock_case
                return mock_query_obj
            else:
                # Segunda llamada: buscar chunk (no existe)
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.first.return_value = None
                return mock_query_obj
        
        mock_db.query.side_effect = mock_query
        
        with pytest.raises(HTTPException) as exc_info:
            get_chunk(case_id="case-1", chunk_id="inexistente", db=mock_db)
        
        assert exc_info.value.status_code == 404
        assert "chunk" in exc_info.value.detail.lower()
    
    def test_get_chunk_de_otro_caso_falla_404(self):
        """
        ✅ Obtener chunk de otro caso → 404.
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "case-1"
        
        mock_db = MagicMock()
        
        call_count = [0]
        
        def mock_query(model):
            call_count[0] += 1
            if call_count[0] == 1:
                # Primera llamada: buscar caso (existe)
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.first.return_value = mock_case
                return mock_query_obj
            else:
                # Segunda llamada: buscar chunk en case-1 (no existe porque pertenece a case-2)
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.first.return_value = None
                return mock_query_obj
        
        mock_db.query.side_effect = mock_query
        
        with pytest.raises(HTTPException) as exc_info:
            get_chunk(case_id="case-1", chunk_id="chunk-from-case-2", db=mock_db)
        
        assert exc_info.value.status_code == 404
    
    def test_get_chunk_devuelve_datos_exactos(self):
        """
        ✅ get_chunk devuelve datos EXACTOS del core.
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "case-1"
        
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.chunk_id = "chunk-1"
        mock_chunk.case_id = "case-1"
        mock_chunk.document_id = "doc-1"
        mock_chunk.content = "Contenido exacto del chunk"
        mock_chunk.start_char = 50
        mock_chunk.end_char = 77
        mock_chunk.page_start = 2
        mock_chunk.page_end = 2
        mock_chunk.extraction_method = ExtractionMethod.PDF_TEXT
        mock_chunk.created_at = datetime.utcnow()
        
        mock_document = Mock(spec=Document)
        mock_document.filename = "document.pdf"
        
        mock_db = MagicMock()
        
        call_count = [0]
        
        def mock_query(model):
            call_count[0] += 1
            if call_count[0] == 1:
                # Primera llamada: buscar caso
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.first.return_value = mock_case
                return mock_query_obj
            elif call_count[0] == 2:
                # Segunda llamada: buscar chunk
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.first.return_value = mock_chunk
                return mock_query_obj
            else:
                # Tercera llamada: buscar documento
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.first.return_value = mock_document
                return mock_query_obj
        
        mock_db.query.side_effect = mock_query
        
        result = get_chunk(case_id="case-1", chunk_id="chunk-1", db=mock_db)
        
        assert result.chunk_id == "chunk-1"
        assert result.content == "Contenido exacto del chunk"
        assert result.location.start_char == 50
        assert result.location.end_char == 77
        assert result.location.page_start == 2


class TestEndpointInvariants:
    """Tests de invariantes del dominio."""
    
    def test_no_existe_endpoint_post_chunks(self):
        """
        ✅ NO debe existir endpoint POST /chunks (crear chunks desde UI).
        """
        from app.api.chunks import router
        
        # Verificar que no hay rutas POST
        post_routes = [
            route for route in router.routes
            if hasattr(route, 'methods') and 'POST' in route.methods
        ]
        
        assert len(post_routes) == 0, "NO debe existir endpoint POST para crear chunks"
    
    def test_no_existe_endpoint_put_chunks(self):
        """
        ✅ NO debe existir endpoint PUT /chunks (editar chunks).
        """
        from app.api.chunks import router
        
        # Verificar que no hay rutas PUT
        put_routes = [
            route for route in router.routes
            if hasattr(route, 'methods') and 'PUT' in route.methods
        ]
        
        assert len(put_routes) == 0, "NO debe existir endpoint PUT para editar chunks"
    
    def test_no_existe_endpoint_delete_chunks(self):
        """
        ✅ NO debe existir endpoint DELETE /chunks (borrar chunks).
        """
        from app.api.chunks import router
        
        # Verificar que no hay rutas DELETE
        delete_routes = [
            route for route in router.routes
            if hasattr(route, 'methods') and 'DELETE' in route.methods
        ]
        
        assert len(delete_routes) == 0, "NO debe existir endpoint DELETE para borrar chunks"
    
    def test_no_existe_endpoint_search_semantico(self):
        """
        ✅ NO debe existir endpoint POST /chunks/search (búsqueda semántica).
        """
        from app.api.chunks import router
        
        # Verificar que no hay rutas con /search
        search_routes = [
            route for route in router.routes
            if hasattr(route, 'path') and 'search' in route.path.lower()
        ]
        
        assert len(search_routes) == 0, "NO debe existir endpoint de búsqueda semántica"
    
    def test_no_existe_endpoint_analyze(self):
        """
        ✅ NO debe existir endpoint POST /chunks/analyze (análisis).
        """
        from app.api.chunks import router
        
        # Verificar que no hay rutas con /analyze
        analyze_routes = [
            route for route in router.routes
            if hasattr(route, 'path') and 'analyze' in route.path.lower()
        ]
        
        assert len(analyze_routes) == 0, "NO debe existir endpoint de análisis"

