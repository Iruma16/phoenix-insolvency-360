"""
TESTS DE ENDPOINT DE GESTIÓN DE CASOS (PANTALLA 0).

Verifican que:
- NO se permite editar casos existentes
- NO se permite borrar casos
- NO se sobrescriben ejecuciones
- El estado refleja el core real
- NO se devuelven datos inventados
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from fastapi import HTTPException

from app.api.cases import (
    create_case,
    list_cases,
    get_case,
    _calculate_analysis_status,
    _build_case_summary,
)
from app.models.case_summary import (
    CreateCaseRequest,
    AnalysisStatus,
)
from app.models.case import Case
from app.models.document import Document
from app.models.fact import Fact
from app.models.risk import Risk


def create_mock_db_for_build_summary(doc_count=0, fact_count=0, risk_count=0, last_updated=None):
    """
    Helper para crear mock de DB específico para _build_case_summary.
    
    _build_case_summary hace 4 queries en orden:
    1. Document count
    2. Fact count
    3. Risk count
    4. func.max(Document.created_at)
    
    Args:
        doc_count: Número de documentos
        fact_count: Número de facts
        risk_count: Número de risks
        last_updated: Timestamp de última actualización
        
    Returns:
        Mock de sesión DB configurado
    """
    mock_db = MagicMock()
    
    # Contador de llamadas para devolver valores en orden
    call_count = [0]
    
    def mock_query(model_or_func):
        mock_query_obj = MagicMock()
        mock_filter = MagicMock()
        
        call_count[0] += 1
        current_call = call_count[0]
        
        # Llamada 1: Document count
        if current_call == 1:
            mock_filter.count.return_value = doc_count
        # Llamada 2: Fact count
        elif current_call == 2:
            mock_filter.count.return_value = fact_count
        # Llamada 3: Risk count
        elif current_call == 3:
            mock_filter.count.return_value = risk_count
        # Llamada 4: func.max(Document.created_at) scalar
        elif current_call == 4:
            mock_filter.scalar.return_value = last_updated
        else:
            # Llamadas adicionales (no deberían ocurrir en _build_case_summary)
            mock_filter.count.return_value = 0
            mock_filter.scalar.return_value = None
        
        mock_query_obj.filter.return_value = mock_filter
        return mock_query_obj
    
    mock_db.query.side_effect = mock_query
    
    return mock_db


class TestCreateCase:
    """Tests de creación de casos."""
    
    def test_create_case_genera_case_id_automatico(self):
        """
        ✅ El case_id se genera automáticamente por el core.
        """
        # Mock DB con 0 documentos, facts, risks (caso nuevo)
        mock_db = create_mock_db_for_build_summary(doc_count=0, fact_count=0, risk_count=0)
        
        # Simular caso creado
        mock_case = Mock(spec=Case)
        mock_case.case_id = "test-uuid-1234"
        mock_case.name = "Caso Test"
        mock_case.client_ref = None
        mock_case.created_at = datetime.utcnow()
        
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        
        def mock_refresh(obj):
            obj.case_id = mock_case.case_id
            obj.name = mock_case.name
            obj.created_at = mock_case.created_at
            obj.client_ref = mock_case.client_ref
        
        mock_db.refresh.side_effect = mock_refresh
        
        request = CreateCaseRequest(name="Caso Test")
        
        result = create_case(request, db=mock_db)
        
        # Verificar que se creó el caso
        assert mock_db.add.called
        assert mock_db.commit.called
        
        # Verificar que el case_id existe (generado por core)
        assert result.case_id is not None
        assert len(result.case_id) > 0
    
    def test_create_case_inicia_en_not_started(self):
        """
        ✅ Un caso nuevo inicia en estado NOT_STARTED.
        """
        # Sin documentos → NOT_STARTED
        mock_db = create_mock_db_for_build_summary(doc_count=0, fact_count=0, risk_count=0)
        
        mock_case = Mock(spec=Case)
        mock_case.case_id = "test-uuid"
        mock_case.name = "Caso Test"
        mock_case.client_ref = None
        mock_case.created_at = datetime.utcnow()
        
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        
        def mock_refresh(obj):
            obj.case_id = mock_case.case_id
            obj.name = mock_case.name
            obj.created_at = mock_case.created_at
            obj.client_ref = mock_case.client_ref
        
        mock_db.refresh.side_effect = mock_refresh
        
        request = CreateCaseRequest(name="Caso Test")
        result = create_case(request, db=mock_db)
        
        assert result.analysis_status == AnalysisStatus.NOT_STARTED


class TestListCases:
    """Tests de listado de casos."""
    
    def test_list_cases_devuelve_casos_reales(self):
        """
        ✅ list_cases devuelve solo casos existentes en el core.
        """
        # Simular 2 casos existentes
        mock_case1 = Mock(spec=Case)
        mock_case1.case_id = "case-1"
        mock_case1.name = "Caso 1"
        mock_case1.client_ref = None
        mock_case1.created_at = datetime(2025, 1, 1)
        
        mock_case2 = Mock(spec=Case)
        mock_case2.case_id = "case-2"
        mock_case2.name = "Caso 2"
        mock_case2.client_ref = None
        mock_case2.created_at = datetime(2025, 1, 2)
        
        # Mock DB
        mock_db = MagicMock()
        
        # Contador de llamadas
        call_count = [0]
        
        def mock_query_override(model):
            call_count[0] += 1
            current_call = call_count[0]
            
            if current_call == 1:
                # Primera llamada: listar casos
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.order_by.return_value.all.return_value = [
                    mock_case2,
                    mock_case1,
                ]
                return mock_query_obj
            else:
                # Llamadas siguientes: _build_case_summary para cada caso
                # Para cada caso se hacen 4 queries (doc, fact, risk, max)
                mock_query_obj = MagicMock()
                mock_filter = MagicMock()
                mock_filter.count.return_value = 0
                mock_filter.scalar.return_value = None
                mock_query_obj.filter.return_value = mock_filter
                return mock_query_obj
        
        mock_db.query.side_effect = mock_query_override
        
        result = list_cases(db=mock_db)
        
        assert len(result) == 2
        assert result[0].case_id == "case-2"  # Más reciente primero
        assert result[1].case_id == "case-1"


class TestGetCase:
    """Tests de consulta de caso individual."""
    
    def test_get_case_existente_ok(self):
        """
        ✅ get_case devuelve caso si existe.
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "test-case"
        mock_case.name = "Caso Test"
        mock_case.client_ref = "REF-123"
        mock_case.created_at = datetime.utcnow()
        
        # Mock DB
        mock_db = MagicMock()
        
        # Contador de llamadas
        call_count = [0]
        
        def mock_query_override(model):
            call_count[0] += 1
            current_call = call_count[0]
            
            if current_call == 1:
                # Primera llamada: buscar caso
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.first.return_value = mock_case
                return mock_query_obj
            elif current_call == 2:
                # Segunda llamada: count de documentos
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.count.return_value = 5
                return mock_query_obj
            elif current_call == 3:
                # Tercera llamada: count de facts
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.count.return_value = 0
                return mock_query_obj
            elif current_call == 4:
                # Cuarta llamada: count de risks
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.count.return_value = 0
                return mock_query_obj
            else:
                # Quinta llamada: func.max(Document.created_at)
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.scalar.return_value = None
                return mock_query_obj
        
        mock_db.query.side_effect = mock_query_override
        
        result = get_case(case_id="test-case", db=mock_db)
        
        assert result.case_id == "test-case"
        assert result.name == "Caso Test"
        assert result.documents_count == 5
    
    def test_get_case_inexistente_falla_404(self):
        """
        ✅ get_case lanza 404 si el caso no existe.
        """
        # Mock DB
        mock_db = MagicMock()
        
        # Query devuelve None (caso no existe)
        mock_query_obj = MagicMock()
        mock_query_obj.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query_obj
        
        with pytest.raises(HTTPException) as exc_info:
            get_case(case_id="inexistente", db=mock_db)
        
        assert exc_info.value.status_code == 404
        assert "no encontrado" in exc_info.value.detail.lower()


class TestAnalysisStatusCalculation:
    """Tests del cálculo de estado de análisis."""
    
    def test_sin_documentos_es_not_started(self):
        """
        ✅ Sin documentos → NOT_STARTED.
        """
        mock_db = MagicMock()
        
        status = _calculate_analysis_status(
            case_id="test",
            documents_count=0,
            facts_count=0,
            risks_count=0,
            db=mock_db,
        )
        
        assert status == AnalysisStatus.NOT_STARTED
    
    def test_con_documentos_sin_analisis_es_in_progress(self):
        """
        ✅ Con documentos pero sin facts/risks → IN_PROGRESS.
        """
        mock_db = MagicMock()
        
        status = _calculate_analysis_status(
            case_id="test",
            documents_count=5,
            facts_count=0,
            risks_count=0,
            db=mock_db,
        )
        
        assert status == AnalysisStatus.IN_PROGRESS
    
    def test_con_documentos_y_analisis_es_completed(self):
        """
        ✅ Con documentos y facts/risks → COMPLETED.
        """
        mock_db = MagicMock()
        
        status = _calculate_analysis_status(
            case_id="test",
            documents_count=5,
            facts_count=10,
            risks_count=3,
            db=mock_db,
        )
        
        assert status == AnalysisStatus.COMPLETED


class TestEndpointInvariants:
    """Tests de invariantes del dominio."""
    
    def test_no_existe_endpoint_put_cases(self):
        """
        ✅ NO debe existir endpoint PUT /cases/{case_id} (editar caso).
        """
        from app.api.cases import router
        
        # Verificar que no hay rutas PUT
        put_routes = [
            route for route in router.routes
            if hasattr(route, 'methods') and 'PUT' in route.methods
        ]
        
        assert len(put_routes) == 0, "NO debe existir endpoint PUT para editar casos"
    
    def test_no_existe_endpoint_delete_cases(self):
        """
        ✅ NO debe existir endpoint DELETE /cases/{case_id} (borrar caso).
        """
        from app.api.cases import router
        
        # Verificar que no hay rutas DELETE
        delete_routes = [
            route for route in router.routes
            if hasattr(route, 'methods') and 'DELETE' in route.methods
        ]
        
        assert len(delete_routes) == 0, "NO debe existir endpoint DELETE para borrar casos"
    
    def test_no_existe_endpoint_patch_cases(self):
        """
        ✅ NO debe existir endpoint PATCH /cases/{case_id} (modificar estado).
        """
        from app.api.cases import router
        
        # Verificar que no hay rutas PATCH
        patch_routes = [
            route for route in router.routes
            if hasattr(route, 'methods') and 'PATCH' in route.methods
        ]
        
        assert len(patch_routes) == 0, "NO debe existir endpoint PATCH para modificar estados"


class TestBuildCaseSummary:
    """Tests de construcción de CaseSummary desde el core."""
    
    def test_build_case_summary_refleja_estado_real(self):
        """
        ✅ _build_case_summary devuelve estado calculado desde el core.
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "test-case"
        mock_case.name = "Caso Test"
        mock_case.client_ref = None
        mock_case.created_at = datetime.utcnow()
        
        # Simular 3 documentos, 5 facts, 2 risks
        last_updated = datetime.utcnow()
        mock_db = create_mock_db_for_build_summary(
            doc_count=3, 
            fact_count=5, 
            risk_count=2, 
            last_updated=last_updated
        )
        
        result = _build_case_summary(mock_case, db=mock_db)
        
        # Debe reflejar el estado real del core
        assert result.documents_count == 3
        assert result.analysis_status == AnalysisStatus.COMPLETED  # Tiene facts + risks
    
    def test_build_case_summary_no_inventa_datos(self):
        """
        ✅ _build_case_summary NO inventa datos no existentes.
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "empty-case"
        mock_case.name = "Caso Vacío"
        mock_case.client_ref = None
        mock_case.created_at = datetime.utcnow()
        
        # Sin documentos, facts, ni risks
        mock_db = create_mock_db_for_build_summary(doc_count=0, fact_count=0, risk_count=0, last_updated=None)
        
        result = _build_case_summary(mock_case, db=mock_db)
        
        # Debe reflejar la ausencia de datos
        assert result.documents_count == 0
        assert result.last_execution_at is None
        assert result.analysis_status == AnalysisStatus.NOT_STARTED

