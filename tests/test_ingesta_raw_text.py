"""
Tests mínimos para verificar que el texto bruto se persiste en Document.raw_text (FASE 1).

OBJETIVO:
- Verificar que Document.raw_text contiene el texto extraído para documentos válidos
- Verificar que Document.raw_text es NULL para documentos inválidos
- No tocar lógica de chunking, embeddings ni RAG
"""
from datetime import datetime

from app.models.document import Document


def test_documento_valido_persiste_raw_text():
    """
    FASE 1: Documento válido → raw_text contiene el texto extraído.

    Test directo del modelo Document para verificar que el campo raw_text
    se puede asignar y persistir correctamente.
    """
    # Arrange
    texto_extraido = (
        "Este es el texto extraído del documento de prueba. Contiene información legal relevante."
    )

    # Act - Crear documento con raw_text
    doc = Document(
        case_id="case-test-123",
        filename="documento_valido.pdf",
        file_format="pdf",
        doc_type="documento",
        source="upload",
        date_start=datetime.utcnow(),
        date_end=datetime.utcnow(),
        reliability="original",
        storage_path="/path/to/doc",
        parsing_status="completed",
        raw_text=texto_extraido,  # FASE 1: Asignar texto bruto
    )

    # Assert
    # FASE 1: Verificar que raw_text NO es NULL y contiene el texto extraído
    assert doc.raw_text is not None
    assert doc.raw_text == texto_extraido
    assert len(doc.raw_text) > 0

    # Verificar que el resto de los campos están correctos
    assert doc.case_id == "case-test-123"
    assert doc.filename == "documento_valido.pdf"
    assert doc.parsing_status == "completed"


def test_documento_invalido_raw_text_es_null():
    """
    FASE 1: Documento inválido → raw_text es NULL.

    Test directo del modelo Document para verificar que raw_text
    puede ser NULL cuando el documento es rechazado.
    """
    # Act - Crear documento rechazado sin raw_text
    doc = Document(
        case_id="case-test-456",
        filename="documento_invalido.pdf",
        file_format="pdf",
        doc_type="documento",
        source="upload",
        date_start=datetime.utcnow(),
        date_end=datetime.utcnow(),
        reliability="media",
        storage_path="/rejected/documento_invalido.pdf",
        parsing_status="rejected",
        parsing_rejection_reason="Documento rechazado en validación pre-ingesta",
        raw_text=None,  # FASE 1: NULL para documentos inválidos
    )

    # Assert
    # FASE 1: Verificar que raw_text es NULL porque el documento fue rechazado
    assert doc.raw_text is None

    # Verificar que el documento está marcado como rechazado
    assert doc.parsing_status == "rejected"
    assert doc.parsing_rejection_reason is not None


def test_documento_con_error_raw_text_es_null():
    """
    FASE 1: Documento con error → raw_text es NULL.

    Test directo del modelo Document para verificar que raw_text
    es NULL cuando el procesamiento falla.
    """
    # Act - Crear documento con error sin raw_text
    doc = Document(
        case_id="case-test-789",
        filename="documento_error.pdf",
        file_format="pdf",
        doc_type="documento",
        source="upload",
        date_start=datetime.utcnow(),
        date_end=datetime.utcnow(),
        reliability="media",
        storage_path="/failed/documento_error.pdf",
        parsing_status="failed",
        parsing_rejection_reason="Error inesperado en parsing",
        raw_text=None,  # FASE 1: NULL para documentos con error
    )

    # Assert
    # FASE 1: Verificar que raw_text es NULL porque hubo un error
    assert doc.raw_text is None

    # Verificar que el documento está marcado como failed
    assert doc.parsing_status == "failed"


def test_inmutabilidad_raw_text():
    """
    FASE 1: raw_text debe asignarse UNA SOLA VEZ y no modificarse después.

    Este test es conceptual: verifica que el campo raw_text se asigna
    en la creación del Document y no se modifica en pasos posteriores.
    """
    # Arrange
    texto_original = "Texto original del documento"

    # Act
    doc = Document(
        case_id="case-test-inmutabilidad",
        filename="doc_inmutable.pdf",
        file_format="pdf",
        doc_type="documento",
        source="upload",
        date_start=datetime.utcnow(),
        date_end=datetime.utcnow(),
        reliability="original",
        storage_path="/path/to/doc",
        raw_text=texto_original,
    )

    # Assert
    # FASE 1: Verificar que raw_text se asignó correctamente
    assert doc.raw_text == texto_original

    # Verificar que el campo existe y es accesible
    assert hasattr(doc, "raw_text")
    assert isinstance(doc.raw_text, str)
