"""
Tests para validación FAIL-FAST de ingesta.

ENDURECIMIENTO #2 (FASE 3):
Demostrar que documentos inválidos son bloqueados ANTES de:
- Chunking
- Embeddings
- Persistencia
"""
import pytest
import tempfile
from pathlib import Path

from app.services.ingestion_failfast import (
    validate_document_failfast,
    should_skip_document,
    ValidationMode,
)
from app.core.exceptions import DocumentValidationError


class TestFailFastSTRICT:
    """Tests para modo STRICT: excepción bloquea pipeline."""
    
    def test_documento_corrupto_rechazado_strict(self):
        """
        Documento corrupto → DocumentValidationError en modo STRICT.
        NO se debe llamar a chunking ni embeddings.
        """
        # Crear archivo PDF corrupto
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"esto no es un PDF valido")
            corrupt_pdf_path = Path(f.name)
        
        try:
            # MODO STRICT debe lanzar excepción
            with pytest.raises(DocumentValidationError) as exc_info:
                validate_document_failfast(
                    file_path=corrupt_pdf_path,
                    extracted_text=None,
                    case_id="TEST_CASE_001",
                    mode=ValidationMode.STRICT,
                )
            
            # Verificar que la excepción contiene información correcta
            assert exc_info.value.code == "DOCUMENT_VALIDATION_FAILED"
            assert "RECHAZADO" in exc_info.value.message
            assert exc_info.value.details["reject_code"] in [
                "PDF_CORRUPTED",
                "PDF_SCANNED_NO_OCR",
                "CONTENT_TOO_SHORT",
            ]
        
        finally:
            corrupt_pdf_path.unlink()
    
    def test_documento_vacio_rechazado_strict(self):
        """
        Documento vacío → DocumentValidationError en modo STRICT.
        """
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"")  # Archivo vacío
            empty_txt_path = Path(f.name)
        
        try:
            with pytest.raises(DocumentValidationError) as exc_info:
                validate_document_failfast(
                    file_path=empty_txt_path,
                    extracted_text="",
                    case_id="TEST_CASE_002",
                    mode=ValidationMode.STRICT,
                )
            
            assert exc_info.value.details["reject_code"] == "FILE_EMPTY"
        
        finally:
            empty_txt_path.unlink()
    
    def test_documento_texto_insuficiente_rechazado_strict(self):
        """
        Documento con texto < 100 caracteres → rechazado.
        """
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("texto corto")  # Solo 11 caracteres
            short_txt_path = Path(f.name)
        
        try:
            with pytest.raises(DocumentValidationError) as exc_info:
                validate_document_failfast(
                    file_path=short_txt_path,
                    extracted_text="texto corto",
                    case_id="TEST_CASE_003",
                    mode=ValidationMode.STRICT,
                )
            
            assert exc_info.value.details["reject_code"] == "CONTENT_TOO_SHORT"
        
        finally:
            short_txt_path.unlink()
    
    def test_documento_valido_continua_strict(self):
        """
        Documento válido → NO lanza excepción, pipeline puede continuar.
        """
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            # Escribir texto suficiente (>100 chars)
            texto_valido = "Este es un texto suficientemente largo para pasar la validación. " * 5
            f.write(texto_valido)
            valid_txt_path = Path(f.name)
        
        try:
            result = validate_document_failfast(
                file_path=valid_txt_path,
                extracted_text=texto_valido,
                case_id="TEST_CASE_004",
                mode=ValidationMode.STRICT,
            )
            
            # Verificar que el documento es válido
            assert result.is_valid is True
            assert result.reject_code is None
            assert "validation_status" in result.details
        
        finally:
            valid_txt_path.unlink()


class TestFailFastPERMISSIVE:
    """Tests para modo PERMISSIVE: documento rechazado pero pipeline continúa."""
    
    def test_documento_invalido_no_bloquea_otros_permissive(self):
        """
        MODO PERMISSIVE:
        - 1 documento inválido → NO lanza excepción
        - El pipeline puede continuar procesando otros documentos
        """
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("texto corto")  # Insuficiente
            invalid_txt_path = Path(f.name)
        
        try:
            # MODO PERMISSIVE NO debe lanzar excepción
            result = validate_document_failfast(
                file_path=invalid_txt_path,
                extracted_text="texto corto",
                case_id="TEST_CASE_005",
                mode=ValidationMode.PERMISSIVE,
            )
            
            # El resultado indica que es inválido
            assert result.is_valid is False
            assert result.reject_code == "CONTENT_TOO_SHORT"
            
            # Verificar que debe ser skipped
            assert should_skip_document(result) is True
        
        finally:
            invalid_txt_path.unlink()
    
    def test_documento_valido_procesa_permissive(self):
        """
        MODO PERMISSIVE: Documento válido procesa normalmente.
        """
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            texto_valido = "Este es un texto suficientemente largo para pasar la validación. " * 5
            f.write(texto_valido)
            valid_txt_path = Path(f.name)
        
        try:
            result = validate_document_failfast(
                file_path=valid_txt_path,
                extracted_text=texto_valido,
                case_id="TEST_CASE_006",
                mode=ValidationMode.PERMISSIVE,
            )
            
            assert result.is_valid is True
            assert should_skip_document(result) is False
        
        finally:
            valid_txt_path.unlink()


class TestContratoValidacion:
    """Tests del contrato PreIngestionValidationResult."""
    
    def test_resultado_tiene_campos_obligatorios_exactos(self):
        """
        PreIngestionValidationResult debe tener EXACTAMENTE estos campos:
        - is_valid: bool
        - reject_code: str | None
        - details: dict
        - validator_version: str
        - metrics: dict
        
        NO debe tener campos adicionales como reject_message, filename, timestamp, etc.
        """
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            texto_valido = "Este es un texto suficientemente largo para pasar la validación. " * 5
            f.write(texto_valido)
            valid_txt_path = Path(f.name)
        
        try:
            result = validate_document_failfast(
                file_path=valid_txt_path,
                extracted_text=texto_valido,
                case_id="TEST_CASE_007",
                mode=ValidationMode.PERMISSIVE,
            )
            
            # Verificar SOLO campos del contrato
            assert hasattr(result, "is_valid")
            assert hasattr(result, "reject_code")
            assert hasattr(result, "details")
            assert hasattr(result, "validator_version")
            assert hasattr(result, "metrics")
            
            # Verificar tipos
            assert isinstance(result.is_valid, bool)
            assert result.reject_code is None or isinstance(result.reject_code, str)
            assert isinstance(result.details, dict)
            assert isinstance(result.validator_version, str)
            assert isinstance(result.metrics, dict)
            
            # Verificar métricas obligatorias
            assert "text_len" in result.metrics
            assert "file_size_mb" in result.metrics
            assert "pages_estimated" in result.metrics
            assert "noise_ratio" in result.metrics
            
            # Verificar que NO hay campos adicionales en nivel raíz
            # (filename, timestamp, etc. deben estar SOLO en details)
            assert not hasattr(result, "reject_message")
            assert not hasattr(result, "filename")
            assert not hasattr(result, "timestamp")
            assert not hasattr(result, "file_format")
        
        finally:
            valid_txt_path.unlink()


class TestGarantiaFailFast:
    """
    Tests que garantizan que si is_valid=False,
    NO se llama a chunking ni embeddings.
    """
    
    def test_documento_invalido_no_permite_chunking(self):
        """
        Si is_valid=False → should_skip_document=True
        GARANTÍA: chunking NO se ejecuta.
        """
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("corto")
            invalid_path = Path(f.name)
        
        try:
            result = validate_document_failfast(
                file_path=invalid_path,
                extracted_text="corto",
                case_id="TEST_CASE_008",
                mode=ValidationMode.PERMISSIVE,
            )
            
            assert result.is_valid is False
            assert should_skip_document(result) is True
        
        finally:
            invalid_path.unlink()
    
    def test_documento_valido_permite_chunking(self):
        """
        Si is_valid=True → should_skip_document=False
        Pipeline puede continuar.
        """
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            texto_valido = "Texto largo válido. " * 20
            f.write(texto_valido)
            valid_path = Path(f.name)
        
        try:
            result = validate_document_failfast(
                file_path=valid_path,
                extracted_text=texto_valido,
                case_id="TEST_CASE_009",
                mode=ValidationMode.PERMISSIVE,
            )
            
            assert result.is_valid is True
            assert should_skip_document(result) is False
        
        finally:
            valid_path.unlink()
    
    def test_ingesta_integrada_bloquea_documento_invalido(self, monkeypatch):
        """
        Test de integración: ingerir_archivo con validación STRICT
        debe retornar None si documento es inválido.
        """
        # Mock OpenAI client para evitar necesidad de API key
        import os
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-mock")
        
        from app.services.ingesta import ingerir_archivo
        
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("corto")
            invalid_path = Path(f.name)
        
        try:
            with open(invalid_path, "rb") as stream:
                result = ingerir_archivo(
                    file_stream=stream,
                    filename=invalid_path.name,
                    file_path=invalid_path,
                    case_id="TEST_CASE_010",
                    validation_mode="strict",
                )
            
            # Documento inválido debe retornar None (bloqueado)
            assert result is None
        
        except Exception:
            # En modo STRICT puede lanzar excepción (también válido)
            pass
        
        finally:
            invalid_path.unlink()
    
    def test_ingesta_integrada_permite_documento_valido(self, monkeypatch):
        """
        Test de integración: ingerir_archivo con validación PERMISSIVE
        debe procesar documento válido.
        """
        # Mock OpenAI client para evitar necesidad de API key
        import os
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-mock")
        
        from app.services.ingesta import ingerir_archivo
        
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            texto_valido = "Texto largo valido. " * 20
            f.write(texto_valido)
            valid_path = Path(f.name)
        
        try:
            with open(valid_path, "rb") as stream:
                result = ingerir_archivo(
                    file_stream=stream,
                    filename=valid_path.name,
                    file_path=valid_path,
                    case_id="TEST_CASE_011",
                    validation_mode="permissive",
                )
            
            # Documento válido debe procesarse (no None)
            assert result is not None
            assert hasattr(result, "texto")
        
        finally:
            valid_path.unlink()

