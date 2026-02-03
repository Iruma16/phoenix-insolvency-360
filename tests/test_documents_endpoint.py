"""
TESTS DE ENDPOINT DE GESTIÓN DE DOCUMENTOS (PANTALLA 1).

Verifican que:
- NO se permite subir a case_id inexistente
- NO se permite modificar documentos existentes
- NO se inventan estados
- chunks_count refleja la realidad
- NO se silencian errores del core
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from fastapi import HTTPException, UploadFile

from app.api.documents import (
    _build_document_summary,
    _calculate_document_status,
    ingest_documents,
    list_documents,
)
from app.models.case import Case
from app.models.document import Document
from app.models.document_summary import DocumentStatus


class TestCalculateDocumentStatus:
    """Tests de cálculo de estado de documento."""

    def test_rejected_es_failed(self):
        """
        ✅ Documento con parsing_status='rejected' → FAILED.
        """
        mock_doc = Mock(spec=Document)
        mock_doc.parsing_status = "rejected"

        status = _calculate_document_status(mock_doc, chunks_count=0)

        assert status == DocumentStatus.FAILED

    def test_failed_es_failed(self):
        """
        ✅ Documento con parsing_status='failed' → FAILED.
        """
        mock_doc = Mock(spec=Document)
        mock_doc.parsing_status = "failed"

        status = _calculate_document_status(mock_doc, chunks_count=0)

        assert status == DocumentStatus.FAILED

    def test_completed_con_chunks_es_ingested(self):
        """
        ✅ Documento con parsing_status='completed' y chunks → INGESTED.
        """
        mock_doc = Mock(spec=Document)
        mock_doc.parsing_status = "completed"

        status = _calculate_document_status(mock_doc, chunks_count=5)

        assert status == DocumentStatus.INGESTED

    def test_completed_sin_chunks_es_pending(self):
        """
        ✅ Documento con parsing_status='completed' pero sin chunks → PENDING.
        """
        mock_doc = Mock(spec=Document)
        mock_doc.parsing_status = "completed"

        status = _calculate_document_status(mock_doc, chunks_count=0)

        assert status == DocumentStatus.PENDING

    def test_pending_es_pending(self):
        """
        ✅ Documento con parsing_status='pending' → PENDING.
        """
        mock_doc = Mock(spec=Document)
        mock_doc.parsing_status = "pending"

        status = _calculate_document_status(mock_doc, chunks_count=0)

        assert status == DocumentStatus.PENDING


class TestBuildDocumentSummary:
    """Tests de construcción de DocumentSummary desde el core."""

    def test_build_summary_refleja_chunks_reales(self):
        """
        ✅ _build_document_summary devuelve chunks_count real.
        """
        mock_doc = Mock(spec=Document)
        mock_doc.document_id = "doc-1"
        mock_doc.case_id = "case-1"
        mock_doc.filename = "test.pdf"
        mock_doc.file_format = "PDF"
        mock_doc.parsing_status = "completed"
        mock_doc.parsing_rejection_reason = None
        mock_doc.created_at = datetime.utcnow()

        # Mock DB con 10 chunks
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 10

        result = _build_document_summary(mock_doc, db=mock_db)

        assert result.chunks_count == 10
        assert result.status == DocumentStatus.INGESTED

    def test_build_summary_sin_chunks_es_pending(self):
        """
        ✅ _build_document_summary sin chunks → PENDING.
        """
        mock_doc = Mock(spec=Document)
        mock_doc.document_id = "doc-1"
        mock_doc.case_id = "case-1"
        mock_doc.filename = "test.pdf"
        mock_doc.file_format = "PDF"
        mock_doc.parsing_status = "pending"
        mock_doc.parsing_rejection_reason = None
        mock_doc.created_at = datetime.utcnow()

        # Mock DB sin chunks
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 0

        result = _build_document_summary(mock_doc, db=mock_db)

        assert result.chunks_count == 0
        assert result.status == DocumentStatus.PENDING

    def test_build_summary_failed_incluye_error_message(self):
        """
        ✅ _build_document_summary con FAILED incluye error_message.
        """
        mock_doc = Mock(spec=Document)
        mock_doc.document_id = "doc-1"
        mock_doc.case_id = "case-1"
        mock_doc.filename = "test.pdf"
        mock_doc.file_format = "PDF"
        mock_doc.parsing_status = "rejected"
        mock_doc.parsing_rejection_reason = "Documento corrupto"
        mock_doc.created_at = datetime.utcnow()

        # Mock DB
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 0

        result = _build_document_summary(mock_doc, db=mock_db)

        assert result.status == DocumentStatus.FAILED
        assert result.error_message == "Documento corrupto"


class TestListDocuments:
    """Tests de listado de documentos."""

    def test_list_documents_caso_inexistente_falla_404(self):
        """
        ✅ Listar documentos de caso inexistente → 404.
        """
        mock_db = MagicMock()

        # Caso no existe
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            list_documents(case_id="inexistente", db=mock_db)

        assert exc_info.value.status_code == 404
        assert "no encontrado" in exc_info.value.detail.lower()

    def test_list_documents_devuelve_estado_real(self):
        """
        ✅ list_documents devuelve estado real del core.
        """
        mock_case = Mock(spec=Case)
        mock_case.case_id = "case-1"

        mock_doc1 = Mock(spec=Document)
        mock_doc1.document_id = "doc-1"
        mock_doc1.case_id = "case-1"
        mock_doc1.filename = "doc1.pdf"
        mock_doc1.file_format = "PDF"
        mock_doc1.parsing_status = "completed"
        mock_doc1.parsing_rejection_reason = None
        mock_doc1.created_at = datetime(2025, 1, 2)

        mock_doc2 = Mock(spec=Document)
        mock_doc2.document_id = "doc-2"
        mock_doc2.case_id = "case-1"
        mock_doc2.filename = "doc2.pdf"
        mock_doc2.file_format = "PDF"
        mock_doc2.parsing_status = "rejected"
        mock_doc2.parsing_rejection_reason = "Error"
        mock_doc2.created_at = datetime(2025, 1, 1)

        mock_db = MagicMock()

        # Contador de llamadas
        call_count = [0]

        def mock_query(model):
            call_count[0] += 1
            current_call = call_count[0]

            if current_call == 1:
                # Primera llamada: buscar caso
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.first.return_value = mock_case
                return mock_query_obj
            elif current_call == 2:
                # Segunda llamada: listar documentos
                mock_query_obj = MagicMock()
                mock_query_obj.filter.return_value.order_by.return_value.all.return_value = [
                    mock_doc1,
                    mock_doc2,
                ]
                return mock_query_obj
            else:
                # Llamadas siguientes: count de chunks para cada documento
                mock_query_obj = MagicMock()
                # doc1 tiene 5 chunks, doc2 tiene 0
                if (current_call - 2) % 2 == 1:  # doc1
                    mock_query_obj.filter.return_value.count.return_value = 5
                else:  # doc2
                    mock_query_obj.filter.return_value.count.return_value = 0
                return mock_query_obj

        mock_db.query.side_effect = mock_query

        result = list_documents(case_id="case-1", db=mock_db)

        assert len(result) == 2
        assert result[0].document_id == "doc-1"
        assert result[0].status == DocumentStatus.INGESTED
        assert result[0].chunks_count == 5
        assert result[1].document_id == "doc-2"
        assert result[1].status == DocumentStatus.FAILED


class TestEndpointInvariants:
    """Tests de invariantes del dominio."""

    def test_no_existe_endpoint_put_documents(self):
        """
        ✅ NO debe existir endpoint PUT /documents (editar documento).
        """
        from app.api.documents import router

        # Verificar que no hay rutas PUT
        put_routes = [
            route for route in router.routes if hasattr(route, "methods") and "PUT" in route.methods
        ]

        assert len(put_routes) == 0, "NO debe existir endpoint PUT para editar documentos"

    def test_no_existe_endpoint_delete_documents(self):
        """
        ✅ NO debe existir endpoint DELETE /documents (borrar documento).
        """
        from app.api.documents import router

        # Verificar que no hay rutas DELETE
        delete_routes = [
            route
            for route in router.routes
            if hasattr(route, "methods") and "DELETE" in route.methods
        ]

        assert len(delete_routes) == 0, "NO debe existir endpoint DELETE para borrar documentos"

    def test_no_existe_endpoint_retry(self):
        """
        ✅ NO debe existir endpoint POST /documents/{id}/retry (reintentar).
        """
        from app.api.documents import router

        # Verificar que no hay rutas con /retry
        retry_routes = [
            route
            for route in router.routes
            if hasattr(route, "path") and "retry" in route.path.lower()
        ]

        assert len(retry_routes) == 0, "NO debe existir endpoint para reintentar automáticamente"


class TestIngestDocuments:
    """Tests de ingesta de documentos."""

    @pytest.mark.asyncio
    async def test_ingest_documents_caso_inexistente_falla_404(self):
        """
        ✅ Ingerir documentos en caso inexistente → 404.
        """
        mock_db = MagicMock()

        # Caso no existe
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Mock file
        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = "test.pdf"
        mock_file.read.return_value = b"test content"

        with pytest.raises(HTTPException) as exc_info:
            await ingest_documents(case_id="inexistente", files=[mock_file], db=mock_db)

        assert exc_info.value.status_code == 404
        assert "no encontrado" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_ingest_documents_sin_archivos_falla_400(self):
        """
        ✅ Ingerir sin archivos → 400.
        """
        mock_db = MagicMock()

        mock_case = Mock(spec=Case)
        mock_case.case_id = "case-1"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_case

        with pytest.raises(HTTPException) as exc_info:
            await ingest_documents(case_id="case-1", files=[], db=mock_db)

        assert exc_info.value.status_code == 400
        assert "archivos" in exc_info.value.detail.lower()
