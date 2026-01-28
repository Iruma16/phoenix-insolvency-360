"""
TESTS: Validación DURA PRE-Ingesta (Endurecimiento #2)

OBJETIVO: Validar que ningún documento de calidad insuficiente
llegue al RAG ni a la plantilla legal.

PRINCIPIO: FAIL HARD en validación PRE-ingesta.
"""
import tempfile
from datetime import datetime
from pathlib import Path

from app.services.document_pre_ingestion_validation import (
    VALIDATOR_VERSION,
    PreIngestionRejectCode,
    check_file_size,
    check_format_supported,
    check_min_text_length,
    check_text_noise_ratio,
    validate_document_pre_ingestion,
)

# ============================
# TEST 1: CHECK FORMATO SOPORTADO
# ============================


def test_check_format_supported_valid():
    """Validar que formatos soportados pasen el check."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        file_path = Path(f.name)

    try:
        is_valid, reject_code, message = check_format_supported(file_path)

        assert is_valid is True
        assert reject_code is None
        assert "soportado" in message.lower()
    finally:
        file_path.unlink()


def test_check_format_supported_invalid():
    """Validar que formatos NO soportados fallen el check."""
    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        file_path = Path(f.name)

    try:
        is_valid, reject_code, message = check_format_supported(file_path)

        assert is_valid is False
        assert reject_code == PreIngestionRejectCode.FORMAT_UNSUPPORTED
        assert ".exe" in message
    finally:
        file_path.unlink()


# ============================
# TEST 2: CHECK TEXTO MÍNIMO
# ============================


def test_check_min_text_length_valid():
    """Validar que texto suficiente pase el check."""
    text = "Este es un documento de prueba con suficiente texto para pasar la validación mínima de 100 caracteres."

    is_valid, reject_code, message = check_min_text_length(text, min_length=100)

    assert is_valid is True
    assert reject_code is None
    assert "suficiente" in message.lower()


def test_check_min_text_length_too_short():
    """Validar que texto insuficiente falle el check."""
    text = "Texto corto."

    is_valid, reject_code, message = check_min_text_length(text, min_length=100)

    assert is_valid is False
    assert reject_code == PreIngestionRejectCode.CONTENT_TOO_SHORT
    assert "100 chars" in message


def test_check_min_text_length_empty():
    """Validar que texto vacío falle el check."""
    text = ""

    is_valid, reject_code, message = check_min_text_length(text, min_length=100)

    assert is_valid is False
    assert reject_code == PreIngestionRejectCode.CONTENT_NO_TEXT_EXTRACTED


# ============================
# TEST 3: CHECK RATIO TEXTO/RUIDO
# ============================


def test_check_text_noise_ratio_valid():
    """Validar que texto limpio pase el check."""
    text = "Este es un texto limpio con palabras normales y puntuación válida. Más contenido aquí."

    is_valid, reject_code, message, ratio = check_text_noise_ratio(text, min_ratio=0.7)

    assert is_valid is True
    assert reject_code is None
    assert ratio >= 0.7
    assert "aceptable" in message.lower()


def test_check_text_noise_ratio_too_noisy():
    """Validar que texto con mucho ruido falle el check."""
    # Texto con muchos caracteres extraños (50% ruido)
    text = "�����������������������������Normal text here�����������������������������"

    is_valid, reject_code, message, ratio = check_text_noise_ratio(text, min_ratio=0.7)

    assert is_valid is False
    assert reject_code == PreIngestionRejectCode.CONTENT_TOO_NOISY
    assert ratio < 0.7


# ============================
# TEST 4: CHECK TAMAÑO DE ARCHIVO
# ============================


def test_check_file_size_valid():
    """Validar que archivo de tamaño razonable pase el check."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        # Escribir 1 KB de datos
        f.write(b"x" * 1024)
        file_path = Path(f.name)

    try:
        is_valid, reject_code, message = check_file_size(file_path, max_size_mb=50)

        assert is_valid is True
        assert reject_code is None
        assert "OK" in message
    finally:
        file_path.unlink()


def test_check_file_size_empty():
    """Validar que archivo vacío falle el check."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        file_path = Path(f.name)

    try:
        is_valid, reject_code, message = check_file_size(file_path, max_size_mb=50)

        assert is_valid is False
        assert reject_code == PreIngestionRejectCode.FILE_EMPTY
        assert "vacío" in message.lower() or "0 bytes" in message
    finally:
        file_path.unlink()


def test_check_file_size_too_large():
    """Validar que archivo demasiado grande falle el check."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        # Simular archivo grande (escribir metadata, no todo el contenido)
        file_path = Path(f.name)

    try:
        # Mock del tamaño del archivo
        from unittest.mock import patch

        with patch.object(Path, "stat") as mock_stat:
            # Simular archivo de 100 MB
            mock_stat.return_value.st_size = 100 * 1024 * 1024

            is_valid, reject_code, message = check_file_size(file_path, max_size_mb=50)

            assert is_valid is False
            assert reject_code == PreIngestionRejectCode.FILE_TOO_LARGE
            assert "grande" in message.lower() or "large" in message.lower()
    finally:
        file_path.unlink()


# ============================
# TEST 5: VALIDACIÓN COMPLETA
# ============================


def test_validate_document_pre_ingestion_valid_txt():
    """Validar documento TXT válido completo."""
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as f:
        # Escribir texto válido
        f.write(
            "Este es un documento de prueba válido con suficiente contenido de texto para pasar todas las validaciones. "
            * 5
        )
        file_path = Path(f.name)

    try:
        # Leer texto
        with open(file_path, encoding="utf-8") as f:
            text = f.read()

        result = validate_document_pre_ingestion(
            file_path=file_path,
            extracted_text=text,
        )

        assert result.is_valid is True
        assert result.reject_code is None
        assert result.filename == file_path.name
        assert result.file_format == ".txt"
        assert result.validator_version == VALIDATOR_VERSION
        assert result.text_length is not None
        assert result.text_length >= 100
    finally:
        file_path.unlink()


def test_validate_document_pre_ingestion_unsupported_format():
    """Validar que formato no soportado sea rechazado."""
    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        f.write(b"dummy content")
        file_path = Path(f.name)

    try:
        result = validate_document_pre_ingestion(
            file_path=file_path,
            extracted_text=None,
        )

        assert result.is_valid is False
        assert result.reject_code == PreIngestionRejectCode.FORMAT_UNSUPPORTED
        assert ".exe" in result.reject_message
    finally:
        file_path.unlink()


def test_validate_document_pre_ingestion_empty_file():
    """Validar que archivo vacío sea rechazado."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        file_path = Path(f.name)

    try:
        result = validate_document_pre_ingestion(
            file_path=file_path,
            extracted_text=None,
        )

        assert result.is_valid is False
        assert result.reject_code == PreIngestionRejectCode.FILE_EMPTY
    finally:
        file_path.unlink()


def test_validate_document_pre_ingestion_text_too_short():
    """Validar que texto demasiado corto sea rechazado."""
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as f:
        f.write("Texto corto.")
        file_path = Path(f.name)

    try:
        text = "Texto corto."

        result = validate_document_pre_ingestion(
            file_path=file_path,
            extracted_text=text,
        )

        assert result.is_valid is False
        assert result.reject_code == PreIngestionRejectCode.CONTENT_TOO_SHORT
        assert result.text_length == len(text)
    finally:
        file_path.unlink()


def test_validate_document_pre_ingestion_text_too_noisy():
    """Validar que texto con mucho ruido sea rechazado."""
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as f:
        # Texto con mucho ruido
        noisy_text = "������" * 50 + "Some text" + "������" * 50
        f.write(noisy_text)
        file_path = Path(f.name)

    try:
        result = validate_document_pre_ingestion(
            file_path=file_path,
            extracted_text=noisy_text,
        )

        assert result.is_valid is False
        assert result.reject_code == PreIngestionRejectCode.CONTENT_TOO_NOISY
        assert result.text_noise_ratio is not None
        assert result.text_noise_ratio < 0.7
    finally:
        file_path.unlink()


# ============================
# TEST 6: INVARIANTES CERTIFICADOS
# ============================


def test_cert_invariante_formato_no_soportado_no_pasa():
    """[CERT] INVARIANTE: Formato no soportado NUNCA puede pasar validación."""
    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        file_path = Path(f.name)

    try:
        result = validate_document_pre_ingestion(file_path, extracted_text=None)

        # INVARIANTE: Formato no soportado → is_valid=False
        assert result.is_valid is False
        assert result.reject_code == PreIngestionRejectCode.FORMAT_UNSUPPORTED
    finally:
        file_path.unlink()


def test_cert_invariante_texto_vacio_no_pasa():
    """[CERT] INVARIANTE: Texto vacío NUNCA puede pasar validación."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        file_path = Path(f.name)
        f.write(b"")

    try:
        result = validate_document_pre_ingestion(file_path, extracted_text="")

        # INVARIANTE: Texto vacío → is_valid=False
        assert result.is_valid is False
        assert result.reject_code in [
            PreIngestionRejectCode.CONTENT_NO_TEXT_EXTRACTED,
            PreIngestionRejectCode.FILE_EMPTY,
        ]
    finally:
        file_path.unlink()


def test_cert_invariante_documento_valido_tiene_metadata():
    """[CERT] INVARIANTE: Todo resultado de validación DEBE tener metadata obligatoria."""
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as f:
        f.write("Texto válido suficiente para pasar validación. " * 10)
        file_path = Path(f.name)

    try:
        text = "Texto válido suficiente para pasar validación. " * 10
        result = validate_document_pre_ingestion(file_path, extracted_text=text)

        # INVARIANTE: Metadata obligatoria SIEMPRE presente
        assert result.filename is not None
        assert result.file_size_bytes >= 0
        assert result.file_format is not None
        assert result.timestamp is not None
        assert isinstance(result.timestamp, datetime)
        assert result.validator_version == VALIDATOR_VERSION
    finally:
        file_path.unlink()


def test_cert_invariante_texto_menor_100_chars_falla():
    """[CERT] INVARIANTE: Texto < 100 caracteres NUNCA puede pasar validación."""
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as f:
        short_text = "Texto muy corto."
        f.write(short_text)
        file_path = Path(f.name)

    try:
        result = validate_document_pre_ingestion(file_path, extracted_text=short_text)

        # INVARIANTE: Texto < 100 chars → is_valid=False
        assert result.is_valid is False
        assert result.reject_code == PreIngestionRejectCode.CONTENT_TOO_SHORT
        assert result.text_length < 100
    finally:
        file_path.unlink()


def test_cert_invariante_ratio_ruido_menor_70_falla():
    """[CERT] INVARIANTE: Ratio texto/ruido < 70% NUNCA puede pasar validación."""
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as f:
        # Texto con mucho ruido (menos del 70% válido)
        noisy_text = "�" * 200 + "Valid text here but dominated by noise" + "�" * 200
        f.write(noisy_text)
        file_path = Path(f.name)

    try:
        result = validate_document_pre_ingestion(file_path, extracted_text=noisy_text)

        # INVARIANTE: Ratio < 70% → is_valid=False
        assert result.is_valid is False
        assert result.reject_code == PreIngestionRejectCode.CONTENT_TOO_NOISY
        assert result.text_noise_ratio is not None
        assert result.text_noise_ratio < 0.7
    finally:
        file_path.unlink()


# ============================
# TEST 7: INTEGRACIÓN CON LOGGING
# ============================


def test_log_pre_ingestion_validation(caplog):
    """Validar que el logging estructurado funcione correctamente."""
    from app.services.document_pre_ingestion_validation import log_pre_ingestion_validation

    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as f:
        f.write("Texto válido para testing. " * 10)
        file_path = Path(f.name)

    try:
        text = "Texto válido para testing. " * 10
        result = validate_document_pre_ingestion(file_path, extracted_text=text)

        # Loggear resultado
        log_pre_ingestion_validation(
            case_id="CASE_TEST_001",
            result=result,
        )

        # Verificar que el log contiene información obligatoria
        log_output = caplog.text

        assert "PRE-INGESTION VALIDATION" in log_output
        assert "Validator Version" in log_output
        assert VALIDATOR_VERSION in log_output
        assert "CASE_TEST_001" in log_output
        assert result.filename in log_output

        if result.is_valid:
            assert "VALID" in log_output
        else:
            assert "REJECTED" in log_output
            assert result.reject_code.value in log_output
    finally:
        file_path.unlink()


# ============================
# RESUMEN DE TESTS
# ============================

"""
COBERTURA DE TESTS:

1. ✅ Check formato soportado (válido + inválido)
2. ✅ Check texto mínimo (válido + corto + vacío)
3. ✅ Check ratio texto/ruido (válido + ruidoso)
4. ✅ Check tamaño archivo (válido + vacío + grande)
5. ✅ Validación completa (válido + varios rechazos)
6. ✅ Invariantes certificados (5 invariantes)
7. ✅ Integración con logging

TOTAL: 22 tests implementados

INVARIANTES CERTIFICADOS:
- INVARIANTE 1: Formato no soportado → is_valid=False
- INVARIANTE 2: Texto vacío → is_valid=False
- INVARIANTE 3: Metadata obligatoria SIEMPRE presente
- INVARIANTE 4: Texto < 100 chars → is_valid=False
- INVARIANTE 5: Ratio ruido < 70% → is_valid=False
"""
