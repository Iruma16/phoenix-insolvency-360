"""
TESTS DE ENDPOINT DE CERTIFICACIÓN (MANIFEST) (PANTALLA 5).

Verifican que:
- NO se certifica sin trace completo
- NO se permite regenerar manifest
- NO se modifica manifest
- El manifest refleja exactamente el trace
- Los límites del sistema están declarados
"""
from unittest.mock import MagicMock, Mock

import pytest
from fastapi import HTTPException

from app.api.manifest import create_manifest
from app.models.case import Case


class TestCreateManifest:
    """Tests del endpoint de creación de manifest."""

    def test_create_manifest_caso_inexistente_falla_404(self):
        """
        ✅ Crear manifest de caso inexistente → 404.
        """
        mock_db = MagicMock()

        # Caso no existe
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            create_manifest(case_id="inexistente", db=mock_db)

        assert exc_info.value.status_code == 404
        assert "no encontrado" in exc_info.value.detail.lower()

    def test_create_manifest_sin_trace_falla_404(self):
        """
        ✅ Crear manifest sin trace previo → 404 con mensaje claro.
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "case-1"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_case

        # Por ahora, siempre devuelve 404 (sin persistencia implementada)
        with pytest.raises(HTTPException) as exc_info:
            create_manifest(case_id="case-1", db=mock_db)

        assert exc_info.value.status_code == 404
        assert "trace" in exc_info.value.detail.lower()


class TestEndpointInvariants:
    """Tests de invariantes del dominio."""

    def test_no_existe_endpoint_put_manifest(self):
        """
        ✅ NO debe existir endpoint PUT /manifest (editar manifest).
        """
        from app.api.manifest import router

        # Verificar que no hay rutas PUT
        put_routes = [
            route for route in router.routes if hasattr(route, "methods") and "PUT" in route.methods
        ]

        assert len(put_routes) == 0, "NO debe existir endpoint PUT para editar manifest"

    def test_no_existe_endpoint_delete_manifest(self):
        """
        ✅ NO debe existir endpoint DELETE /manifest (borrar manifest).
        """
        from app.api.manifest import router

        # Verificar que no hay rutas DELETE
        delete_routes = [
            route
            for route in router.routes
            if hasattr(route, "methods") and "DELETE" in route.methods
        ]

        assert len(delete_routes) == 0, "NO debe existir endpoint DELETE para borrar manifest"

    def test_no_existe_endpoint_regenerate_manifest(self):
        """
        ✅ NO debe existir endpoint POST /manifest/regenerate (regenerar manifest).
        """
        from app.api.manifest import router

        # Verificar que no hay rutas con /regenerate
        regenerate_routes = [
            route
            for route in router.routes
            if hasattr(route, "path") and "regenerate" in route.path.lower()
        ]

        assert len(regenerate_routes) == 0, "NO debe existir endpoint de regeneración"


class TestManifestImmutability:
    """Tests de inmutabilidad del manifest."""

    def test_manifest_model_es_inmutable(self):
        """
        ✅ El modelo HardManifest es inmutable (frozen=True).
        """
        from app.trace.manifest import HardManifest

        # Verificar que el modelo tiene frozen=True
        assert (
            HardManifest.model_config.get("frozen") is True
        ), "HardManifest debe ser inmutable (frozen=True)"


class TestManifestContract:
    """Tests del contrato del manifest."""

    def test_manifest_incluye_execution_limits(self):
        """
        ✅ El manifest debe declarar execution_limits (qué NO hace el sistema).
        """
        import hashlib
        from datetime import datetime

        from pydantic import ValidationError

        from app.trace.manifest import HardManifest

        # El manifest debe tener execution_limits obligatorio
        with pytest.raises(ValidationError) as exc_info:
            HardManifest(
                trace_id="trace-1",
                case_id="case-1",
                schema_versions={"chunk": "1.0", "trace": "1.0"},
                integrity_hash=hashlib.sha256(b"test").hexdigest(),
                # execution_limits FALTA (obligatorio)
                signed_at=datetime.utcnow(),
                system_version="1.0.0",
            )

        assert "execution_limits" in str(exc_info.value).lower()

    def test_manifest_integrity_hash_formato_valido(self):
        """
        ✅ El integrity_hash del manifest debe ser un SHA256 válido.
        """
        from datetime import datetime

        from pydantic import ValidationError

        from app.trace.manifest import HardManifest

        # Hash inválido (no SHA256)
        with pytest.raises(ValidationError) as exc_info:
            HardManifest(
                trace_id="trace-1",
                case_id="case-1",
                schema_versions={"chunk": "1.0", "trace": "1.0"},
                integrity_hash="not_a_valid_sha256",  # INVÁLIDO
                execution_limits=["No realiza análisis en tiempo real"],
                signed_at=datetime.utcnow(),
                system_version="1.0.0",
            )

        # Debe fallar por formato de hash inválido
        assert (
            "integrity_hash" in str(exc_info.value).lower()
            or "sha256" in str(exc_info.value).lower()
        )

    def test_manifest_con_datos_validos_ok(self):
        """
        ✅ Manifest con datos válidos se crea correctamente.
        """
        import hashlib
        from datetime import datetime

        from app.trace.manifest import HardManifest

        manifest = HardManifest(
            trace_id="trace-1",
            case_id="case-1",
            schema_versions={"chunk": "1.0.0", "trace": "1.0.0"},
            integrity_hash=hashlib.sha256(b"test_trace_content").hexdigest(),
            execution_limits=[
                "No realiza análisis en tiempo real",
                "No sustituye criterio legal experto",
                "No garantiza exhaustividad sin revisión humana",
            ],
            signed_at=datetime.utcnow(),
            system_version="1.0.0",
        )

        assert manifest.trace_id == "trace-1"
        assert manifest.case_id == "case-1"
        assert len(manifest.execution_limits) >= 1
        assert len(manifest.integrity_hash) == 64  # SHA256 tiene 64 caracteres hex
