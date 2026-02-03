"""
TESTS DE ENDPOINT DE ANÁLISIS TÉCNICO / ALERTAS (PANTALLA 3).

Verifican que:
- NO se devuelve alerta sin evidencia
- NO se devuelve evidencia sin location
- NO se generan alertas "interpretativas"
- NO se usan LLMs / embeddings
- NO se modifican datos del core
- NO se inventan alertas cuando no hay base
"""
from datetime import datetime
from unittest.mock import MagicMock, Mock

import pytest
from fastapi import HTTPException

from app.api.analysis_alerts import (
    _build_alert_evidence,
    _detect_duplicated_data_alerts,
    _detect_inconsistent_data_alerts,
    _detect_missing_data_alerts,
    _detect_suspicious_patterns,
    get_analysis_alerts,
)
from app.models.analysis_alert import (
    AlertEvidence,
    AlertType,
    AnalysisAlert,
)
from app.models.case import Case
from app.models.document import Document
from app.models.document_chunk import DocumentChunk, ExtractionMethod


class TestBuildAlertEvidence:
    """Tests de construcción de AlertEvidence desde el core."""

    def test_build_evidence_con_location_completa_ok(self):
        """
        ✅ _build_alert_evidence con location completa → OK.
        """
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.chunk_id = "chunk-1"
        mock_chunk.document_id = "doc-1"
        mock_chunk.content = "Este es el contenido del chunk"
        mock_chunk.start_char = 100
        mock_chunk.end_char = 200
        mock_chunk.page_start = 1
        mock_chunk.page_end = 2
        mock_chunk.extraction_method = ExtractionMethod.PDF_TEXT.value

        mock_document = Mock(spec=Document)
        mock_document.filename = "test.pdf"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_document

        result = _build_alert_evidence(mock_chunk, db=mock_db)

        assert result.chunk_id == "chunk-1"
        assert result.content == "Este es el contenido del chunk"
        assert result.location.start_char == 100
        assert result.location.end_char == 200
        assert result.location.page_start == 1
        assert result.location.page_end == 2

    def test_build_evidence_sin_offsets_falla(self):
        """
        ✅ _build_alert_evidence sin offsets → FALLA.
        """
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.chunk_id = "chunk-1"
        mock_chunk.start_char = None  # FALTA offset
        mock_chunk.end_char = 200

        mock_db = MagicMock()

        with pytest.raises(ValueError) as exc_info:
            _build_alert_evidence(mock_chunk, db=mock_db)

        assert "sin offsets" in str(exc_info.value).lower()

    def test_build_evidence_sin_extraction_method_falla(self):
        """
        ✅ _build_alert_evidence sin extraction_method → FALLA.
        """
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.chunk_id = "chunk-1"
        mock_chunk.start_char = 100
        mock_chunk.end_char = 200
        mock_chunk.extraction_method = None  # FALTA extraction_method

        mock_db = MagicMock()

        with pytest.raises(ValueError) as exc_info:
            _build_alert_evidence(mock_chunk, db=mock_db)

        assert "extraction_method" in str(exc_info.value).lower()

    def test_build_evidence_con_contenido_vacio_falla(self):
        """
        ✅ _build_alert_evidence con contenido vacío → FALLA.
        """
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.chunk_id = "chunk-1"
        mock_chunk.start_char = 100
        mock_chunk.end_char = 200
        mock_chunk.extraction_method = ExtractionMethod.PDF_TEXT.value
        mock_chunk.content = ""  # Contenido VACÍO

        mock_db = MagicMock()

        with pytest.raises(ValueError) as exc_info:
            _build_alert_evidence(mock_chunk, db=mock_db)

        assert "vacío" in str(exc_info.value).lower()


class TestDetectionRules:
    """Tests de reglas de detección deterministas."""

    def test_detect_missing_data_sin_problemas_devuelve_vacio(self):
        """
        ✅ Sin problemas detectables → lista vacía (NO se inventa).
        """
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.extraction_method = ExtractionMethod.PDF_TEXT.value
        mock_chunk.page_start = 1  # Tiene página

        mock_db = MagicMock()

        result = _detect_missing_data_alerts("case-1", [mock_chunk], db=mock_db)

        assert result == []

    def test_detect_duplicated_data_sin_duplicados_devuelve_vacio(self):
        """
        ✅ Sin duplicados → lista vacía (NO se inventa).
        """
        mock_chunk1 = Mock(spec=DocumentChunk)
        mock_chunk1.content = "Contenido único 1" + "x" * 50

        mock_chunk2 = Mock(spec=DocumentChunk)
        mock_chunk2.content = "Contenido único 2" + "y" * 50

        mock_db = MagicMock()

        result = _detect_duplicated_data_alerts("case-1", [mock_chunk1, mock_chunk2], db=mock_db)

        assert result == []

    def test_detect_inconsistent_data_sin_inconsistencias_devuelve_vacio(self):
        """
        ✅ Sin inconsistencias → lista vacía (NO se inventa).
        """
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.start_char = 100
        mock_chunk.end_char = 200  # Válido: start < end
        mock_chunk.page_start = 1
        mock_chunk.page_end = 2  # Válido: start <= end

        mock_db = MagicMock()

        result = _detect_inconsistent_data_alerts("case-1", [mock_chunk], db=mock_db)

        assert result == []

    def test_detect_suspicious_patterns_sin_patrones_devuelve_vacio(self):
        """
        ✅ Sin patrones sospechosos → lista vacía (NO se inventa).
        """
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.content = "Contenido normal de tamaño razonable para un chunk"

        mock_db = MagicMock()

        result = _detect_suspicious_patterns("case-1", [mock_chunk], db=mock_db)

        assert result == []

    def test_detect_inconsistent_data_detecta_offsets_invalidos(self):
        """
        ✅ Detecta offsets inválidos (start >= end).
        """
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.chunk_id = "chunk-invalid"
        mock_chunk.document_id = "doc-1"
        mock_chunk.start_char = 200  # INVÁLIDO
        mock_chunk.end_char = 100  # start >= end
        mock_chunk.page_start = 1
        mock_chunk.page_end = 1
        mock_chunk.extraction_method = ExtractionMethod.PDF_TEXT.value
        mock_chunk.content = "Contenido del chunk con offsets inválidos"

        mock_document = Mock(spec=Document)
        mock_document.filename = "test.pdf"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_document

        result = _detect_inconsistent_data_alerts("case-1", [mock_chunk], db=mock_db)

        assert len(result) == 1
        assert result[0].alert_type == AlertType.INCONSISTENT_DATA
        assert "offsets inválidos" in result[0].description.lower()
        assert len(result[0].evidence) >= 1


class TestGetAnalysisAlerts:
    """Tests del endpoint principal."""

    def test_get_alerts_caso_inexistente_falla_404(self):
        """
        ✅ Obtener alertas de caso inexistente → 404.
        """
        mock_db = MagicMock()

        # Caso no existe
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            get_analysis_alerts(case_id="inexistente", db=mock_db)

        assert exc_info.value.status_code == 404
        assert "no encontrado" in exc_info.value.detail.lower()

    def test_get_alerts_sin_chunks_devuelve_vacio(self):
        """
        ✅ Caso sin chunks → lista vacía (NO se inventa).
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
                # Segunda llamada: buscar chunks (vacío)
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.all.return_value = []
                return mock_query_obj

        mock_db.query.side_effect = mock_query

        result = get_analysis_alerts(case_id="case-1", db=mock_db)

        # Sin chunks → sin alertas (NO se inventa)
        assert result == []

    def test_get_alerts_devuelve_alertas_deterministas(self):
        """
        ✅ Las alertas son deterministas: sin problemas → sin alertas.

        Test simplificado: si no hay problemas, no se inventan alertas.
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "case-1"

        # Chunk válido (sin problemas)
        mock_chunk = Mock(spec=DocumentChunk)
        mock_chunk.chunk_id = "chunk-valid"
        mock_chunk.document_id = "doc-1"
        mock_chunk.case_id = "case-1"
        mock_chunk.start_char = 100  # VÁLIDO
        mock_chunk.end_char = 200  # start < end
        mock_chunk.page_start = 1
        mock_chunk.page_end = 2
        mock_chunk.extraction_method = ExtractionMethod.PDF_TEXT.value
        mock_chunk.content = "Contenido válido del chunk sin problemas detectables"

        mock_db = MagicMock()

        call_count = [0]

        def mock_query(model):
            call_count[0] += 1
            if call_count[0] == 1:
                # Primera llamada: buscar caso
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.first.return_value = mock_case
                return mock_query_obj
            else:
                # Segunda llamada: buscar chunks
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.all.return_value = [mock_chunk]
                return mock_query_obj

        mock_db.query.side_effect = mock_query

        # Ejecutar
        result = get_analysis_alerts(case_id="case-1", db=mock_db)

        # Sin problemas → sin alertas (determinista, no se inventa)
        assert result == []


class TestAlertModel:
    """Tests del modelo de alertas."""

    def test_analysis_alert_sin_evidencia_falla(self):
        """
        ✅ Alerta sin evidencia → FALLA (validación de Pydantic).
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            AnalysisAlert(
                alert_id="alert-1",
                case_id="case-1",
                alert_type=AlertType.MISSING_DATA,
                description="Descripción técnica de la alerta",
                evidence=[],  # VACÍO: no permitido
                created_at=datetime.utcnow(),
            )

        assert "evidence" in str(exc_info.value).lower()

    def test_analysis_alert_descripcion_corta_falla(self):
        """
        ✅ Alerta con descripción <10 chars → FALLA.
        """
        from pydantic import ValidationError

        mock_evidence = Mock(spec=AlertEvidence)

        with pytest.raises(ValidationError) as exc_info:
            AnalysisAlert(
                alert_id="alert-1",
                case_id="case-1",
                alert_type=AlertType.MISSING_DATA,
                description="Corto",  # <10 chars
                evidence=[mock_evidence],
                created_at=datetime.utcnow(),
            )

        assert "description" in str(exc_info.value).lower()

    def test_analysis_alert_con_terminos_legales_falla(self):
        """
        ✅ Alerta con términos legales prohibidos → FALLA.
        """
        from pydantic import ValidationError

        mock_evidence = AlertEvidence(
            chunk_id="chunk-1",
            document_id="doc-1",
            filename="test.pdf",
            location={
                "start_char": 0,
                "end_char": 100,
                "page_start": 1,
                "page_end": 1,
                "extraction_method": "pdf_text",
            },
            content="Contenido de evidencia",
        )

        # Términos legales prohibidos
        prohibited_terms = [
            "El acusado es culpable de fraude",
            "Se detectó un delito evidente",
            "El inocente no tiene responsabilidad penal",
        ]

        for description in prohibited_terms:
            with pytest.raises(ValidationError) as exc_info:
                AnalysisAlert(
                    alert_id="alert-1",
                    case_id="case-1",
                    alert_type=AlertType.MISSING_DATA,
                    description=description,
                    evidence=[mock_evidence],
                    created_at=datetime.utcnow(),
                )

            assert "prohibido" in str(exc_info.value).lower()


class TestEndpointInvariants:
    """Tests de invariantes del dominio."""

    def test_no_existe_endpoint_post_alerts(self):
        """
        ✅ NO debe existir endpoint POST /alerts (crear alertas manualmente).
        """
        from app.api.analysis_alerts import router

        # Verificar que no hay rutas POST
        post_routes = [
            route
            for route in router.routes
            if hasattr(route, "methods") and "POST" in route.methods
        ]

        assert len(post_routes) == 0, "NO debe existir endpoint POST para crear alertas"

    def test_no_existe_endpoint_put_alerts(self):
        """
        ✅ NO debe existir endpoint PUT /alerts (editar alertas).
        """
        from app.api.analysis_alerts import router

        # Verificar que no hay rutas PUT
        put_routes = [
            route for route in router.routes if hasattr(route, "methods") and "PUT" in route.methods
        ]

        assert len(put_routes) == 0, "NO debe existir endpoint PUT para editar alertas"

    def test_no_existe_endpoint_delete_alerts(self):
        """
        ✅ NO debe existir endpoint DELETE /alerts (borrar alertas).
        """
        from app.api.analysis_alerts import router

        # Verificar que no hay rutas DELETE
        delete_routes = [
            route
            for route in router.routes
            if hasattr(route, "methods") and "DELETE" in route.methods
        ]

        assert len(delete_routes) == 0, "NO debe existir endpoint DELETE para borrar alertas"

    def test_no_existe_endpoint_interpret(self):
        """
        ✅ NO debe existir endpoint POST /interpret (interpretación legal).
        """
        from app.api.analysis_alerts import router

        # Verificar que no hay rutas con /interpret
        interpret_routes = [
            route
            for route in router.routes
            if hasattr(route, "path") and "interpret" in route.path.lower()
        ]

        assert len(interpret_routes) == 0, "NO debe existir endpoint de interpretación legal"

    def test_no_existe_endpoint_llm(self):
        """
        ✅ NO debe existir endpoint POST /llm (uso de LLM).
        """
        from app.api.analysis_alerts import router

        # Verificar que no hay rutas con /llm
        llm_routes = [
            route
            for route in router.routes
            if hasattr(route, "path") and "llm" in route.path.lower()
        ]

        assert len(llm_routes) == 0, "NO debe existir endpoint de LLM"
