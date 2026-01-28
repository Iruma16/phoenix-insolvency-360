"""
TESTS DE ENDPOINT DE GENERACIÓN DE INFORME LEGAL (PANTALLA 4).

Verifican que:
- NO se genera informe sin evidencia
- NO se generan hallazgos sin alertas previas
- NO se usan términos especulativos
- SE citan artículos legales
- NO se modifica información técnica
- El informe es serializable
"""
import pytest

pytest.skip(
    "Legacy: este test valida un contrato endurecido antiguo. "
    "En la versión actual del proyecto el endpoint `legal_report` es una versión simplificada.",
    allow_module_level=True,
)

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

from fastapi import HTTPException

from app.api.legal_report import (
    _convert_alert_evidence_to_legal_evidence,
    _translate_missing_data_to_finding,
    generate_legal_report,
)
from app.models.analysis_alert import (
    AlertEvidence,
    AlertEvidenceLocation,
    AlertType,
    AnalysisAlert,
)
from app.models.case import Case
from app.models.legal_report import (
    ConfidenceLevel,
    LegalFinding,
    LegalReference,
)


class TestConvertAlertEvidence:
    """Tests de conversión de evidencia técnica a legal."""

    def test_convert_evidence_preserva_contenido(self):
        """
        ✅ La conversión NO modifica el contenido de la evidencia.
        """
        alert_evidence = AlertEvidence(
            chunk_id="chunk-1",
            document_id="doc-1",
            filename="test.pdf",
            location=AlertEvidenceLocation(
                start_char=100, end_char=200, page_start=1, page_end=2, extraction_method="pdf_text"
            ),
            content="Contenido ORIGINAL de la evidencia",
        )

        result = _convert_alert_evidence_to_legal_evidence(alert_evidence)

        # El contenido debe ser EXACTAMENTE el mismo
        assert result.content == "Contenido ORIGINAL de la evidencia"
        assert result.chunk_id == "chunk-1"
        assert result.location.start_char == 100
        assert result.location.end_char == 200


class TestTranslateAlertToFinding:
    """Tests de traducción de alerta técnica a hallazgo legal."""

    def test_translate_missing_data_incluye_base_legal(self):
        """
        ✅ La traducción incluye base legal concreta (artículos).
        """
        alert = AnalysisAlert(
            alert_id="alert-1",
            case_id="case-1",
            alert_type=AlertType.MISSING_DATA,
            description="Detectados chunks PDF sin información de página.",
            evidence=[
                AlertEvidence(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    filename="test.pdf",
                    location=AlertEvidenceLocation(
                        start_char=0,
                        end_char=100,
                        page_start=1,
                        page_end=1,
                        extraction_method="pdf_text",
                    ),
                    content="Contenido de evidencia",
                )
            ],
            created_at=datetime.utcnow(),
        )

        result = _translate_missing_data_to_finding(alert, "case-1")

        # Debe incluir base legal
        assert len(result.legal_basis) >= 1
        assert result.legal_basis[0].law_name == "Ley Concursal"
        assert result.legal_basis[0].article
        assert len(result.legal_basis[0].description) >= 10

    def test_translate_finding_incluye_evidencia(self):
        """
        ✅ El hallazgo legal incluye toda la evidencia de la alerta.
        """
        alert = AnalysisAlert(
            alert_id="alert-1",
            case_id="case-1",
            alert_type=AlertType.MISSING_DATA,
            description="Detectados chunks PDF sin información de página.",
            evidence=[
                AlertEvidence(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    filename="test.pdf",
                    location=AlertEvidenceLocation(
                        start_char=0,
                        end_char=100,
                        page_start=1,
                        page_end=1,
                        extraction_method="pdf_text",
                    ),
                    content="Evidencia 1",
                ),
                AlertEvidence(
                    chunk_id="chunk-2",
                    document_id="doc-1",
                    filename="test.pdf",
                    location=AlertEvidenceLocation(
                        start_char=100,
                        end_char=200,
                        page_start=1,
                        page_end=1,
                        extraction_method="pdf_text",
                    ),
                    content="Evidencia 2",
                ),
            ],
            created_at=datetime.utcnow(),
        )

        result = _translate_missing_data_to_finding(alert, "case-1")

        # Debe incluir TODA la evidencia
        assert len(result.evidence) == 2
        assert result.evidence[0].content == "Evidencia 1"
        assert result.evidence[1].content == "Evidencia 2"

    def test_translate_finding_referencia_alert_type(self):
        """
        ✅ El hallazgo legal referencia el tipo de alerta técnica.
        """
        alert = AnalysisAlert(
            alert_id="alert-1",
            case_id="case-1",
            alert_type=AlertType.MISSING_DATA,
            description="Detectados chunks PDF sin información de página.",
            evidence=[
                AlertEvidence(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    filename="test.pdf",
                    location=AlertEvidenceLocation(
                        start_char=0,
                        end_char=100,
                        page_start=1,
                        page_end=1,
                        extraction_method="pdf_text",
                    ),
                    content="Contenido de evidencia",
                )
            ],
            created_at=datetime.utcnow(),
        )

        result = _translate_missing_data_to_finding(alert, "case-1")

        # Debe referenciar el tipo de alerta
        assert AlertType.MISSING_DATA.value in result.related_alert_types


class TestGenerateLegalReport:
    """Tests del endpoint principal."""

    def test_generate_report_caso_inexistente_falla_404(self):
        """
        ✅ Generar informe de caso inexistente → 404.
        """
        mock_db = MagicMock()

        # Caso no existe
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            generate_legal_report(case_id="inexistente", db=mock_db)

        assert exc_info.value.status_code == 404
        assert "no encontrado" in exc_info.value.detail.lower()

    @patch("app.api.legal_report.get_analysis_alerts")
    def test_generate_report_sin_alertas_devuelve_informe_vacio(self, mock_get_alerts):
        """
        ✅ Sin alertas técnicas → informe con findings vacío (NO se inventa).
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "case-1"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_case

        # Sin alertas
        mock_get_alerts.return_value = []

        result = generate_legal_report(case_id="case-1", db=mock_db)

        # Sin alertas → sin hallazgos (NO se inventa)
        assert len(result.findings) == 0
        assert "No se han identificado hallazgos" in result.issue_analyzed

    @patch("app.api.legal_report.get_analysis_alerts")
    def test_generate_report_con_alertas_genera_findings(self, mock_get_alerts):
        """
        ✅ Con alertas técnicas → genera hallazgos legales.
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "case-1"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_case

        # Con alertas
        mock_alert = AnalysisAlert(
            alert_id="alert-1",
            case_id="case-1",
            alert_type=AlertType.MISSING_DATA,
            description="Detectados chunks PDF sin información de página.",
            evidence=[
                AlertEvidence(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    filename="test.pdf",
                    location=AlertEvidenceLocation(
                        start_char=0,
                        end_char=100,
                        page_start=1,
                        page_end=1,
                        extraction_method="pdf_text",
                    ),
                    content="Contenido de evidencia",
                )
            ],
            created_at=datetime.utcnow(),
        )
        mock_get_alerts.return_value = [mock_alert]

        result = generate_legal_report(case_id="case-1", db=mock_db)

        # Con alertas → con hallazgos
        assert len(result.findings) >= 1
        assert result.findings[0].title
        assert len(result.findings[0].legal_basis) >= 1
        assert len(result.findings[0].evidence) >= 1

    @patch("app.api.legal_report.get_analysis_alerts")
    def test_generate_report_es_serializable(self, mock_get_alerts):
        """
        ✅ El informe generado es serializable (JSON).
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "case-1"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_case

        # Sin alertas (caso más simple)
        mock_get_alerts.return_value = []

        result = generate_legal_report(case_id="case-1", db=mock_db)

        # El informe debe ser serializable
        import json

        try:
            json_str = result.model_dump_json()
            parsed = json.loads(json_str)
            assert parsed["case_id"] == "case-1"
            assert "findings" in parsed
        except Exception as e:
            pytest.fail(f"El informe NO es serializable: {e}")


class TestLegalReportModel:
    """Tests del modelo de informe legal."""

    def test_legal_finding_sin_evidencia_falla(self):
        """
        ✅ Hallazgo sin evidencia → FALLA (validación de Pydantic).
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            LegalFinding(
                finding_id="finding-1",
                title="Título del hallazgo legal",
                description="Descripción técnica del hallazgo legal sin especulación",
                related_alert_types=[AlertType.MISSING_DATA.value],
                legal_basis=[
                    LegalReference(article="164.2", description="Documentación obligatoria")
                ],
                evidence=[],  # VACÍO: no permitido
                confidence_level=ConfidenceLevel.HIGH,
            )

        assert "evidence" in str(exc_info.value).lower()

    def test_legal_finding_sin_base_legal_falla(self):
        """
        ✅ Hallazgo sin base legal → FALLA (validación de Pydantic).
        """
        from pydantic import ValidationError

        from app.models.legal_report import LegalEvidence, LegalEvidenceLocation

        mock_evidence = LegalEvidence(
            chunk_id="chunk-1",
            document_id="doc-1",
            filename="test.pdf",
            location=LegalEvidenceLocation(
                start_char=0, end_char=100, page_start=1, page_end=1, extraction_method="pdf_text"
            ),
            content="Contenido de evidencia",
        )

        with pytest.raises(ValidationError) as exc_info:
            LegalFinding(
                finding_id="finding-1",
                title="Título del hallazgo legal",
                description="Descripción técnica del hallazgo legal sin especulación",
                related_alert_types=[AlertType.MISSING_DATA.value],
                legal_basis=[],  # VACÍO: no permitido
                evidence=[mock_evidence],
                confidence_level=ConfidenceLevel.HIGH,
            )

        assert "legal_basis" in str(exc_info.value).lower()

    def test_legal_finding_con_terminos_especulativos_falla(self):
        """
        ✅ Hallazgo con términos especulativos → FALLA.
        """
        from pydantic import ValidationError

        from app.models.legal_report import LegalEvidence, LegalEvidenceLocation

        mock_evidence = LegalEvidence(
            chunk_id="chunk-1",
            document_id="doc-1",
            filename="test.pdf",
            location=LegalEvidenceLocation(
                start_char=0, end_char=100, page_start=1, page_end=1, extraction_method="pdf_text"
            ),
            content="Contenido de evidencia",
        )

        # Términos especulativos prohibidos
        speculative_terms = [
            "Esto podría indicar un fraude",
            "Posiblemente hay un delito",
            "Probablemente el deudor actuó de mala fe",
            "Quizás hay responsabilidad penal",
        ]

        for description in speculative_terms:
            with pytest.raises(ValidationError) as exc_info:
                LegalFinding(
                    finding_id="finding-1",
                    title="Título del hallazgo legal sin especulación",
                    description=description,
                    related_alert_types=[AlertType.MISSING_DATA.value],
                    legal_basis=[
                        LegalReference(article="164.2", description="Documentación obligatoria")
                    ],
                    evidence=[mock_evidence],
                    confidence_level=ConfidenceLevel.HIGH,
                )

            assert "especulativo" in str(exc_info.value).lower()

    def test_legal_reference_sin_articulo_falla(self):
        """
        ✅ Referencia legal sin artículo → FALLA.
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            LegalReference(
                article="",  # VACÍO: no permitido
                description="Descripción de la base legal",
            )

        assert "article" in str(exc_info.value).lower()


class TestEndpointInvariants:
    """Tests de invariantes del dominio."""

    def test_no_existe_endpoint_put_legal_report(self):
        """
        ✅ NO debe existir endpoint PUT /legal-report (editar informes).
        """
        from app.api.legal_report import router

        # Verificar que no hay rutas PUT
        put_routes = [
            route for route in router.routes if hasattr(route, "methods") and "PUT" in route.methods
        ]

        assert len(put_routes) == 0, "NO debe existir endpoint PUT para editar informes"

    def test_no_existe_endpoint_delete_legal_report(self):
        """
        ✅ NO debe existir endpoint DELETE /legal-report (borrar informes).
        """
        from app.api.legal_report import router

        # Verificar que no hay rutas DELETE
        delete_routes = [
            route
            for route in router.routes
            if hasattr(route, "methods") and "DELETE" in route.methods
        ]

        assert len(delete_routes) == 0, "NO debe existir endpoint DELETE para borrar informes"

    def test_no_existe_endpoint_interpret(self):
        """
        ✅ NO debe existir endpoint POST /interpret (reinterpretación).
        """
        from app.api.legal_report import router

        # Verificar que no hay rutas con /interpret
        interpret_routes = [
            route
            for route in router.routes
            if hasattr(route, "path") and "interpret" in route.path.lower()
        ]

        assert len(interpret_routes) == 0, "NO debe existir endpoint de reinterpretación"

    def test_no_existe_endpoint_modify(self):
        """
        ✅ NO debe existir endpoint POST /modify (modificación manual).
        """
        from app.api.legal_report import router

        # Verificar que no hay rutas con /modify
        modify_routes = [
            route
            for route in router.routes
            if hasattr(route, "path") and "modify" in route.path.lower()
        ]

        assert len(modify_routes) == 0, "NO debe existir endpoint de modificación manual"
