"""
Tests para HARDENING DE PRODUCCIÓN (PUNTO 8 avanzado).

Verifica capacidades opcionales de:
- Retención avanzada con TTL
- Control de acceso defensivo
- Auditoría de accesos
"""
import pytest
import sys
from io import StringIO
from unittest.mock import MagicMock
import time


def capture_stdout(func):
    """Captura stdout."""
    def wrapper(*args, **kwargs):
        old_stdout = sys.stdout
        sys.stdout = new_stdout = StringIO()
        try:
            result = func(*args, **kwargs)
            output = new_stdout.getvalue()
            return result, output
        finally:
            sys.stdout = old_stdout
    return wrapper


def test_retention_backend_selection():
    """Test 1: Selección de backend de retención."""
    from app.services.retention_policy import get_retention_backend, RetentionConfig
    
    @capture_stdout
    def get_backend():
        config = RetentionConfig(backend_type="in-memory", ttl_seconds=3600)
        return get_retention_backend(config)
    
    backend, output = get_backend()
    
    # CERT: Verificar selección de backend
    assert "[CERT] RETENTION_BACKEND_SELECTED backend=in-memory" in output
    assert "ttl=3600" in output
    
    print("✅ PASSED: test_retention_backend_selection")


def test_retention_ttl_expiration():
    """Test 2: TTL y expiración de registros."""
    from app.services.retention_policy import InMemoryRetentionBackend
    
    backend = InMemoryRetentionBackend()
    
    # Almacenar con TTL de 1 segundo
    backend.store("key1", "value1", ttl=1)
    
    # Inmediatamente debe estar disponible
    assert backend.get("key1") == "value1"
    
    # Esperar expiración
    time.sleep(1.1)
    
    # Ahora debe estar expirado
    assert backend.get("key1") is None
    
    print("✅ PASSED: test_retention_ttl_expiration")


def test_retention_delete_by_case_id():
    """Test 3: Borrado por case_id."""
    from app.services.retention_policy import InMemoryRetentionBackend
    
    backend = InMemoryRetentionBackend()
    
    # Crear mock records para diferentes casos
    record_a1 = MagicMock()
    record_a1.case_id = "case_A"
    record_a1.request_id = "req_A1"
    
    record_a2 = MagicMock()
    record_a2.case_id = "case_A"
    record_a2.request_id = "req_A2"
    
    record_b = MagicMock()
    record_b.case_id = "case_B"
    record_b.request_id = "req_B"
    
    backend.store("req_A1", record_a1)
    backend.store("req_A2", record_a2)
    backend.store("req_B", record_b)
    
    # Borrar case_A
    deleted_count = backend.delete_by_case_id("case_A")
    
    # CERT: Verificar que se borraron 2 registros
    assert deleted_count == 2
    
    # CERT: case_A debe estar borrado
    assert backend.get("req_A1") is None
    assert backend.get("req_A2") is None
    
    # CERT: case_B NO debe estar afectado
    assert backend.get("req_B") is not None
    
    print("✅ PASSED: test_retention_delete_by_case_id")


def test_retention_cleanup_expired():
    """Test 4: Limpieza automática de expirados."""
    from app.services.retention_policy import InMemoryRetentionBackend
    
    backend = InMemoryRetentionBackend()
    
    # Almacenar varios con diferentes TTL
    backend.store("expired1", "val1", ttl=1)
    backend.store("expired2", "val2", ttl=1)
    backend.store("valid", "val3", ttl=10)
    
    # Esperar que expiren
    time.sleep(1.1)
    
    # Limpiar expirados
    cleaned = backend.cleanup_expired()
    
    # CERT: Debe haber limpiado 2
    assert cleaned == 2
    
    # CERT: Los expirados no deben estar
    assert backend.get("expired1") is None
    assert backend.get("expired2") is None
    
    # CERT: El válido sí
    assert backend.get("valid") is not None
    
    print("✅ PASSED: test_retention_cleanup_expired")


def test_access_control_case_id_match():
    """Test 5: Validación de case_id en control de acceso."""
    from app.services.access_control import assert_case_id_match, AccessViolationError
    
    # Mock objeto con case_id correcto
    obj_correct = MagicMock()
    obj_correct.case_id = "case_A"
    
    # NO debe lanzar excepción
    assert_case_id_match("READ", "case_A", obj_correct, strict=True)
    
    # Mock objeto con case_id INCORRECTO
    obj_wrong = MagicMock()
    obj_wrong.case_id = "case_B"
    
    # DEBE lanzar excepción
    with pytest.raises(AccessViolationError):
        assert_case_id_match("READ", "case_A", obj_wrong, strict=True)
    
    print("✅ PASSED: test_access_control_case_id_match")


def test_access_control_chunk_validation():
    """Test 6: Validación de chunks pertenecientes a case."""
    from app.services.access_control import validate_chunk_belongs_to_case, AccessViolationError
    
    # Chunk correcto
    chunk_ok = MagicMock()
    chunk_ok.case_id = "case_A"
    chunk_ok.chunk_id = "chunk_001"
    
    assert validate_chunk_belongs_to_case(chunk_ok, "case_A", strict=True) is True
    
    # Chunk incorrecto
    chunk_wrong = MagicMock()
    chunk_wrong.case_id = "case_B"
    chunk_wrong.chunk_id = "chunk_002"
    
    with pytest.raises(AccessViolationError):
        validate_chunk_belongs_to_case(chunk_wrong, "case_A", strict=True)
    
    # Modo non-strict NO lanza excepción
    assert validate_chunk_belongs_to_case(chunk_wrong, "case_A", strict=False) is False
    
    print("✅ PASSED: test_access_control_chunk_validation")


def test_access_control_audit_logging():
    """Test 7: Logging de auditoría de accesos."""
    from app.services.access_control import log_access_attempt
    
    @capture_stdout
    def log():
        log_access_attempt(
            operation="READ",
            case_id="case_A",
            resource_type="document",
            resource_id="doc_001",
            success=True
        )
    
    _, output = log()
    
    # CERT: Verificar formato de audit log
    assert "[AUDIT] ACCESS_LOG" in output
    assert "operation=READ" in output
    assert "case_id=case_A" in output
    assert "resource_type=document" in output
    assert "resource_id=doc_001" in output
    assert "status=SUCCESS" in output
    
    print("✅ PASSED: test_access_control_audit_logging")


def test_access_control_filter_cross_case():
    """Test 8: Filtrado defensivo de resultados cross-case."""
    from app.services.access_control import filter_results_by_case_id
    
    # Crear lista mixta
    item_a1 = MagicMock()
    item_a1.case_id = "case_A"
    
    item_a2 = MagicMock()
    item_a2.case_id = "case_A"
    
    item_b = MagicMock()
    item_b.case_id = "case_B"  # Intruso
    
    mixed_results = [item_a1, item_b, item_a2]
    
    @capture_stdout
    def filter_items():
        return filter_results_by_case_id(mixed_results, "case_A", strict=True)
    
    filtered, output = filter_items()
    
    # CERT: Solo 2 items deben quedar (los de case_A)
    assert len(filtered) == 2
    assert item_a1 in filtered
    assert item_a2 in filtered
    assert item_b not in filtered
    
    # CERT: Debe haber logueado la filtración
    assert "[CERT] CROSS_CASE_ITEMS_FILTERED count=1" in output
    
    print("✅ PASSED: test_access_control_filter_cross_case")


def test_hardening_backward_compatible():
    """Test 9: Hardening NO rompe compatibilidad."""
    # Verificar que módulos nuevos son opcionales
    try:
        from app.services.retention_policy import get_retention_backend
        from app.services.access_control import assert_case_id_match
        
        # Deben importar sin error
        assert get_retention_backend is not None
        assert assert_case_id_match is not None
        
    except ImportError as e:
        pytest.fail(f"Hardening modules no importables: {e}")
    
    print("✅ PASSED: test_hardening_backward_compatible")

