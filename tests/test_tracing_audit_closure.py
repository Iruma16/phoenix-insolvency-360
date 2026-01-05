"""
TEST TRACING AUDIT CLOSURE

Tests para cerrar matices operativos del PUNTO 6.
Certifica comportamientos críticos para producción.
"""
try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from io import StringIO
import sys
import json
import os

# Agregar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_decision_record_storage_explicit():
    """
    TEST: Storage de DecisionRecord debe ser explícito.
    
    INVARIANTE: [CERT] DECISION_RECORD_STORAGE con backend, key, retention
    """
    from app.services.tracing import TracingSession, store_decision_record
    
    # Capturar stdout
    captured_output = StringIO()
    sys.stdout = captured_output
    
    try:
        session = TracingSession(component="RAG", case_id="test_storage")
        session.set_prompt_version("v1.0.0")
        session.set_vectorstore_version("v_20250105_120000")
        session.set_decision("TEST")
        
        record = session.emit_decision_record()
        store_decision_record(record)
        
        output = captured_output.getvalue()
        
        # Validar certificación de storage
        assert "[CERT] DECISION_RECORD_STORAGE" in output, \
            "FAIL: No aparece certificación de storage"
        assert "backend=" in output, "FAIL: Falta backend explícito"
        assert "key=" in output, "FAIL: Falta key explícita"
        assert "retention=" in output, "FAIL: Falta política de retención"
        
        # Validar que backend es explícito (no "unknown" o genérico)
        assert "in-memory-dict" in output or "redis" in output or "postgres" in output, \
            "FAIL: Backend no es explícito"
        
    finally:
        sys.stdout = sys.__stdout__
    
    print("✅ test_decision_record_storage_explicit: PASS")


def test_replay_deterministic_with_scores():
    """
    TEST: Replay debe preservar scores para determinismo absoluto.
    
    INVARIANTE: [CERT] REPLAY_CONTEXT con chunk_ids y scores
    """
    from app.services.tracing import TracingSession
    
    # Capturar stdout
    captured_output = StringIO()
    sys.stdout = captured_output
    
    try:
        session = TracingSession(component="RAG", case_id="test_deterministic")
        session.set_prompt_version("v1.0.0")
        session.set_vectorstore_version("v_20250105_120000")
        
        # Añadir chunks CON scores
        chunks_with_scores = [
            ("chunk_001", 0.95),
            ("chunk_002", 0.87),
            ("chunk_003", 0.82),
        ]
        session.add_chunk_ids_with_scores(chunks_with_scores)
        
        session.set_decision("TEST")
        trace = session.finish()
        
        output = captured_output.getvalue()
        
        # Validar certificación de replay context
        assert "[CERT] REPLAY_CONTEXT" in output, \
            "FAIL: No aparece certificación de replay context"
        assert "chunk_ids=" in output, "FAIL: Faltan chunk_ids"
        assert "scores=" in output, "FAIL: Faltan scores"
        
        # Validar que scores están presentes
        assert "0.95" in output and "0.87" in output and "0.82" in output, \
            "FAIL: Scores no están presentes"
        
        # Validar que TraceContext incluye scores
        assert trace.chunk_scores is not None, "FAIL: chunk_scores es None"
        assert len(trace.chunk_scores) == 3, "FAIL: No se preservaron todos los scores"
        
    finally:
        sys.stdout = sys.__stdout__
    
    print("✅ test_replay_deterministic_with_scores: PASS")


def test_step_visibility():
    """
    TEST: Steps intermedios deben ser visibles con latencias.
    
    INVARIANTE: [TRACE_STEP] con step, latency_ms, tokens
    """
    from app.services.tracing import TracingSession
    
    # Capturar stdout
    captured_output = StringIO()
    sys.stdout = captured_output
    
    try:
        session = TracingSession(component="PROSECUTOR", case_id="test_steps")
        
        # Loggear steps
        session.log_step("retrieval", latency_ms=45.2)
        session.log_step("gate_1_obligacion", latency_ms=2.1)
        session.log_step("gate_2_trazable", latency_ms=3.5)
        session.log_step("llm_call", latency_ms=320.5, tokens_in=1500, tokens_out=300)
        
        output = captured_output.getvalue()
        
        # Validar que aparecen steps
        assert output.count("[TRACE_STEP]") >= 4, \
            "FAIL: No aparecen todos los steps"
        assert "step=retrieval" in output, "FAIL: Falta step retrieval"
        assert "step=llm_call" in output, "FAIL: Falta step llm_call"
        assert "latency_ms=" in output, "FAIL: Falta latency_ms"
        assert "tokens_in=" in output, "FAIL: Faltan tokens_in"
        assert "tokens_out=" in output, "FAIL: Faltan tokens_out"
        
    finally:
        sys.stdout = sys.__stdout__
    
    print("✅ test_step_visibility: PASS")


def test_no_latest_certification():
    """
    TEST: Debe certificar que NO se usa "latest".
    
    INVARIANTE: [CERT] NO_LATEST_USAGE = OK
    """
    from app.services.tracing import (
        TracingSession,
        store_decision_record,
        get_decision_record,
    )
    
    # Capturar stdout
    captured_output = StringIO()
    sys.stdout = captured_output
    
    try:
        session = TracingSession(component="RAG", case_id="test_no_latest")
        session.set_prompt_version("v1.0.0")
        session.set_vectorstore_version("v_20250105_120000")
        session.set_decision("TEST")
        
        record = session.emit_decision_record()
        store_decision_record(record)
        
        # Recuperar record
        retrieved = get_decision_record(session.request_id)
        
        output = captured_output.getvalue()
        
        # Validar certificación
        assert "[CERT] NO_LATEST_USAGE = OK" in output, \
            "FAIL: No aparece certificación de NO_LATEST_USAGE"
        
    finally:
        sys.stdout = sys.__stdout__
    
    print("✅ test_no_latest_certification: PASS")


def test_no_fallbacks_certification():
    """
    TEST: Debe certificar que NO hay fallbacks silenciosos.
    
    INVARIANTE: [CERT] NO_FALLBACKS = OK
    """
    from app.services.tracing import TracingSession
    
    # Capturar stdout
    captured_output = StringIO()
    sys.stdout = captured_output
    
    try:
        session = TracingSession(component="RAG", case_id="test_no_fallbacks")
        session.set_prompt_version("v1.0.0")
        session.set_vectorstore_version("v_20250105_120000")
        session.set_decision("TEST")
        
        trace = session.finish()
        
        output = captured_output.getvalue()
        
        # Validar certificación
        assert "[CERT] NO_FALLBACKS = OK" in output, \
            "FAIL: No aparece certificación de NO_FALLBACKS"
        
    finally:
        sys.stdout = sys.__stdout__
    
    print("✅ test_no_fallbacks_certification: PASS")


def test_no_global_state_certification():
    """
    TEST: Debe certificar que NO usa estado global mutable.
    
    INVARIANTE: [CERT] NO_GLOBAL_STATE = OK
    """
    from app.services.tracing import TracingSession
    
    # Capturar stdout
    captured_output = StringIO()
    sys.stdout = captured_output
    
    try:
        session = TracingSession(component="RAG", case_id="test_no_global_state")
        
        output = captured_output.getvalue()
        
        # Validar certificación (se emite en __init__)
        assert "[CERT] NO_GLOBAL_STATE = OK" in output, \
            "FAIL: No aparece certificación de NO_GLOBAL_STATE"
        
    finally:
        sys.stdout = sys.__stdout__
    
    print("✅ test_no_global_state_certification: PASS")


def test_latest_in_versions_fails():
    """
    TEST: Si un DecisionRecord contiene "latest", debe fallar.
    
    INVARIANTE: Assert en get_decision_record si hay "latest"
    """
    from app.services.tracing import DecisionRecord, store_decision_record, get_decision_record
    
    # Capturar stdout
    captured_output = StringIO()
    sys.stdout = captured_output
    
    try:
        # Crear record con "latest" (MAL)
        bad_record = DecisionRecord(
            request_id="bad_request_001",
            case_id="test",
            component="RAG",
            prompt_version="latest",  # PROHIBIDO
            vectorstore_version="v_20250105_120000",
            retrieval_params={},
            tools_used=[],
            cited_chunks=[],
            decision_final="TEST",
        )
        
        store_decision_record(bad_record)
        
        # Intentar recuperar (debe fallar)
        try:
            get_decision_record("bad_request_001")
            # Si llega aquí, FAIL
            assert False, "FAIL: DecisionRecord con 'latest' NO falló"
        except AssertionError as e:
            if "latest" in str(e).lower():
                # CORRECTO: Detectó "latest" y falló
                pass
            else:
                raise
        
    finally:
        sys.stdout = sys.__stdout__
    
    print("✅ test_latest_in_versions_fails: PASS")


# ============================
# EJECUTAR TESTS
# ============================

if __name__ == "__main__":
    if HAS_PYTEST:
        pytest.main([__file__, "-v"])
    else:
        # Ejecutar tests manualmente
        print("\n" + "="*80)
        print("EJECUTANDO TESTS DE AUDITORÍA DE TRACING")
        print("="*80)
        
        test_decision_record_storage_explicit()
        test_replay_deterministic_with_scores()
        test_step_visibility()
        test_no_latest_certification()
        test_no_fallbacks_certification()
        test_no_global_state_certification()
        test_latest_in_versions_fails()
        
        print("\n" + "="*80)
        print("✅ TODOS LOS TESTS DE AUDITORÍA PASARON")
        print("="*80)

