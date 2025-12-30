"""
Tests para el sistema de monitoreo.
"""
import pytest
import time

from app.core.monitoring import PerformanceMonitor, get_monitor


def test_monitor_creation():
    """Test: Crear monitor de rendimiento."""
    monitor = PerformanceMonitor()
    
    assert monitor is not None
    assert monitor.metrics.total_cases_analyzed == 0


def test_track_phase():
    """Test: Trackear tiempo de fase."""
    monitor = PerformanceMonitor()
    
    with monitor.track_phase("test_phase", case_id="CASE_001"):
        time.sleep(0.01)  # Simular trabajo
    
    metrics = monitor.get_metrics()
    assert "test_phase" in metrics["phase_times"]
    assert metrics["phase_times"]["test_phase"]["count"] == 1
    assert metrics["phase_times"]["test_phase"]["avg_ms"] > 0


def test_track_case_analysis():
    """Test: Trackear análisis completo de caso."""
    monitor = PerformanceMonitor()
    
    with monitor.track_case_analysis("CASE_TEST"):
        time.sleep(0.01)
    
    metrics = monitor.get_metrics()
    assert metrics["total_cases_analyzed"] == 1
    assert metrics["avg_execution_time_ms"] > 0


def test_track_llm_call():
    """Test: Trackear llamada LLM."""
    monitor = PerformanceMonitor()
    
    monitor.track_llm_call("auditor", case_id="CASE_001", success=True, duration_ms=150)
    
    metrics = monitor.get_metrics()
    assert metrics["llm"]["total_calls"] == 1
    assert metrics["llm"]["errors"] == 0
    assert metrics["llm"]["success_rate"] == 100.0


def test_track_llm_error():
    """Test: Trackear error LLM."""
    monitor = PerformanceMonitor()
    
    monitor.track_llm_call("auditor", case_id="CASE_001", success=False, error=Exception("LLM error"))
    
    metrics = monitor.get_metrics()
    assert metrics["llm"]["total_calls"] == 1
    assert metrics["llm"]["errors"] == 1
    assert metrics["llm"]["success_rate"] == 0.0


def test_track_rag_query():
    """Test: Trackear consulta RAG."""
    monitor = PerformanceMonitor()
    
    monitor.track_rag_query("legal", case_id="CASE_001", success=True, num_results=5, duration_ms=50)
    
    metrics = monitor.get_metrics()
    assert metrics["rag"]["total_queries"] == 1
    assert metrics["rag"]["errors"] == 0
    assert metrics["rag"]["success_rate"] == 100.0


def test_track_rag_error():
    """Test: Trackear error RAG."""
    monitor = PerformanceMonitor()
    
    monitor.track_rag_query("case", case_id="CASE_001", success=False, error=Exception("RAG error"))
    
    metrics = monitor.get_metrics()
    assert metrics["rag"]["total_queries"] == 1
    assert metrics["rag"]["errors"] == 1
    assert metrics["rag"]["success_rate"] == 0.0


def test_multiple_phases():
    """Test: Múltiples fases trackadas."""
    monitor = PerformanceMonitor()
    
    with monitor.track_phase("phase1", case_id="CASE_001"):
        time.sleep(0.01)
    
    with monitor.track_phase("phase2", case_id="CASE_001"):
        time.sleep(0.01)
    
    with monitor.track_phase("phase1", case_id="CASE_002"):
        time.sleep(0.01)
    
    metrics = monitor.get_metrics()
    assert "phase1" in metrics["phase_times"]
    assert "phase2" in metrics["phase_times"]
    assert metrics["phase_times"]["phase1"]["count"] == 2
    assert metrics["phase_times"]["phase2"]["count"] == 1


def test_error_tracking_in_phase():
    """Test: Tracking de errores en fases."""
    monitor = PerformanceMonitor()
    
    try:
        with monitor.track_phase("error_phase", case_id="CASE_001"):
            raise ValueError("Test error")
    except ValueError:
        pass
    
    metrics = monitor.get_metrics()
    assert metrics["total_errors"] == 1


def test_reset_metrics():
    """Test: Reset de métricas."""
    monitor = PerformanceMonitor()
    
    monitor.track_llm_call("auditor", success=True)
    monitor.track_rag_query("legal", success=True)
    
    monitor.reset_metrics()
    
    metrics = monitor.get_metrics()
    assert metrics["llm"]["total_calls"] == 0
    assert metrics["rag"]["total_queries"] == 0
    assert metrics["total_cases_analyzed"] == 0


def test_get_global_monitor():
    """Test: Obtener monitor global."""
    monitor1 = get_monitor()
    monitor2 = get_monitor()
    
    assert monitor1 is monitor2  # Debe ser el mismo objeto


def test_metrics_structure():
    """Test: Estructura de métricas."""
    monitor = PerformanceMonitor()
    metrics = monitor.get_metrics()
    
    assert "total_cases_analyzed" in metrics
    assert "total_errors" in metrics
    assert "avg_execution_time_ms" in metrics
    assert "llm" in metrics
    assert "rag" in metrics
    assert "phase_times" in metrics
    assert "generated_at" in metrics
    
    assert "total_calls" in metrics["llm"]
    assert "errors" in metrics["llm"]
    assert "success_rate" in metrics["llm"]
    
    assert "total_queries" in metrics["rag"]
    assert "errors" in metrics["rag"]
    assert "success_rate" in metrics["rag"]

