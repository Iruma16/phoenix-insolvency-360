"""
Servicio base para toda la aplicación.

Proporciona funcionalidad común a todos los servicios:
- Logging estructurado
- Manejo de excepciones
- Acceso a base de datos
"""
from typing import Optional
from sqlalchemy.orm import Session

from app.core.logger import StructuredLogger, get_logger
from app.core.exceptions import PhoenixException


class BaseService:
    """
    Clase base para todos los servicios.
    
    Los servicios encapsulan la lógica de negocio y orquestan
    operaciones complejas entre múltiples componentes.
    """
    
    def __init__(
        self,
        db: Session,
        logger: Optional[StructuredLogger] = None
    ):
        """
        Inicializa el servicio base.
        
        Args:
            db: Sesión de base de datos
            logger: Logger estructurado (opcional)
        """
        self.db = db
        self.logger = logger or get_logger()
    
    def _log_info(self, message: str, **kwargs):
        """Log nivel INFO."""
        self.logger.info(message, **kwargs)
    
    def _log_warning(self, message: str, **kwargs):
        """Log nivel WARNING."""
        self.logger.warning(message, **kwargs)
    
    def _log_error(self, message: str, error: Optional[Exception] = None, **kwargs):
        """Log nivel ERROR."""
        self.logger.error(message, error=error, **kwargs)
    
    def _handle_exception(
        self,
        error: Exception,
        context: str,
        case_id: Optional[str] = None
    ) -> PhoenixException:
        """
        Maneja una excepción de manera consistente.
        
        Args:
            error: Excepción original
            context: Contexto donde ocurrió
            case_id: ID del caso (si aplica)
        
        Returns:
            PhoenixException wrapeada
        """
        # Si ya es PhoenixException, retornar tal cual
        if isinstance(error, PhoenixException):
            self._log_error(
                f"Phoenix exception in {context}",
                error=error,
                case_id=case_id
            )
            return error
        
        # Wrap en PhoenixException genérica
        self._log_error(
            f"Unexpected error in {context}",
            error=error,
            case_id=case_id
        )
        
        from app.core.exceptions import PhoenixException
        return PhoenixException(
            code="INTERNAL_ERROR",
            message=f"Error interno en {context}",
            details={"context": context},
            original_error=error
        )

