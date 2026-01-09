"""
TESTS DE ENDPOINT DE VISUALIZACIÓN DE TRACE (PANTALLA 5).

Verifican que:
- NO se accede a trace inexistente
- NO se modifica trace
- NO se borra trace
- El trace es inmutable y read-only
"""
import pytest
from unittest.mock import Mock, MagicMock

from fastapi import HTTPException

from app.api.trace import get_execution_trace
from app.models.case import Case


class TestGetExecutionTrace:
    """Tests del endpoint de obtención de trace."""
    
    def test_get_trace_caso_inexistente_falla_404(self):
        """
        ✅ Obtener trace de caso inexistente → 404.
        """
        mock_db = MagicMock()
        
        # Caso no existe
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            get_execution_trace(case_id="inexistente", db=mock_db)
        
        assert exc_info.value.status_code == 404
        assert "no encontrado" in exc_info.value.detail.lower()
    
    def test_get_trace_sin_trace_falla_404(self):
        """
        ✅ Obtener trace sin ejecución previa → 404 con mensaje claro.
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "case-1"
        
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_case
        
        # Por ahora, siempre devuelve 404 (sin persistencia implementada)
        with pytest.raises(HTTPException) as exc_info:
            get_execution_trace(case_id="case-1", db=mock_db)
        
        assert exc_info.value.status_code == 404
        assert "trace" in exc_info.value.detail.lower()


class TestEndpointInvariants:
    """Tests de invariantes del dominio."""
    
    def test_no_existe_endpoint_post_trace(self):
        """
        ✅ NO debe existir endpoint POST /trace (crear trace manualmente).
        """
        from app.api.trace import router
        
        # Verificar que no hay rutas POST
        post_routes = [
            route for route in router.routes
            if hasattr(route, 'methods') and 'POST' in route.methods
        ]
        
        assert len(post_routes) == 0, "NO debe existir endpoint POST para crear trace"
    
    def test_no_existe_endpoint_put_trace(self):
        """
        ✅ NO debe existir endpoint PUT /trace (editar trace).
        """
        from app.api.trace import router
        
        # Verificar que no hay rutas PUT
        put_routes = [
            route for route in router.routes
            if hasattr(route, 'methods') and 'PUT' in route.methods
        ]
        
        assert len(put_routes) == 0, "NO debe existir endpoint PUT para editar trace"
    
    def test_no_existe_endpoint_delete_trace(self):
        """
        ✅ NO debe existir endpoint DELETE /trace (borrar trace).
        """
        from app.api.trace import router
        
        # Verificar que no hay rutas DELETE
        delete_routes = [
            route for route in router.routes
            if hasattr(route, 'methods') and 'DELETE' in route.methods
        ]
        
        assert len(delete_routes) == 0, "NO debe existir endpoint DELETE para borrar trace"
    
    def test_no_existe_endpoint_regenerate_trace(self):
        """
        ✅ NO debe existir endpoint POST /trace/regenerate (regenerar trace).
        """
        from app.api.trace import router
        
        # Verificar que no hay rutas con /regenerate
        regenerate_routes = [
            route for route in router.routes
            if hasattr(route, 'path') and 'regenerate' in route.path.lower()
        ]
        
        assert len(regenerate_routes) == 0, "NO debe existir endpoint de regeneración"


class TestTraceImmutability:
    """Tests de inmutabilidad del trace."""
    
    def test_trace_model_es_inmutable(self):
        """
        ✅ El modelo ExecutionTrace es inmutable (frozen=True).
        """
        from app.trace.models import ExecutionTrace
        
        # Verificar que el modelo tiene frozen=True
        assert ExecutionTrace.model_config.get("frozen") is True, (
            "ExecutionTrace debe ser inmutable (frozen=True)"
        )
    
    def test_trace_decision_es_inmutable(self):
        """
        ✅ El modelo TraceDecision es inmutable (frozen=True).
        """
        from app.trace.models import TraceDecision
        
        # Verificar que el modelo tiene frozen=True
        assert TraceDecision.model_config.get("frozen") is True, (
            "TraceDecision debe ser inmutable (frozen=True)"
        )

