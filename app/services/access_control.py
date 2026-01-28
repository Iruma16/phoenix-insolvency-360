"""
Control de acceso defensivo por case_id (HARDENING OPCIONAL).

⚠️ IMPORTANTE - MODO STRICT EN PRODUCCIÓN:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Por defecto: strict=True (OBLIGATORIO en producción)

El modo non-strict (strict=False) SOLO debe usarse en:
- Entornos de desarrollo (ENVIRONMENT=dev)
- Tests automatizados (ENVIRONMENT=test)

En producción, non-strict es un RIESGO DE SEGURIDAD.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Capa de validación adicional sin modificar lógica core.
"""
import os
from typing import Any, Optional, List
import sys


class AccessViolationError(Exception):
    """Error de violación de acceso cross-case."""
    pass


def _check_strict_mode_safe(strict: bool, operation: str) -> None:
    """
    Verifica que modo non-strict NO se use en producción.
    
    Emite WARNING si non-strict en producción.
    """
    if not strict:
        env = os.getenv("ENVIRONMENT", "dev").lower()
        
        if env in ["production", "prod"]:
            # ⚠️ CRÍTICO: non-strict en producción
            warning = (
                f"[SECURITY] Access control running in NON-STRICT mode for operation={operation}. "
                f"This is UNSAFE in production. Set strict=True or ENVIRONMENT=dev/test."
            )
            print(warning, file=sys.stderr)
            print(f"[CERT] UNSAFE_NON_STRICT_MODE operation={operation} environment={env}")


def assert_case_id_match(
    operation: str,
    expected_case_id: str,
    actual_value: Any,
    strict: bool = True
) -> None:
    """
    Assert defensivo de case_id.
    
    Args:
        operation: Nombre de la operación (para logging)
        expected_case_id: case_id esperado
        actual_value: Objeto con .case_id o diccionario con 'case_id'
        strict: Si True, lanza excepción; si False, solo loguea
                ⚠️ strict=False NO debe usarse en producción
    """
    # Verificar modo strict seguro
    _check_strict_mode_safe(strict, operation)
    
    actual_case_id = None
    
    # Extraer case_id del valor
    if hasattr(actual_value, "case_id"):
        actual_case_id = actual_value.case_id
    elif isinstance(actual_value, dict) and "case_id" in actual_value:
        actual_case_id = actual_value["case_id"]
    else:
        # No tiene case_id, puede ser válido en algunos contextos
        return
    
    if actual_case_id != expected_case_id:
        error_msg = (
            f"[SECURITY] CROSS_CASE_ACCESS_ATTEMPT: "
            f"operation={operation} "
            f"expected_case_id={expected_case_id} "
            f"actual_case_id={actual_case_id}"
        )
        
        print(error_msg, file=sys.stderr)
        print(f"[CERT] ACCESS_VIOLATION_DETECTED operation={operation}")
        
        if strict:
            raise AccessViolationError(error_msg)


def validate_chunk_belongs_to_case(
    chunk: Any,
    case_id: str,
    strict: bool = True
) -> bool:
    """
    Valida que un chunk pertenezca al case_id esperado.
    
    Args:
        strict: ⚠️ strict=False NO debe usarse en producción
    
    Returns:
        True si es válido, False si no (en modo non-strict)
    
    Raises:
        AccessViolationError si strict=True y no coincide
    """
    # Verificar modo strict seguro
    _check_strict_mode_safe(strict, "validate_chunk")
    
    if not chunk:
        return True  # Chunk None es válido (puede no existir)
    
    chunk_case_id = getattr(chunk, "case_id", None)
    
    if chunk_case_id and chunk_case_id != case_id:
        error_msg = (
            f"[SECURITY] Chunk {getattr(chunk, 'chunk_id', 'unknown')} "
            f"pertenece a case {chunk_case_id}, esperado {case_id}"
        )
        
        print(error_msg, file=sys.stderr)
        print(f"[CERT] CHUNK_CASE_ID_MISMATCH chunk={getattr(chunk, 'chunk_id', 'unknown')}")
        
        if strict:
            raise AccessViolationError(error_msg)
        return False
    
    return True


def validate_document_belongs_to_case(
    document: Any,
    case_id: str,
    strict: bool = True
) -> bool:
    """
    Valida que un documento pertenezca al case_id esperado.
    
    Args:
        strict: ⚠️ strict=False NO debe usarse en producción
    """
    # Verificar modo strict seguro
    _check_strict_mode_safe(strict, "validate_document")
    
    if not document:
        return True
    
    doc_case_id = getattr(document, "case_id", None)
    
    if doc_case_id and doc_case_id != case_id:
        error_msg = (
            f"[SECURITY] Document {getattr(document, 'document_id', 'unknown')} "
            f"pertenece a case {doc_case_id}, esperado {case_id}"
        )
        
        print(error_msg, file=sys.stderr)
        print(f"[CERT] DOCUMENT_CASE_ID_MISMATCH doc={getattr(document, 'document_id', 'unknown')}")
        
        if strict:
            raise AccessViolationError(error_msg)
        return False
    
    return True


def log_access_attempt(
    operation: str,
    case_id: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    success: bool = True
) -> None:
    """
    Loguea intento de acceso para auditoría.
    
    Args:
        operation: Tipo de operación (READ, WRITE, DELETE)
        case_id: case_id del contexto
        resource_type: Tipo de recurso (document, chunk, decision_record)
        resource_id: ID del recurso específico
        success: Si el acceso fue exitoso
    """
    status = "SUCCESS" if success else "DENIED"
    
    log_line = (
        f"[AUDIT] ACCESS_LOG "
        f"operation={operation} "
        f"case_id={case_id} "
        f"resource_type={resource_type} "
        f"resource_id={resource_id or 'N/A'} "
        f"status={status}"
    )
    
    print(log_line)


def filter_results_by_case_id(
    results: List[Any],
    case_id: str,
    strict: bool = False
) -> List[Any]:
    """
    Filtra defensivamente resultados para asegurar case_id.
    
    Args:
        results: Lista de objetos con .case_id
        case_id: case_id esperado
        strict: Si True, loguea violaciones detectadas
    
    Returns:
        Lista filtrada solo con objetos del case_id correcto
    """
    filtered = []
    violations = 0
    
    for item in results:
        item_case_id = getattr(item, "case_id", None)
        
        if item_case_id is None:
            # Sin case_id, permitir por defecto
            filtered.append(item)
        elif item_case_id == case_id:
            # case_id correcto
            filtered.append(item)
        else:
            # case_id incorrecto - violación detectada
            violations += 1
            if strict:
                print(
                    f"[SECURITY] Filtered out item with case_id={item_case_id} "
                    f"(expected {case_id})",
                    file=sys.stderr
                )
    
    if violations > 0:
        print(f"[CERT] CROSS_CASE_ITEMS_FILTERED count={violations} expected_case_id={case_id}")
    
    return filtered

