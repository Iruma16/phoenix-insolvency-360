"""
TESTS DE AUTORIDAD DE TRACE (FASE 6 - ENDURECIMIENTO 6).

Estos tests DEBEN fallar si:
- el trace permite ambigüedad temporal
- el replay produce resultados distintos
- una decisión no está registrada
- el manifest no certifica límites
- el trace puede modificarse después de creado
"""
import pytest
from datetime import datetime, timedelta

from app.trace.models import (
    ExecutionTrace,
    TraceDecision,
    TraceError,
    DecisionType,
    ExecutionMode,
    generate_trace_id,
)
from app.trace.trace_builder import TraceBuilder
from app.trace.replay import replay_trace, TraceReplayer
from app.trace.manifest import (
    create_manifest,
    verify_manifest,
    HardManifest,
    SchemaVersions,
    FinOpsSnapshot,
)


class TestTraceModels:
    """Tests del contrato de modelos de trace."""
    
    def test_trace_sin_decisiones_falla(self):
        """
        ✅ Trace sin decisiones debe lanzar excepción.
        """
        with pytest.raises(Exception):  # ValidationError from Pydantic
            ExecutionTrace(
                trace_id="test_trace",
                case_id="test_case",
                execution_timestamp=datetime.utcnow(),
                input_summary={"question_hash": "abc123"},
                decisions=[],  # VACÍO → debe fallar
                execution_mode=ExecutionMode.STRICT,
                system_version="1.0.0",
            )
    
    def test_decision_sin_timestamp_falla(self):
        """
        ✅ Decision sin timestamp debe lanzar excepción.
        """
        with pytest.raises(ValueError):
            TraceDecision(
                step_name="test_step",
                decision_type=DecisionType.VALIDATION,
                description="Test decision description here",
                timestamp=None,  # Falta timestamp → debe fallar
            )
    
    def test_decisiones_desordenadas_fallan(self):
        """
        ✅ Decisiones desordenadas deben lanzar excepción.
        """
        now = datetime.utcnow()
        
        decision1 = TraceDecision(
            step_name="step_1",
            decision_type=DecisionType.VALIDATION,
            description="First decision for testing",
            timestamp=now,
        )
        
        decision2 = TraceDecision(
            step_name="step_2",
            decision_type=DecisionType.VALIDATION,
            description="Second decision for testing",
            timestamp=now - timedelta(seconds=10),  # ANTES de decision1 → debe fallar
        )
        
        with pytest.raises(ValueError, match="Decisiones no ordenadas"):
            ExecutionTrace(
                trace_id="test_trace",
                case_id="test_case",
                execution_timestamp=now - timedelta(seconds=20),
                input_summary={"question_hash": "abc123"},
                decisions=[decision1, decision2],  # DESORDENADAS
                execution_mode=ExecutionMode.STRICT,
                system_version="1.0.0",
            )
    
    def test_trace_es_inmutable(self):
        """
        ✅ ExecutionTrace debe ser inmutable (frozen=True).
        """
        now = datetime.utcnow()
        
        decision = TraceDecision(
            step_name="test_step",
            decision_type=DecisionType.VALIDATION,
            description="Test decision for immutability",
            timestamp=now,
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now,
            input_summary={"question_hash": "abc123"},
            decisions=[decision],
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
        )
        
        # Intentar modificar debe fallar (Pydantic frozen)
        with pytest.raises(Exception):  # ValidationError o AttributeError
            trace.case_id = "modified_case"
    
    def test_trace_id_es_determinista(self):
        """
        ✅ trace_id debe ser determinista para mismo case_id + timestamp.
        """
        case_id = "test_case_123"
        timestamp = datetime(2025, 1, 7, 12, 0, 0)
        
        trace_id_1 = generate_trace_id(case_id, timestamp)
        trace_id_2 = generate_trace_id(case_id, timestamp)
        
        assert trace_id_1 == trace_id_2
        assert trace_id_1.startswith("trace_")


class TestTraceBuilder:
    """Tests del constructor de trace."""
    
    def test_builder_construye_trace_valido(self):
        """
        ✅ TraceBuilder debe construir un trace válido.
        """
        builder = TraceBuilder(
            case_id="test_case",
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0"
        )
        
        builder.set_input_summary("Test question", filters={"doc_type": "PDF"})
        
        builder.record_decision(
            step_name="validation",
            decision_type=DecisionType.VALIDATION,
            description="Document validation completed successfully",
        )
        
        builder.register_chunks_used(["chunk_1", "chunk_2"])
        builder.register_documents_consulted(["doc_1"])
        builder.mark_completed()
        
        trace = builder.build()
        
        assert trace.case_id == "test_case"
        assert len(trace.decisions) == 1
        assert len(trace.chunk_ids) == 2
        assert trace.completed_at is not None
    
    def test_builder_sin_decisiones_falla(self):
        """
        ✅ Builder sin decisiones no puede construir trace.
        """
        builder = TraceBuilder(
            case_id="test_case",
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0"
        )
        
        # NO registrar decisiones
        
        with pytest.raises(Exception):  # ValidationError from Pydantic
            builder.build()
    
    def test_builder_registra_errores(self):
        """
        ✅ Builder debe poder registrar errores.
        """
        builder = TraceBuilder(
            case_id="test_case",
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0"
        )
        
        builder.record_decision(
            step_name="start",
            decision_type=DecisionType.VALIDATION,
            description="Starting execution with validation",
        )
        
        builder.record_error(
            error_code="TEST_ERROR",
            error_message="Test error message",
            step_name="validation",
            recovered=True,
        )
        
        trace = builder.build()
        
        assert len(trace.errors) == 1
        assert trace.errors[0].error_code == "TEST_ERROR"
        assert trace.errors[0].recovered is True


class TestReplay:
    """Tests de replay de trace."""
    
    def test_replay_trace_valido_ok(self):
        """
        ✅ Replay de trace válido debe ser OK.
        """
        now = datetime.utcnow()
        
        decision = TraceDecision(
            step_name="test_step",
            decision_type=DecisionType.VALIDATION,
            description="Test decision for valid replay",
            timestamp=now,
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now - timedelta(seconds=10),
            input_summary={"question_hash": "abc123"},
            decisions=[decision],
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
            completed_at=now,
        )
        
        result = replay_trace(trace)
        
        assert result.is_valid is True
        assert len(result.divergences) == 0
    
    def test_replay_detecta_completed_at_invalido(self):
        """
        ✅ Replay debe detectar completed_at anterior a execution_timestamp.
        """
        now = datetime.utcnow()
        
        decision = TraceDecision(
            step_name="test_step",
            decision_type=DecisionType.VALIDATION,
            description="Test decision with invalid completed_at",
            timestamp=now,
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now,
            input_summary={"question_hash": "abc123"},
            decisions=[decision],
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
            completed_at=now - timedelta(seconds=10),  # ANTES de execution_timestamp
        )
        
        result = replay_trace(trace)
        
        assert result.is_valid is False
        assert any("completed_at es anterior" in d for d in result.divergences)
    
    def test_replay_detecta_evidence_huerfana(self):
        """
        ✅ Replay debe detectar evidence_ids no registrados en chunk_ids.
        """
        now = datetime.utcnow()
        
        decision = TraceDecision(
            step_name="test_step",
            decision_type=DecisionType.CHUNK_SELECTED,
            description="Test decision with orphan evidence",
            evidence_ids=["chunk_999"],  # NO registrado en chunk_ids
            timestamp=now,
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now - timedelta(seconds=10),
            input_summary={"question_hash": "abc123"},
            decisions=[decision],
            chunk_ids=["chunk_1", "chunk_2"],  # NO incluye chunk_999
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
        )
        
        result = replay_trace(trace)
        
        assert result.is_valid is False
        assert any("sin registrar en chunk_ids" in d for d in result.divergences)
    
    def test_replay_reconstruye_flujo(self):
        """
        ✅ Replay debe reconstruir flujo de ejecución.
        """
        now = datetime.utcnow()
        
        decision1 = TraceDecision(
            step_name="step_1",
            decision_type=DecisionType.VALIDATION,
            description="First step in execution flow",
            timestamp=now,
        )
        
        decision2 = TraceDecision(
            step_name="step_2",
            decision_type=DecisionType.GATE_APPLIED,
            description="Second step in execution flow",
            timestamp=now + timedelta(seconds=5),
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now - timedelta(seconds=10),
            input_summary={"question_hash": "abc123"},
            decisions=[decision1, decision2],
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
            completed_at=now + timedelta(seconds=10),
        )
        
        result = replay_trace(trace)
        
        assert len(result.reconstructed_flow) >= 2  # Al menos 2 decisiones
        
        # Verificar orden
        flow_steps = [f["step"] for f in result.reconstructed_flow if f.get("type") == "decision"]
        assert flow_steps == ["step_1", "step_2"]


class TestManifest:
    """Tests de manifest hard."""
    
    def test_create_manifest_valido(self):
        """
        ✅ Crear manifest válido para un trace.
        """
        now = datetime.utcnow()
        
        decision = TraceDecision(
            step_name="test_step",
            decision_type=DecisionType.VALIDATION,
            description="Test decision for manifest creation",
            timestamp=now,
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now,
            input_summary={"question_hash": "abc123"},
            decisions=[decision],
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
        )
        
        manifest = create_manifest(
            trace=trace,
            system_version="1.0.0",
        )
        
        assert manifest.trace_id == trace.trace_id
        assert manifest.case_id == trace.case_id
        assert len(manifest.integrity_hash) == 64  # SHA256
        assert manifest.schema_versions.trace_schema == "1.0.0"
    
    def test_manifest_sin_integrity_hash_falla(self):
        """
        ✅ Manifest sin integrity_hash debe fallar.
        """
        with pytest.raises(ValueError):
            HardManifest(
                trace_id="test_trace",
                case_id="test_case",
                schema_versions=SchemaVersions(
                    chunk_schema="1.0.0",
                    rag_schema="1.0.0",
                    legal_output_schema="1.0.0",
                    trace_schema="1.0.0",
                ),
                integrity_hash=None,  # Falta hash → debe fallar
                signed_at=datetime.utcnow(),
                system_version="1.0.0",
            )
    
    def test_manifest_verifica_integridad(self):
        """
        ✅ Manifest debe verificar integridad del trace.
        """
        now = datetime.utcnow()
        
        decision = TraceDecision(
            step_name="test_step",
            decision_type=DecisionType.VALIDATION,
            description="Test decision for integrity verification",
            timestamp=now,
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now,
            input_summary={"question_hash": "abc123"},
            decisions=[decision],
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
        )
        
        manifest = create_manifest(trace, system_version="1.0.0")
        
        # Verificar integridad
        assert manifest.verify_integrity(trace) is True
        assert verify_manifest(manifest, trace) is True
    
    def test_manifest_certifica_limites(self):
        """
        ✅ Manifest debe certificar límites explícitos del sistema.
        """
        now = datetime.utcnow()
        
        decision = TraceDecision(
            step_name="test_step",
            decision_type=DecisionType.VALIDATION,
            description="Test decision for limits certification",
            timestamp=now,
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now,
            input_summary={"question_hash": "abc123"},
            decisions=[decision],
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
        )
        
        manifest = create_manifest(trace, system_version="1.0.0")
        
        # Verificar límites
        assert manifest.execution_limits.cannot_process_without_documents is True
        assert manifest.execution_limits.cannot_generate_without_evidence is True
        assert manifest.execution_limits.cannot_guarantee_legal_validity is True
        assert manifest.execution_limits.requires_human_review is True
    
    def test_manifest_es_inmutable(self):
        """
        ✅ HardManifest debe ser inmutable (frozen=True).
        """
        now = datetime.utcnow()
        
        decision = TraceDecision(
            step_name="test_step",
            decision_type=DecisionType.VALIDATION,
            description="Test decision for manifest immutability",
            timestamp=now,
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now,
            input_summary={"question_hash": "abc123"},
            decisions=[decision],
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
        )
        
        manifest = create_manifest(trace, system_version="1.0.0")
        
        # Intentar modificar debe fallar
        with pytest.raises(Exception):  # ValidationError o AttributeError
            manifest.trace_id = "modified_trace"
    
    def test_manifest_incluye_finops_snapshot(self):
        """
        ✅ Manifest puede incluir snapshot de FinOps.
        """
        now = datetime.utcnow()
        
        decision = TraceDecision(
            step_name="test_step",
            decision_type=DecisionType.VALIDATION,
            description="Test decision for finops snapshot",
            timestamp=now,
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now,
            input_summary={"question_hash": "abc123"},
            decisions=[decision],
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
        )
        
        finops = FinOpsSnapshot(
            total_cost_usd=0.05,
            llm_calls=2,
            embedding_calls=10,
            tokens_used=1500,
        )
        
        manifest = create_manifest(
            trace=trace,
            system_version="1.0.0",
            finops_snapshot=finops,
        )
        
        assert manifest.finops_snapshot is not None
        assert manifest.finops_snapshot.total_cost_usd == 0.05
        assert manifest.finops_snapshot.llm_calls == 2


class TestTraceAuthority:
    """Tests de autoridad del trace."""
    
    def test_trace_timeline_no_permite_ambiguedad(self):
        """
        ✅ El timeline del trace debe ser completamente determinista.
        """
        now = datetime.utcnow()
        
        decision1 = TraceDecision(
            step_name="step_1",
            decision_type=DecisionType.VALIDATION,
            description="First decision with precise timestamp",
            timestamp=now,
        )
        
        decision2 = TraceDecision(
            step_name="step_2",
            decision_type=DecisionType.GATE_APPLIED,
            description="Second decision with precise timestamp",
            timestamp=now + timedelta(seconds=5),
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now - timedelta(seconds=10),
            input_summary={"question_hash": "abc123"},
            decisions=[decision1, decision2],
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
        )
        
        timeline = trace.get_timeline()
        
        # Verificar que timeline está ordenado
        for i in range(1, len(timeline)):
            assert timeline[i]["timestamp"] >= timeline[i-1]["timestamp"]
    
    def test_trace_certifica_que_sabía_sistema(self):
        """
        ✅ El trace debe certificar QUÉ SABÍA el sistema.
        """
        now = datetime.utcnow()
        
        decision = TraceDecision(
            step_name="evidence_check",
            decision_type=DecisionType.EVIDENCE_CHECK,
            description="Evidence check completed with 3 chunks found",
            evidence_ids=["chunk_1", "chunk_2", "chunk_3"],
            timestamp=now,
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now,
            input_summary={"question_hash": "abc123"},
            decisions=[decision],
            chunk_ids=["chunk_1", "chunk_2", "chunk_3"],
            document_ids=["doc_1"],
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
        )
        
        # El trace debe poder responder: "qué sabía"
        summary = trace.get_execution_summary()
        
        assert summary["chunks_used"] == 3
        assert summary["documents_consulted"] == 1
    
    def test_trace_certifica_cuando_lo_sabía(self):
        """
        ✅ El trace debe certificar CUÁNDO lo sabía el sistema.
        """
        execution_time = datetime(2025, 1, 7, 12, 0, 0)
        decision_time = datetime(2025, 1, 7, 12, 0, 5)
        
        decision = TraceDecision(
            step_name="validation",
            decision_type=DecisionType.VALIDATION,
            description="Validation completed at specific time",
            timestamp=decision_time,
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=execution_time,
            input_summary={"question_hash": "abc123"},
            decisions=[decision],
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
        )
        
        # El trace debe poder responder: "cuándo"
        assert trace.execution_timestamp == execution_time
        assert trace.decisions[0].timestamp >= execution_time
    
    def test_trace_certifica_con_que_evidencia(self):
        """
        ✅ El trace debe certificar CON QUÉ EVIDENCIA trabajó el sistema.
        """
        now = datetime.utcnow()
        
        decision = TraceDecision(
            step_name="report_generation",
            decision_type=DecisionType.REPORT_GENERATED,
            description="Legal report generated using specific chunks",
            evidence_ids=["chunk_a", "chunk_b"],
            timestamp=now,
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now,
            input_summary={"question_hash": "abc123"},
            decisions=[decision],
            chunk_ids=["chunk_a", "chunk_b"],
            legal_report_hash="abc123def456",
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
        )
        
        # El trace debe poder responder: "con qué evidencia"
        assert len(trace.chunk_ids) == 2
        assert "chunk_a" in trace.chunk_ids
        assert "chunk_b" in trace.chunk_ids
    
    def test_trace_certifica_con_que_coste(self):
        """
        ✅ El trace + manifest deben certificar CON QUÉ COSTE se ejecutó.
        """
        now = datetime.utcnow()
        
        decision = TraceDecision(
            step_name="llm_call",
            decision_type=DecisionType.REPORT_GENERATED,
            description="LLM call executed with cost tracking",
            timestamp=now,
        )
        
        trace = ExecutionTrace(
            trace_id="test_trace",
            case_id="test_case",
            execution_timestamp=now,
            input_summary={"question_hash": "abc123"},
            decisions=[decision],
            execution_mode=ExecutionMode.STRICT,
            system_version="1.0.0",
        )
        
        finops = FinOpsSnapshot(
            total_cost_usd=0.08,
            llm_calls=1,
            embedding_calls=5,
            tokens_used=2000,
        )
        
        manifest = create_manifest(
            trace=trace,
            system_version="1.0.0",
            finops_snapshot=finops,
        )
        
        # El manifest debe poder responder: "con qué coste"
        assert manifest.finops_snapshot.total_cost_usd == 0.08
        assert manifest.finops_snapshot.llm_calls == 1

