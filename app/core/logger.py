"""
Sistema de logging estructurado para Phoenix Legal.

Formato JSON pensado para auditoría legal y trazabilidad.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class StructuredLogger:
    """
    Logger estructurado con formato JSON para auditoría legal.

    Cada log incluye:
    - timestamp ISO8601
    - level (INFO/WARNING/ERROR)
    - case_id (si aplica)
    - action (tipo de acción)
    - message
    - extra_data (opcional)
    """

    def __init__(self, name: str, log_file: Optional[Path] = None):
        """
        Inicializa el logger estructurado.

        Args:
            name: Nombre del logger (ej: "phoenix.legal")
            log_file: Ruta al archivo de log (opcional)
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        self.logger.handlers = []  # Limpiar handlers existentes

        # Handler para consola
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(JsonFormatter())
        self.logger.addHandler(console_handler)

        # Handler para archivo (si se especifica)
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(JsonFormatter())
            self.logger.addHandler(file_handler)

    def info(
        self, message: str, case_id: Optional[str] = None, action: Optional[str] = None, **extra
    ):
        """Log nivel INFO."""
        self._log(logging.INFO, message, case_id, action, extra)

    def warning(
        self, message: str, case_id: Optional[str] = None, action: Optional[str] = None, **extra
    ):
        """Log nivel WARNING."""
        self._log(logging.WARNING, message, case_id, action, extra)

    def error(
        self,
        message: str,
        case_id: Optional[str] = None,
        action: Optional[str] = None,
        error: Optional[Exception] = None,
        **extra,
    ):
        """Log nivel ERROR."""
        if error:
            extra["error_type"] = type(error).__name__
            extra["error_message"] = str(error)
        self._log(logging.ERROR, message, case_id, action, extra)

    def _log(
        self,
        level: int,
        message: str,
        case_id: Optional[str],
        action: Optional[str],
        extra: dict[str, Any],
    ):
        """Método interno para logging."""
        log_data = {"case_id": case_id, "action": action, **extra}

        # Filtrar None values
        log_data = {k: v for k, v in log_data.items() if v is not None}

        self.logger.log(level, message, extra={"data": log_data})


class JsonFormatter(logging.Formatter):
    """Formatter que convierte logs a JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Formatea el record como JSON."""
        log_obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Añadir data extra si existe
        if hasattr(record, "data"):
            log_obj.update(record.data)

        # Añadir información de excepción si existe
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, ensure_ascii=False)


# Logger global para la aplicación
_default_logger: Optional[StructuredLogger] = None


def get_logger(name: str = "phoenix.legal", log_file: Optional[Path] = None) -> StructuredLogger:
    """
    Obtiene o crea el logger estructurado.

    Args:
        name: Nombre del logger
        log_file: Ruta al archivo de log

    Returns:
        Logger estructurado
    """
    global _default_logger

    if _default_logger is None:
        # Crear directorio de logs por defecto
        if log_file is None:
            log_file = Path("clients_data/logs/phoenix_legal.log")

        _default_logger = StructuredLogger(name, log_file)

    return _default_logger


# Atajos para uso directo
logger = get_logger()


def log_info(message: str, case_id: Optional[str] = None, action: Optional[str] = None, **extra):
    """Atajo para log INFO."""
    logger.info(message, case_id=case_id, action=action, **extra)


def log_warning(message: str, case_id: Optional[str] = None, action: Optional[str] = None, **extra):
    """Atajo para log WARNING."""
    logger.warning(message, case_id=case_id, action=action, **extra)


def log_error(
    message: str,
    case_id: Optional[str] = None,
    action: Optional[str] = None,
    error: Optional[Exception] = None,
    **extra,
):
    """Atajo para log ERROR."""
    logger.error(message, case_id=case_id, action=action, error=error, **extra)
