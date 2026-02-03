"""
TEST TRACING & OBSERVABILITY

Certifica que la instrumentación de observabilidad funciona correctamente.
Tests obligatorios para PUNTO 6: OBSERVABILIDAD Y REPLAY.
"""
try:
    import pytest

    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

import json
import sys
from io import StringIO


def test_trace_context_emitted():
    """
    TEST CRÍTICO: TraceContext debe emitirse por stdout con campos obligatorios.

    INVARIANTE: [TRACE] con request_id, case_id, prompt_version, vectorstore_version
    """
    from app.services.tracing import TracingSession

    # Capturar stdout
    captured_output = StringIO()
    sys.stdout = captured_output

    try:
        # Crear sesión de tracing
        session = TracingSession(component="RAG", case_id="test_case_001")
        session.set_prompt_version("v1.0.0")
        session.set_vectorstore_version("v_20250105_120000")
        session.set_retrieval_params(top_k=5)
        session.set_decision("RESPUESTA_CON_EVIDENCIA")

        # Finalizar y emitir
        trace = session.finish()

        output = captured_output.getvalue()

        # Validar que aparece [TRACE]
        assert "[TRACE]" in output, "FAIL: No aparece [TRACE] en stdout"

        # Parsear JSON
        trace_line = [line for line in output.split("\n") if "[TRACE]" in line][0]
        trace_json = trace_line.split("[TRACE] ")[1]
        trace_data = json.loads(trace_json)

        # Validar campos obligatorios
        assert "request_id" in trace_data, "FAIL: Falta request_id"
        assert "case_id" in trace_data, "FAIL: Falta case_id"
        assert trace_data["case_id"] == "test_case_001", "FAIL: case_id incorrecto"
        assert "prompt_version" in trace_data, "FAIL: Falta prompt_version"
        assert trace_data["prompt_version"] == "v1.0.0", "FAIL: prompt_version incorrecto"
        assert "vectorstore_version" in trace_data, "FAIL: Falta vectorstore_version"
        assert (
            trace_data["vectorstore_version"] == "v_20250105_120000"
        ), "FAIL: vectorstore_version incorrecto"
        assert "timestamp_start" in trace_data, "FAIL: Falta timestamp_start"
        assert "timestamp_end" in trace_data, "FAIL: Falta timestamp_end"
        assert "latency_ms_total" in trace_data, "FAIL: Falta latency_ms_total"

    finally:
        sys.stdout = sys.__stdout__

    # ÉXITO: TraceContext emitido correctamente
    print("✅ test_trace_context_emitted: PASS")


def test_decision_record_emitted():
    """
    TEST CRÍTICO: DecisionRecord debe emitirse sin PII ni texto libre.

    INVARIANTE: [DECISION_RECORD] sin content, extracto_literal, raw_text
    """
    from app.services.tracing import TracingSession

    # Capturar stdout
    captured_output = StringIO()
    sys.stdout = captured_output

    try:
        # Crear sesión de tracing
        session = TracingSession(component="PROSECUTOR", case_id="test_case_002")
        session.set_prompt_version("prosecutor_v1.0.0")
        session.set_vectorstore_version("v_20250105_120000")
        session.set_retrieval_params(top_k=10)
        session.add_tool("rag_answer_internal")
        session.add_tool("query_legal_rag")

        # Añadir chunks citados SIN extractos
        session.add_cited_chunks(
            [
                {
                    "chunk_id": "chunk_001",
                    "doc_id": "documento.pdf",
                    "page": 1,
                    "start_char": 0,
                    "end_char": 500,
                    "content": "ESTE TEXTO NO DEBE APARECER EN EL RECORD",  # PII
                }
            ]
        )

        session.set_decision("ACCUSATION_START")

        # Emitir DecisionRecord
        record = session.emit_decision_record()

        output = captured_output.getvalue()

        # Validar que aparece [DECISION_RECORD]
        assert "[DECISION_RECORD]" in output, "FAIL: No aparece [DECISION_RECORD] en stdout"

        # Parsear JSON
        record_line = [line for line in output.split("\n") if "[DECISION_RECORD]" in line][0]
        record_json = record_line.split("[DECISION_RECORD] ")[1]
        record_data = json.loads(record_json)

        # Validar campos obligatorios
        assert "request_id" in record_data, "FAIL: Falta request_id"
        assert "prompt_version" in record_data, "FAIL: Falta prompt_version"
        assert "vectorstore_version" in record_data, "FAIL: Falta vectorstore_version"
        assert "retrieval_params" in record_data, "FAIL: Falta retrieval_params"
        assert "tools_used" in record_data, "FAIL: Falta tools_used"
        assert "cited_chunks" in record_data, "FAIL: Falta cited_chunks"

        # Validar que NO contiene PII ni texto libre
        full_output = json.dumps(record_data)
        assert (
            "ESTE TEXTO NO DEBE APARECER" not in full_output
        ), "FAIL: DecisionRecord contiene texto libre (PII)"
        assert "content" not in str(
            record_data.get("cited_chunks", [])
        ), "FAIL: DecisionRecord contiene campo 'content' con PII"
        assert (
            "extracto_literal" not in full_output
        ), "FAIL: DecisionRecord contiene 'extracto_literal' con PII"

        # Validar que cited_chunks tiene SOLO identificadores
        cited_chunks = record_data["cited_chunks"]
        assert len(cited_chunks) > 0, "FAIL: No hay cited_chunks"
        first_chunk = cited_chunks[0]
        assert "chunk_id" in first_chunk, "FAIL: Falta chunk_id en cited_chunk"
        assert "doc_id" in first_chunk, "FAIL: Falta doc_id en cited_chunk"

    finally:
        sys.stdout = sys.__stdout__

    # ÉXITO: DecisionRecord sin PII
    print("✅ test_decision_record_emitted: PASS")


def test_replay_uses_original_versions():
    """
    TEST CRÍTICO: Replay debe usar versiones originales, NUNCA "latest".

    INVARIANTE: replay_of presente, mismas versiones que request original
    """
    from app.services.tracing import (
        TracingSession,
        get_decision_record,
        store_decision_record,
    )

    # Capturar stdout
    captured_output = StringIO()
    sys.stdout = captured_output

    try:
        # REQUEST ORIGINAL
        original_session = TracingSession(component="RAG", case_id="test_case_003")
        original_session.set_prompt_version("v1.0.0")
        original_session.set_vectorstore_version("v_20250105_120000")
        original_session.set_retrieval_params(top_k=5)
        original_session.set_decision("RESPUESTA_CON_EVIDENCIA")

        original_record = original_session.emit_decision_record()
        store_decision_record(original_record)
        original_request_id = original_session.request_id

        # REPLAY DEL REQUEST
        # Recuperar record original
        stored_record = get_decision_record(original_request_id)
        assert stored_record is not None, "FAIL: No se recuperó DecisionRecord"

        # Crear nuevo session para replay
        replay_session = TracingSession(component="RAG", case_id=stored_record.case_id)
        replay_session.mark_replay(original_request_id)

        # CRÍTICO: Usar MISMAS versiones
        replay_session.set_prompt_version(stored_record.prompt_version)
        replay_session.set_vectorstore_version(stored_record.vectorstore_version)
        replay_session.set_retrieval_params(**stored_record.retrieval_params)
        replay_session.set_decision("RESPUESTA_CON_EVIDENCIA")  # Puede variar

        replay_trace = replay_session.finish()

        output = captured_output.getvalue()

        # Parsear TRACE del replay
        trace_lines = [line for line in output.split("\n") if "[TRACE]" in line]
        replay_trace_line = trace_lines[-1]  # Último trace (el del replay)
        replay_trace_json = replay_trace_line.split("[TRACE] ")[1]
        replay_trace_data = json.loads(replay_trace_json)

        # Validar que es un replay
        assert "replay_of" in replay_trace_data, "FAIL: Falta replay_of"
        assert (
            replay_trace_data["replay_of"] == original_request_id
        ), "FAIL: replay_of no coincide con request_id original"

        # Validar que usa MISMAS versiones
        assert (
            replay_trace_data["prompt_version"] == "v1.0.0"
        ), "FAIL: Replay usa prompt_version diferente"
        assert (
            replay_trace_data["vectorstore_version"] == "v_20250105_120000"
        ), "FAIL: Replay usa vectorstore_version diferente"
        assert replay_trace_data["retrieval_top_k"] == 5, "FAIL: Replay usa top_k diferente"

        # Validar que NO usa "latest"
        assert (
            "latest" not in str(replay_trace_data.get("prompt_version", "")).lower()
        ), "FAIL: Replay usa 'latest' en prompt_version"
        assert (
            "latest" not in str(replay_trace_data.get("vectorstore_version", "")).lower()
        ), "FAIL: Replay usa 'latest' en vectorstore_version"

    finally:
        sys.stdout = sys.__stdout__

    # ÉXITO: Replay usa versiones originales
    print("✅ test_replay_uses_original_versions: PASS")


def test_no_pii_in_logs():
    """
    TEST: Verificar que sanitize_for_logging elimina PII.
    """
    from app.services.tracing import sanitize_for_logging

    # Mock data con PII
    data_with_pii = {
        "chunk_id": "chunk_001",
        "content": "Este es texto sensible con datos personales",
        "extracto_literal": "Más texto sensible",
        "page": 1,
        "start_char": 0,
    }

    # Sanitizar
    sanitized = sanitize_for_logging(data_with_pii)

    # Validar que PII fue redactado
    assert "Este es texto sensible" not in str(sanitized), "FAIL: 'content' no fue redactado"
    assert "Más texto sensible" not in str(sanitized), "FAIL: 'extracto_literal' no fue redactado"
    assert "[REDACTED" in str(sanitized.get("content", "")), "FAIL: 'content' no muestra [REDACTED]"

    # Validar que identificadores permanecen
    assert sanitized["chunk_id"] == "chunk_001", "FAIL: chunk_id fue eliminado"
    assert sanitized["page"] == 1, "FAIL: page fue eliminado"

    print("✅ test_no_pii_in_logs: PASS")


# ============================
# EJECUTAR TESTS
# ============================

if __name__ == "__main__":
    if HAS_PYTEST:
        pytest.main([__file__, "-v"])
    else:
        # Ejecutar tests manualmente
        print("\n" + "=" * 80)
        print("EJECUTANDO TESTS DE TRACING")
        print("=" * 80)

        test_trace_context_emitted()
        test_decision_record_emitted()
        test_replay_uses_original_versions()
        test_no_pii_in_logs()

        print("\n" + "=" * 80)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 80)
