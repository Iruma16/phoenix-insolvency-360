"""
Sistema de excepciones estandarizado para Phoenix Legal.

Todas las excepciones del sistema heredan de PhoenixException y siguen
un formato consistente con:
- Código de error único
- Mensaje descriptivo
- Detalles adicionales (dict)
- Severity level

Esto facilita:
- Logging estructurado
- Manejo de errores en API
- Debugging en producción
- Métricas de errores
"""
from typing import Dict, Any, Optional, Literal
from enum import Enum


class ErrorSeverity(str, Enum):
    """Niveles de severidad para errores."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PhoenixException(Exception):
    """
    Excepción base del sistema Phoenix Legal.
    
    Todas las excepciones custom deben heredar de esta clase.
    """
    
    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        original_error: Optional[Exception] = None
    ):
        """
        Inicializa una excepción Phoenix.
        
        Args:
            code: Código único del error (ej: "RAG_QUERY_FAILED")
            message: Mensaje descriptivo para humanos
            details: Detalles adicionales (dict)
            severity: Nivel de severidad
            original_error: Excepción original si es un wrap
        """
        self.code = code
        self.message = message
        self.details = details or {}
        self.severity = severity
        self.original_error = original_error
        
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convierte la excepción a diccionario (para API/logging).
        
        Returns:
            Dict con información de la excepción
        """
        result = {
            "error_code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "details": self.details
        }
        
        if self.original_error:
            result["original_error"] = {
                "type": type(self.original_error).__name__,
                "message": str(self.original_error)
            }
        
        return result
    
    def __str__(self) -> str:
        """String representation."""
        base = f"[{self.code}] {self.message}"
        if self.details:
            base += f" | Details: {self.details}"
        return base


# =========================================================
# EXCEPCIONES DE CONFIGURACIÓN
# =========================================================

class ConfigurationException(PhoenixException):
    """Error de configuración del sistema."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            code="CONFIG_ERROR",
            message=message,
            severity=ErrorSeverity.CRITICAL,
            **kwargs
        )


class MissingConfigException(ConfigurationException):
    """Variable de configuración requerida no encontrada."""
    
    def __init__(self, config_key: str, **kwargs):
        super().__init__(
            message=f"Variable de configuración requerida no encontrada: {config_key}",
            details={"config_key": config_key},
            **kwargs
        )


# =========================================================
# EXCEPCIONES DE BASE DE DATOS
# =========================================================

class DatabaseException(PhoenixException):
    """Error relacionado con base de datos."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            code="DATABASE_ERROR",
            message=message,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )


class CaseNotFoundException(DatabaseException):
    """Caso no encontrado en base de datos."""
    
    def __init__(self, case_id: str, **kwargs):
        super().__init__(
            message=f"Caso no encontrado: {case_id}",
            details={"case_id": case_id},
            **kwargs
        )
        self.code = "CASE_NOT_FOUND"


class DocumentNotFoundException(DatabaseException):
    """Documento no encontrado."""
    
    def __init__(self, document_id: str, **kwargs):
        super().__init__(
            message=f"Documento no encontrado: {document_id}",
            details={"document_id": document_id},
            **kwargs
        )
        self.code = "DOCUMENT_NOT_FOUND"


class DuplicateCaseException(DatabaseException):
    """Intento de crear caso duplicado."""
    
    def __init__(self, case_id: str, **kwargs):
        super().__init__(
            message=f"Ya existe un caso con ID: {case_id}",
            details={"case_id": case_id},
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )
        self.code = "DUPLICATE_CASE"


# =========================================================
# EXCEPCIONES DE RAG (RETRIEVAL)
# =========================================================

class RAGException(PhoenixException):
    """Error relacionado con RAG (Retrieval Augmented Generation)."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            code="RAG_ERROR",
            message=message,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


class RAGQueryFailedException(RAGException):
    """Fallo al consultar RAG."""
    
    def __init__(self, case_id: str, query: str, **kwargs):
        super().__init__(
            message=f"No se pudo consultar RAG para caso {case_id}",
            details={"case_id": case_id, "query": query[:100]},
            **kwargs
        )
        self.code = "RAG_QUERY_FAILED"


class RAGNoResultsException(RAGException):
    """No se encontraron resultados en RAG."""
    
    def __init__(self, query: str, **kwargs):
        super().__init__(
            message="No se encontraron resultados relevantes en RAG",
            details={"query": query[:100]},
            severity=ErrorSeverity.LOW,
            **kwargs
        )
        self.code = "RAG_NO_RESULTS"


class RAGWeakConfidenceException(RAGException):
    """Resultados de RAG con baja confianza."""
    
    def __init__(self, best_score: float, threshold: float, **kwargs):
        super().__init__(
            message=f"Resultados RAG con baja confianza: score={best_score:.2f} > threshold={threshold:.2f}",
            details={"best_score": best_score, "threshold": threshold},
            severity=ErrorSeverity.LOW,
            **kwargs
        )
        self.code = "RAG_WEAK_CONFIDENCE"


class VectorstoreNotFoundException(RAGException):
    """Vectorstore no encontrado."""
    
    def __init__(self, path: str, **kwargs):
        super().__init__(
            message=f"Vectorstore no encontrado en: {path}",
            details={"path": path},
            **kwargs
        )
        self.code = "VECTORSTORE_NOT_FOUND"


# =========================================================
# EXCEPCIONES DE LLM
# =========================================================

class LLMException(PhoenixException):
    """Error relacionado con LLM."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            code="LLM_ERROR",
            message=message,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


class LLMNotAvailableException(LLMException):
    """LLM no disponible (sin API key o deshabilitado)."""
    
    def __init__(self, reason: str = "No API key", **kwargs):
        super().__init__(
            message=f"LLM no disponible: {reason}",
            details={"reason": reason},
            severity=ErrorSeverity.LOW,
            **kwargs
        )
        self.code = "LLM_NOT_AVAILABLE"


class LLMTimeoutException(LLMException):
    """Timeout en llamada a LLM."""
    
    def __init__(self, timeout_seconds: int, **kwargs):
        super().__init__(
            message=f"Timeout en llamada LLM después de {timeout_seconds}s",
            details={"timeout_seconds": timeout_seconds},
            **kwargs
        )
        self.code = "LLM_TIMEOUT"


class LLMRateLimitException(LLMException):
    """Rate limit alcanzado en API de LLM."""
    
    def __init__(self, retry_after: Optional[int] = None, **kwargs):
        super().__init__(
            message="Rate limit alcanzado en API de LLM",
            details={"retry_after": retry_after},
            **kwargs
        )
        self.code = "LLM_RATE_LIMIT"


class LLMInvalidResponseException(LLMException):
    """Respuesta inválida de LLM."""
    
    def __init__(self, reason: str, **kwargs):
        super().__init__(
            message=f"Respuesta inválida de LLM: {reason}",
            details={"reason": reason},
            **kwargs
        )
        self.code = "LLM_INVALID_RESPONSE"


# =========================================================
# EXCEPCIONES DE PROCESAMIENTO DE DOCUMENTOS
# =========================================================

class DocumentProcessingException(PhoenixException):
    """Error al procesar documento."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            code="DOCUMENT_PROCESSING_ERROR",
            message=message,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


class DocumentParsingException(DocumentProcessingException):
    """Error al parsear documento."""
    
    def __init__(self, filename: str, reason: str, **kwargs):
        super().__init__(
            message=f"No se pudo parsear documento {filename}: {reason}",
            details={"filename": filename, "reason": reason},
            **kwargs
        )
        self.code = "DOCUMENT_PARSING_FAILED"


class UnsupportedDocumentTypeException(DocumentProcessingException):
    """Tipo de documento no soportado."""
    
    def __init__(self, filename: str, file_type: str, **kwargs):
        super().__init__(
            message=f"Tipo de documento no soportado: {file_type}",
            details={"filename": filename, "file_type": file_type},
            severity=ErrorSeverity.LOW,
            **kwargs
        )
        self.code = "UNSUPPORTED_DOCUMENT_TYPE"


# =========================================================
# EXCEPCIONES DE ANÁLISIS LEGAL
# =========================================================

class LegalAnalysisException(PhoenixException):
    """Error en análisis legal."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            code="LEGAL_ANALYSIS_ERROR",
            message=message,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


class InsufficientEvidenceException(LegalAnalysisException):
    """Evidencia insuficiente para análisis."""
    
    def __init__(self, reason: str, **kwargs):
        super().__init__(
            message=f"Evidencia insuficiente para análisis: {reason}",
            details={"reason": reason},
            severity=ErrorSeverity.LOW,
            **kwargs
        )
        self.code = "INSUFFICIENT_EVIDENCE"


class RuleEngineException(LegalAnalysisException):
    """Error en motor de reglas."""
    
    def __init__(self, rule_id: str, reason: str, **kwargs):
        super().__init__(
            message=f"Error en regla {rule_id}: {reason}",
            details={"rule_id": rule_id, "reason": reason},
            **kwargs
        )
        self.code = "RULE_ENGINE_ERROR"


# =========================================================
# EXCEPCIONES DE GENERACIÓN DE REPORTES
# =========================================================

class ReportGenerationException(PhoenixException):
    """Error al generar reporte."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            code="REPORT_GENERATION_ERROR",
            message=message,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


class ReportNotFoundException(ReportGenerationException):
    """Reporte no encontrado."""
    
    def __init__(self, case_id: str, **kwargs):
        super().__init__(
            message=f"No se encontró reporte para caso: {case_id}",
            details={"case_id": case_id},
            severity=ErrorSeverity.LOW,
            **kwargs
        )
        self.code = "REPORT_NOT_FOUND"


# =========================================================
# EXCEPCIONES DE AUTENTICACIÓN Y AUTORIZACIÓN
# =========================================================

class AuthenticationException(PhoenixException):
    """Error de autenticación."""
    
    def __init__(self, message: str = "Autenticación fallida", **kwargs):
        super().__init__(
            code="AUTH_ERROR",
            message=message,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


class InvalidTokenException(AuthenticationException):
    """Token JWT inválido."""
    
    def __init__(self, reason: str = "Token inválido", **kwargs):
        super().__init__(
            message=f"Token inválido: {reason}",
            details={"reason": reason},
            **kwargs
        )
        self.code = "INVALID_TOKEN"


class TokenExpiredException(AuthenticationException):
    """Token JWT expirado."""
    
    def __init__(self, **kwargs):
        super().__init__(
            message="Token expirado",
            **kwargs
        )
        self.code = "TOKEN_EXPIRED"


class InsufficientPermissionsException(PhoenixException):
    """Permisos insuficientes."""
    
    def __init__(self, required_permission: str, **kwargs):
        super().__init__(
            code="INSUFFICIENT_PERMISSIONS",
            message=f"Permisos insuficientes. Se requiere: {required_permission}",
            details={"required_permission": required_permission},
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


# =========================================================
# EXCEPCIONES DE VALIDACIÓN
# =========================================================

class ValidationException(PhoenixException):
    """Error de validación de datos."""
    
    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        details = kwargs.get("details", {})
        if field:
            details["field"] = field
        
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            details=details,
            severity=ErrorSeverity.LOW,
            **kwargs
        )


# =========================================================
# EXCEPCIONES DE FINOPS
# =========================================================

class FinOpsBypassError(PhoenixException):
    """
    Excepción cuando se intenta bypass de FinOps entry points.
    
    Definida en FASE 1 para enforcement futuro.
    GATE HARD: Esta excepción indica violación de ley técnica.
    
    PROHIBIDO llamar proveedores directamente fuera de:
    - run_embeddings()
    - run_retrieve()
    - run_llm_call()
    """
    
    def __init__(self, operation: str, reason: str, **kwargs):
        super().__init__(
            code="FINOPS_BYPASS",
            message=f"Bypass de FinOps detectado: operation={operation}, reason={reason}",
            details={"operation": operation, "reason": reason},
            severity=ErrorSeverity.CRITICAL,
            **kwargs
        )


# =========================================================
# EXCEPCIONES DE CONTRATO DE CHUNK (ENDURECIMIENTO #3)
# =========================================================

class ChunkContractViolationError(PhoenixException):
    """
    Excepción cuando se viola el contrato obligatorio de DocumentChunk.
    
    REGLAS DURAS:
    - No puede existir DocumentChunk sin location
    - char_start < char_end
    - page_start <= page_end si ambos existen
    - extraction_method SIEMPRE informado
    """
    
    def __init__(self, rule_violated: str, chunk_id: Optional[str] = None, **kwargs):
        message = f"Violación del contrato de chunk: {rule_violated}"
        details = {"rule_violated": rule_violated}
        if chunk_id:
            details["chunk_id"] = chunk_id
        
        super().__init__(
            code="CHUNK_CONTRACT_VIOLATION",
            message=message,
            details=details,
            severity=ErrorSeverity.CRITICAL,
            **kwargs
        )


class DocumentValidationError(PhoenixException):
    """
    Excepción FAIL-FAST cuando un documento es rechazado en validación pre-ingesta.
    
    Se lanza en modo STRICT para bloquear todo el pipeline.
    En modo PERMISSIVE, se registra pero no bloquea otros documentos.
    
    ENDURECIMIENTO #2 (FASE 3)
    """
    
    def __init__(self, reject_code: str, reason: str, filename: str, **kwargs):
        message = f"Documento RECHAZADO en validación pre-ingesta: {filename}"
        details = {
            "reject_code": reject_code,
            "reason": reason,
            "filename": filename
        }
        
        super().__init__(
            code="DOCUMENT_VALIDATION_FAILED",
            message=message,
            details=details,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def wrap_exception(
    original_error: Exception,
    phoenix_exception_class: type,
    **kwargs
) -> PhoenixException:
    """
    Envuelve una excepción genérica en una PhoenixException.
    
    Args:
        original_error: Excepción original
        phoenix_exception_class: Clase de PhoenixException a usar
        **kwargs: Argumentos adicionales para la excepción
    
    Returns:
        PhoenixException: Excepción wrapeada
    """
    if isinstance(original_error, PhoenixException):
        return original_error
    
    return phoenix_exception_class(
        original_error=original_error,
        **kwargs
    )

