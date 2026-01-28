"""
TESTS DE CONTRATO FUNDACIONAL DE CHUNK (ENDURECIMIENTO 3.0 - FASE 1)

Objetivo: Validar que el contrato de DocumentChunk es obligatorio e inmutable.

REGLAS DURAS:
1. No puede existir DocumentChunk sin location válida
2. char_start < char_end (SIEMPRE)
3. page_start <= page_end (si ambos existen)
4. extraction_method SIEMPRE informado
5. chunk_id DEBE ser determinista

Este test suite NO implementa offsets reales.
Solo valida que el contrato no puede romperse.
"""

import pytest
from pydantic import ValidationError

from app.core.exceptions import ChunkContractViolationError
from app.models.document_chunk import (
    ChunkLocation,
    ExtractionMethod,
    generate_deterministic_chunk_id,
)

# =========================================================
# TESTS DE ChunkLocation
# =========================================================


class TestChunkLocationContract:
    """Tests del contrato de ChunkLocation."""

    def test_valid_location_minimal(self):
        """✅ Location válida con campos mínimos obligatorios."""
        location = ChunkLocation(
            char_start=0, char_end=100, extraction_method=ExtractionMethod.PDF_TEXT
        )

        assert location.char_start == 0
        assert location.char_end == 100
        assert location.extraction_method == ExtractionMethod.PDF_TEXT
        assert location.page_start is None
        assert location.page_end is None

    def test_valid_location_with_pages(self):
        """✅ Location válida con páginas."""
        location = ChunkLocation(
            char_start=0,
            char_end=100,
            extraction_method=ExtractionMethod.PDF_TEXT,
            page_start=1,
            page_end=2,
        )

        assert location.page_start == 1
        assert location.page_end == 2

    def test_valid_location_same_page(self):
        """✅ Location válida con misma página de inicio y fin."""
        location = ChunkLocation(
            char_start=0,
            char_end=100,
            extraction_method=ExtractionMethod.PDF_TEXT,
            page_start=5,
            page_end=5,
        )

        assert location.page_start == 5
        assert location.page_end == 5

    def test_invalid_char_range_equal(self):
        """❌ FALLA: char_start == char_end"""
        with pytest.raises(ChunkContractViolationError) as exc_info:
            ChunkLocation(
                char_start=100,
                char_end=100,  # ← INVÁLIDO
                extraction_method=ExtractionMethod.PDF_TEXT,
            )

        assert "char_end" in str(exc_info.value)
        assert "char_start" in str(exc_info.value)

    def test_invalid_char_range_reversed(self):
        """❌ FALLA: char_end < char_start"""
        with pytest.raises(ChunkContractViolationError) as exc_info:
            ChunkLocation(
                char_start=100,
                char_end=50,  # ← INVÁLIDO
                extraction_method=ExtractionMethod.PDF_TEXT,
            )

        assert "char_end" in str(exc_info.value)

    def test_invalid_page_range(self):
        """❌ FALLA: page_end < page_start"""
        with pytest.raises(ChunkContractViolationError) as exc_info:
            ChunkLocation(
                char_start=0,
                char_end=100,
                extraction_method=ExtractionMethod.PDF_TEXT,
                page_start=5,
                page_end=3,  # ← INVÁLIDO
            )

        assert "page_end" in str(exc_info.value)
        assert "page_start" in str(exc_info.value)

    def test_missing_extraction_method(self):
        """❌ FALLA: extraction_method es obligatorio"""
        with pytest.raises(ValidationError):
            ChunkLocation(
                char_start=0,
                char_end=100,
                # ← extraction_method faltante
            )

    def test_negative_char_start(self):
        """❌ FALLA: char_start no puede ser negativo"""
        with pytest.raises(ValidationError):
            ChunkLocation(
                char_start=-10,  # ← INVÁLIDO
                char_end=100,
                extraction_method=ExtractionMethod.PDF_TEXT,
            )

    def test_negative_page_number(self):
        """❌ FALLA: page_start no puede ser < 1"""
        with pytest.raises(ValidationError):
            ChunkLocation(
                char_start=0,
                char_end=100,
                extraction_method=ExtractionMethod.PDF_TEXT,
                page_start=0,  # ← INVÁLIDO (páginas son 1-indexed)
            )

    def test_extra_fields_forbidden(self):
        """❌ FALLA: No se permiten campos adicionales (extra='forbid')"""
        with pytest.raises(ValidationError) as exc_info:
            ChunkLocation(
                char_start=0,
                char_end=100,
                extraction_method=ExtractionMethod.PDF_TEXT,
                extra_field="not_allowed",  # ← PROHIBIDO
            )

        assert "extra_field" in str(exc_info.value).lower()


# =========================================================
# TESTS DE ExtractionMethod
# =========================================================


class TestExtractionMethod:
    """Tests del enum ExtractionMethod."""

    def test_all_extraction_methods_exist(self):
        """✅ Todos los métodos de extracción están definidos."""
        assert ExtractionMethod.PDF_TEXT == "pdf_text"
        assert ExtractionMethod.OCR == "ocr"
        assert ExtractionMethod.TABLE == "table"
        assert ExtractionMethod.DOCX_TEXT == "docx_text"
        assert ExtractionMethod.TXT == "txt"
        assert ExtractionMethod.UNKNOWN == "unknown"

    def test_extraction_method_is_required(self):
        """✅ ExtractionMethod es obligatorio en ChunkLocation."""
        # Este test es redundante con test_missing_extraction_method
        # pero documenta explícitamente el requisito
        with pytest.raises(ValidationError):
            ChunkLocation(char_start=0, char_end=100)


# =========================================================
# TESTS DE DETERMINISMO DE chunk_id
# =========================================================


class TestChunkIdDeterminism:
    """Tests de determinismo de chunk_id."""

    def test_chunk_id_is_deterministic(self):
        """✅ chunk_id es determinista para mismos inputs."""
        chunk_id_1 = generate_deterministic_chunk_id(
            case_id="CASE_001", doc_id="DOC_001", chunk_index=0, start_char=0, end_char=100
        )

        chunk_id_2 = generate_deterministic_chunk_id(
            case_id="CASE_001", doc_id="DOC_001", chunk_index=0, start_char=0, end_char=100
        )

        assert chunk_id_1 == chunk_id_2

    def test_chunk_id_changes_with_offsets(self):
        """✅ chunk_id cambia si cambian los offsets."""
        chunk_id_1 = generate_deterministic_chunk_id(
            case_id="CASE_001", doc_id="DOC_001", chunk_index=0, start_char=0, end_char=100
        )

        chunk_id_2 = generate_deterministic_chunk_id(
            case_id="CASE_001",
            doc_id="DOC_001",
            chunk_index=0,
            start_char=0,
            end_char=200,  # ← Diferente
        )

        assert chunk_id_1 != chunk_id_2

    def test_chunk_id_changes_with_index(self):
        """✅ chunk_id cambia si cambia el índice."""
        chunk_id_1 = generate_deterministic_chunk_id(
            case_id="CASE_001", doc_id="DOC_001", chunk_index=0, start_char=0, end_char=100
        )

        chunk_id_2 = generate_deterministic_chunk_id(
            case_id="CASE_001",
            doc_id="DOC_001",
            chunk_index=1,  # ← Diferente
            start_char=0,
            end_char=100,
        )

        assert chunk_id_1 != chunk_id_2

    def test_chunk_id_format(self):
        """✅ chunk_id tiene formato esperado: 'chunk_' + hash."""
        chunk_id = generate_deterministic_chunk_id(
            case_id="CASE_001", doc_id="DOC_001", chunk_index=0, start_char=0, end_char=100
        )

        assert chunk_id.startswith("chunk_")
        assert len(chunk_id) == 38  # "chunk_" (6) + hash (32)

    def test_chunk_id_reproducible_across_sessions(self):
        """✅ chunk_id es reproducible (no usa random/timestamp)."""
        # Generar 100 veces con mismos inputs
        chunk_ids = [
            generate_deterministic_chunk_id(
                case_id="CASE_001", doc_id="DOC_001", chunk_index=0, start_char=0, end_char=100
            )
            for _ in range(100)
        ]

        # Todos deben ser iguales
        assert len(set(chunk_ids)) == 1


# =========================================================
# TESTS DE PREPARACIÓN PARA ENDURECIMIENTO 3.1
# =========================================================


class TestOffsetReadiness:
    """Tests que preparan el camino para offsets reales (Endurecimiento 3.1)."""

    def test_location_supports_large_documents(self):
        """✅ ChunkLocation soporta documentos grandes (offsets > 1M)."""
        location = ChunkLocation(
            char_start=1_000_000, char_end=2_000_000, extraction_method=ExtractionMethod.PDF_TEXT
        )

        assert location.char_start == 1_000_000
        assert location.char_end == 2_000_000

    def test_location_supports_multi_page_chunks(self):
        """✅ ChunkLocation soporta chunks que abarcan múltiples páginas."""
        location = ChunkLocation(
            char_start=1000,
            char_end=5000,
            extraction_method=ExtractionMethod.PDF_TEXT,
            page_start=10,
            page_end=12,  # Chunk abarca 3 páginas
        )

        assert location.page_end - location.page_start == 2

    def test_location_preserves_extraction_metadata(self):
        """✅ ChunkLocation preserva metadata de extracción."""
        location = ChunkLocation(char_start=0, char_end=100, extraction_method=ExtractionMethod.OCR)

        # Metadata crítica para auditoría legal
        assert location.extraction_method == ExtractionMethod.OCR

    def test_location_distinguishes_extraction_methods(self):
        """✅ Sistema distingue entre métodos de extracción."""
        methods = [
            ExtractionMethod.PDF_TEXT,
            ExtractionMethod.OCR,
            ExtractionMethod.TABLE,
            ExtractionMethod.DOCX_TEXT,
            ExtractionMethod.TXT,
        ]

        locations = [
            ChunkLocation(char_start=0, char_end=100, extraction_method=method)
            for method in methods
        ]

        # Cada método es identificable
        assert len(set(loc.extraction_method for loc in locations)) == len(methods)


# =========================================================
# TESTS DE CONTRATO INMUTABLE
# =========================================================


class TestContractImmutability:
    """Tests de inmutabilidad del contrato."""

    def test_cannot_modify_location_after_creation(self):
        """✅ ChunkLocation no permite modificación post-creación (validate_assignment=True)."""
        location = ChunkLocation(
            char_start=0, char_end=100, extraction_method=ExtractionMethod.PDF_TEXT
        )

        # Intentar modificar debe fallar (Pydantic validation)
        with pytest.raises(ValidationError):
            location.char_start = 50

    def test_location_contract_is_explicit(self):
        """✅ Contrato de ChunkLocation es explícito (no asume defaults implícitos)."""
        # Todos los campos obligatorios deben ser provistos explícitamente
        with pytest.raises(ValidationError):
            ChunkLocation(
                char_start=0
                # char_end y extraction_method faltantes
            )

    def test_location_validates_on_assignment(self):
        """✅ Validaciones se ejecutan en asignación (validate_assignment=True)."""
        location = ChunkLocation(
            char_start=0, char_end=100, extraction_method=ExtractionMethod.PDF_TEXT
        )

        # Intentar asignar valor inválido debe fallar
        with pytest.raises(ValidationError):
            location.char_end = -50  # ← INVÁLIDO


# =========================================================
# SUMMARY
# =========================================================


def test_contract_summary():
    """
    RESUMEN: El contrato de chunk está explícito y enforzado.

    Este test documenta las garantías del contrato fundacional:

    1. ✅ ChunkLocation es obligatoria
    2. ✅ char_start < char_end (validado)
    3. ✅ page_start <= page_end (validado)
    4. ✅ extraction_method siempre informado
    5. ✅ chunk_id determinista
    6. ✅ Contrato inmutable (extra='forbid', validate_assignment=True)
    7. ✅ Preparado para Endurecimiento 3.1 (offsets reales)
    """
    # Este test siempre pasa - es documentación ejecutable
    assert True


# =========================================================
# TESTS DE BYPASS CERRADOS (CORRECCIONES FASE 2)
# =========================================================


class TestBypassClosure:
    """Tests que verifican que los bypass detectados están cerrados."""

    def test_extraction_method_has_no_default(self):
        """✅ extraction_method NO tiene default en modelo SQL.

        Verifica que no existe bypass estructural que permita
        persistir chunks con extraction_method=UNKNOWN sin validación explícita.
        """
        from sqlalchemy.inspection import inspect

        from app.models.document_chunk import DocumentChunk

        # Inspeccionar columna extraction_method
        mapper = inspect(DocumentChunk)
        extraction_col = mapper.columns["extraction_method"]

        # Verificar que NO tiene default
        assert extraction_col.default is None
        assert extraction_col.server_default is None
        assert not extraction_col.nullable

    def test_negative_start_char_rejected(self):
        """✅ start_char < 0 es rechazado en ChunkLocation."""
        with pytest.raises(ValidationError):
            ChunkLocation(
                char_start=-1,  # ← INVÁLIDO
                char_end=100,
                extraction_method=ExtractionMethod.PDF_TEXT,
            )
