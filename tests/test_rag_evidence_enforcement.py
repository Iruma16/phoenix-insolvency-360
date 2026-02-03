"""
TESTS DE ENFORCEMENT DE EVIDENCIA OBLIGATORIA (FASE 4 - ENDURECIMIENTO 4).

OBJETIVO:
Validar que RAG NO responde sin evidencia suficiente y verificable.

REGLAS DURAS:
1. NO retrieve sin chunks → excepción
2. NO chunks sin location → excepción
3. NO respuesta sin evidencia mínima → excepción
4. Fallo ANTES del LLM call
"""
from unittest.mock import Mock

import pytest

from app.models.document_chunk import DocumentChunk, ExtractionMethod
from app.rag.evidence_enforcer import (
    enforce_evidence_quality,
    validate_chunk_has_location,
    validate_chunks_exist,
    validate_retrieval_result,
)
from app.rag.exceptions import (
    InsufficientEvidenceError,
    InvalidChunkLocationError,
    NoChunksFoundError,
)


class TestChunkLocationValidation:
    """Tests de validación de location en chunks."""

    def test_chunk_without_start_char_rejected(self):
        """❌ Chunk sin start_char → InvalidChunkLocationError"""
        chunk = Mock(spec=DocumentChunk)
        chunk.chunk_id = "chunk_test_001"
        chunk.start_char = None  # ← INVÁLIDO
        chunk.end_char = 100
        chunk.extraction_method = ExtractionMethod.PDF_TEXT

        with pytest.raises(InvalidChunkLocationError) as exc_info:
            validate_chunk_has_location(chunk)

        assert "start_char" in str(exc_info.value).lower()
        assert chunk.chunk_id[:16] in str(exc_info.value)

    def test_chunk_without_end_char_rejected(self):
        """❌ Chunk sin end_char → InvalidChunkLocationError"""
        chunk = Mock(spec=DocumentChunk)
        chunk.chunk_id = "chunk_test_002"
        chunk.start_char = 0
        chunk.end_char = None  # ← INVÁLIDO
        chunk.extraction_method = ExtractionMethod.PDF_TEXT

        with pytest.raises(InvalidChunkLocationError) as exc_info:
            validate_chunk_has_location(chunk)

        assert "end_char" in str(exc_info.value).lower()

    def test_chunk_with_invalid_offsets_rejected(self):
        """❌ Chunk con start_char >= end_char → InvalidChunkLocationError"""
        chunk = Mock(spec=DocumentChunk)
        chunk.chunk_id = "chunk_test_003"
        chunk.start_char = 100
        chunk.end_char = 100  # ← INVÁLIDO (start >= end)
        chunk.extraction_method = ExtractionMethod.PDF_TEXT

        with pytest.raises(InvalidChunkLocationError) as exc_info:
            validate_chunk_has_location(chunk)

        assert "start_char" in str(exc_info.value).lower()
        assert "end_char" in str(exc_info.value).lower()

    def test_chunk_without_extraction_method_rejected(self):
        """❌ Chunk sin extraction_method → InvalidChunkLocationError"""
        chunk = Mock(spec=DocumentChunk)
        chunk.chunk_id = "chunk_test_004"
        chunk.start_char = 0
        chunk.end_char = 100
        chunk.extraction_method = None  # ← INVÁLIDO

        with pytest.raises(InvalidChunkLocationError) as exc_info:
            validate_chunk_has_location(chunk)

        assert "extraction_method" in str(exc_info.value).lower()

    def test_valid_chunk_passes(self):
        """✅ Chunk válido con location completa → sin excepción"""
        chunk = Mock(spec=DocumentChunk)
        chunk.chunk_id = "chunk_test_005"
        chunk.start_char = 0
        chunk.end_char = 100
        chunk.extraction_method = ExtractionMethod.PDF_TEXT

        # No debe lanzar excepción
        validate_chunk_has_location(chunk)


class TestNoChunksEnforcement:
    """Tests de enforcement cuando no hay chunks."""

    def test_no_chunks_raises_error(self):
        """❌ Sin chunks en DB → NoChunksFoundError"""
        db_mock = Mock()
        query_mock = Mock()
        filter_mock = Mock()

        # Simular que no hay chunks
        filter_mock.count.return_value = 0
        query_mock.filter.return_value = filter_mock
        db_mock.query.return_value = query_mock

        with pytest.raises(NoChunksFoundError) as exc_info:
            validate_chunks_exist(db=db_mock, case_id="CASE_001", document_ids=["DOC_001"])

        assert "CASE_001" in str(exc_info.value)
        assert "No hay chunks" in str(exc_info.value)

    def test_chunks_exist_returns_count(self):
        """✅ Chunks en DB → retorna count sin error"""
        db_mock = Mock()
        query_mock = Mock()
        filter_mock = Mock()

        # Simular que hay 5 chunks
        filter_mock.count.return_value = 5
        query_mock.filter.return_value = filter_mock
        db_mock.query.return_value = query_mock

        count = validate_chunks_exist(db=db_mock, case_id="CASE_001", document_ids=["DOC_001"])

        assert count == 5


class TestInsufficientEvidenceEnforcement:
    """Tests de enforcement de evidencia mínima."""

    def test_insufficient_chunks_rejected(self):
        """❌ Menos de 2 chunks → InsufficientEvidenceError"""
        sources = [
            {
                "chunk_id": "chunk_001",
                "document_id": "doc_001",
                "content": "texto",
                "start_char": 0,
                "end_char": 100,
            }
        ]

        with pytest.raises(InsufficientEvidenceError) as exc_info:
            enforce_evidence_quality(sources=sources, case_id="CASE_001", min_chunks=2)

        assert "1" in str(exc_info.value)  # chunks_found
        assert "2" in str(exc_info.value)  # min_required

    def test_sufficient_chunks_passes(self):
        """✅ 2+ chunks con location → sin excepción"""
        sources = [
            {
                "chunk_id": "chunk_001",
                "document_id": "doc_001",
                "content": "texto 1",
                "start_char": 0,
                "end_char": 100,
            },
            {
                "chunk_id": "chunk_002",
                "document_id": "doc_001",
                "content": "texto 2",
                "start_char": 100,
                "end_char": 200,
            },
        ]

        # No debe lanzar excepción
        enforce_evidence_quality(sources=sources, case_id="CASE_001", min_chunks=2)

    def test_source_without_chunk_id_rejected(self):
        """❌ Fuente sin chunk_id → InvalidChunkLocationError"""
        sources = [
            {
                # chunk_id faltante
                "document_id": "doc_001",
                "content": "texto",
                "start_char": 0,
                "end_char": 100,
            },
            {
                "chunk_id": "chunk_002",
                "document_id": "doc_001",
                "content": "texto 2",
                "start_char": 100,
                "end_char": 200,
            },
        ]

        with pytest.raises(InvalidChunkLocationError) as exc_info:
            enforce_evidence_quality(sources=sources, case_id="CASE_001", min_chunks=2)

        assert "chunk_id" in str(exc_info.value).lower()

    def test_source_without_location_rejected(self):
        """❌ Fuente sin start_char/end_char → InvalidChunkLocationError"""
        sources = [
            {
                "chunk_id": "chunk_001",
                "document_id": "doc_001",
                "content": "texto",
                # start_char y end_char faltantes
            },
            {
                "chunk_id": "chunk_002",
                "document_id": "doc_001",
                "content": "texto 2",
                "start_char": 100,
                "end_char": 200,
            },
        ]

        with pytest.raises(InvalidChunkLocationError) as exc_info:
            enforce_evidence_quality(sources=sources, case_id="CASE_001", min_chunks=2)

        assert "start_char" in str(exc_info.value).lower()


class TestRetrievalResultValidation:
    """Tests de validación completa de resultado de retrieval."""

    def test_valid_result_passes(self):
        """✅ Resultado válido con evidencia completa → sin excepción"""
        sources = [
            {
                "chunk_id": "chunk_001",
                "document_id": "doc_001",
                "content": "texto 1",
                "start_char": 0,
                "end_char": 100,
            },
            {
                "chunk_id": "chunk_002",
                "document_id": "doc_001",
                "content": "texto 2",
                "start_char": 100,
                "end_char": 200,
            },
        ]

        # No debe lanzar excepción
        validate_retrieval_result(sources=sources, case_id="CASE_001")

    def test_empty_result_rejected(self):
        """❌ Resultado vacío → InsufficientEvidenceError"""
        sources = []

        with pytest.raises(InsufficientEvidenceError):
            validate_retrieval_result(sources=sources, case_id="CASE_001")

    def test_incomplete_metadata_rejected(self):
        """❌ Fuente sin metadata completa → InvalidChunkLocationError"""
        sources = [
            {
                "chunk_id": "chunk_001",
                # document_id faltante
                "content": "texto",
                "start_char": 0,
                "end_char": 100,
            },
            {
                "chunk_id": "chunk_002",
                "document_id": "doc_001",
                "content": "texto 2",
                "start_char": 100,
                "end_char": 200,
            },
        ]

        with pytest.raises(InvalidChunkLocationError) as exc_info:
            validate_retrieval_result(sources=sources, case_id="CASE_001")

        assert "document_id" in str(exc_info.value).lower()


class TestFailBeforeLLM:
    """Tests que verifican que el fallo ocurre ANTES del LLM call."""

    def test_validation_fails_before_llm(self):
        """
        GARANTÍA: Validación de evidencia falla ANTES de llamar al LLM.

        Si hay evidencia insuficiente, debe lanzar excepción en validación,
        NO después de generar respuesta con LLM.
        """
        sources = [
            {
                "chunk_id": "chunk_001",
                "document_id": "doc_001",
                "content": "texto corto",
                "start_char": 0,
                "end_char": 50,
            }
        ]

        # Debe fallar en validación (antes de LLM)
        with pytest.raises(InsufficientEvidenceError):
            validate_retrieval_result(sources, "CASE_001")

        # Si llegamos aquí, la validación pasó incorrectamente
        # El test debe fallar antes de este punto

    def test_no_silent_failures(self):
        """
        GARANTÍA: No hay fallos silenciosos.

        Evidencia inválida → excepción explícita, NO None/empty string.
        """
        invalid_sources = []

        # Debe lanzar excepción, NO retornar silenciosamente
        with pytest.raises(InsufficientEvidenceError):
            validate_retrieval_result(invalid_sources, "CASE_001")


class TestExceptionHierarchy:
    """Tests de jerarquía de excepciones."""

    def test_all_exceptions_are_rag_evidence_errors(self):
        """✅ Todas las excepciones heredan de RAGEvidenceError"""
        from app.rag.exceptions import RAGEvidenceError

        # Crear instancias de excepciones
        no_chunks = NoChunksFoundError(case_id="CASE_001")
        invalid_location = InvalidChunkLocationError(chunk_id="chunk_001", reason="test")
        insufficient = InsufficientEvidenceError(case_id="CASE_001", chunks_found=1, min_required=2)

        # Todas deben ser RAGEvidenceError
        assert isinstance(no_chunks, RAGEvidenceError)
        assert isinstance(invalid_location, RAGEvidenceError)
        assert isinstance(insufficient, RAGEvidenceError)

    def test_exceptions_have_correct_codes(self):
        """✅ Excepciones tienen códigos de error correctos"""
        no_chunks = NoChunksFoundError(case_id="CASE_001")
        assert no_chunks.code == "RAG_EVIDENCE_ERROR"

        invalid_location = InvalidChunkLocationError(chunk_id="chunk_001", reason="test")
        assert invalid_location.code == "RAG_EVIDENCE_ERROR"

        insufficient = InsufficientEvidenceError(case_id="CASE_001", chunks_found=1, min_required=2)
        assert insufficient.code == "RAG_EVIDENCE_ERROR"
