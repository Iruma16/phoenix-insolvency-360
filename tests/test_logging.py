"""
Tests para el sistema de logging estructurado.
"""
import json

from app.core.logger import StructuredLogger, get_logger


def test_logger_creation():
    """Test: Crear logger estructurado."""
    logger = get_logger("test.logger")

    assert logger is not None
    assert isinstance(logger, StructuredLogger)


def test_info_logging(tmp_path):
    """Test: Log nivel INFO."""
    log_file = tmp_path / "test.log"
    logger = StructuredLogger("test", log_file)

    logger.info("Test message", case_id="CASE_001", action="test")

    assert log_file.exists()
    with open(log_file) as f:
        log_line = f.read()
        log_data = json.loads(log_line)

    assert log_data["level"] == "INFO"
    assert log_data["message"] == "Test message"
    assert log_data["case_id"] == "CASE_001"
    assert log_data["action"] == "test"
    assert "timestamp" in log_data


def test_warning_logging(tmp_path):
    """Test: Log nivel WARNING."""
    log_file = tmp_path / "test.log"
    logger = StructuredLogger("test", log_file)

    logger.warning("Warning message", case_id="CASE_002", action="warning_test")

    with open(log_file) as f:
        log_data = json.loads(f.read())

    assert log_data["level"] == "WARNING"
    assert log_data["message"] == "Warning message"


def test_error_logging(tmp_path):
    """Test: Log nivel ERROR con excepción."""
    log_file = tmp_path / "test.log"
    logger = StructuredLogger("test", log_file)

    error = ValueError("Test error")
    logger.error("Error occurred", case_id="CASE_003", action="error_test", error=error)

    with open(log_file) as f:
        log_data = json.loads(f.read())

    assert log_data["level"] == "ERROR"
    assert log_data["message"] == "Error occurred"
    assert log_data["error_type"] == "ValueError"
    assert log_data["error_message"] == "Test error"


def test_extra_fields(tmp_path):
    """Test: Campos extras en logs."""
    log_file = tmp_path / "test.log"
    logger = StructuredLogger("test", log_file)

    logger.info(
        "Test with extras", case_id="CASE_004", action="extra_test", duration_ms=150, user="analyst"
    )

    with open(log_file) as f:
        log_data = json.loads(f.read())

    assert log_data["duration_ms"] == 150
    assert log_data["user"] == "analyst"


def test_json_format(tmp_path):
    """Test: Formato JSON válido."""
    log_file = tmp_path / "test.log"
    logger = StructuredLogger("test", log_file)

    logger.info("Test JSON", case_id="CASE_005", action="json_test")

    with open(log_file) as f:
        content = f.read()

    # Debe ser JSON válido
    log_data = json.loads(content)
    assert isinstance(log_data, dict)
    assert "timestamp" in log_data
    assert "level" in log_data
    assert "message" in log_data
