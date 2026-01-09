"""
REPLAY DE TRACE AUTORITATIVO (FASE 6 - ENDURECIMIENTO 6).

PRINCIPIO: Replay NO depende del LLM.
El replay reconstruye la ejecución desde el trace, verificando coherencia.

Permite:
- Auditoría técnica
- Verificación de integridad
- Detección de divergencias
"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.trace.models import ExecutionTrace, TraceDecision, TraceError, DecisionType


class ReplayResult:
    """
    Resultado de un replay de trace.
    """
    
    def __init__(self, trace: ExecutionTrace):
        self.trace = trace
        self.is_valid = True
        self.divergences: List[str] = []
        self.warnings: List[str] = []
        self.reconstructed_flow: List[Dict[str, Any]] = []
    
    def add_divergence(self, message: str) -> None:
        """Registra una divergencia detectada."""
        self.is_valid = False
        self.divergences.append(message)
    
    def add_warning(self, message: str) -> None:
        """Registra un warning (no crítico)."""
        self.warnings.append(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa resultado a dict."""
        return {
            "trace_id": self.trace.trace_id,
            "is_valid": self.is_valid,
            "divergences": self.divergences,
            "warnings": self.warnings,
            "reconstructed_steps": len(self.reconstructed_flow),
            "timeline_events": len(self.trace.get_timeline()),
        }


class TraceReplayer:
    """
    Replayer de trace autoritativo.
    
    NO ejecuta lógica de negocio.
    NO llama al LLM.
    SOLO verifica coherencia del trace.
    """
    
    def __init__(self, trace: ExecutionTrace):
        """
        Inicializa replayer con un trace.
        
        Args:
            trace: ExecutionTrace a replicar
        """
        self.trace = trace
        self.result = ReplayResult(trace)
    
    def replay(self) -> ReplayResult:
        """
        Ejecuta replay del trace.
        
        Verifica:
        - Coherencia temporal
        - Integridad de evidencia
        - Completitud de decisiones
        - Validez de estructura
        
        Returns:
            ReplayResult con estado de validación
        """
        # Validar estructura básica
        self._validate_basic_structure()
        
        # Validar coherencia temporal
        self._validate_temporal_coherence()
        
        # Validar evidencia
        self._validate_evidence_integrity()
        
        # Validar decisiones
        self._validate_decisions()
        
        # Reconstruir flujo
        self._reconstruct_execution_flow()
        
        return self.result
    
    def _validate_basic_structure(self) -> None:
        """
        Valida estructura básica del trace.
        """
        # Verificar campos obligatorios
        if not self.trace.trace_id:
            self.result.add_divergence("trace_id faltante")
        
        if not self.trace.case_id:
            self.result.add_divergence("case_id faltante")
        
        if not self.trace.decisions:
            self.result.add_divergence("Trace sin decisiones")
        
        if not self.trace.execution_timestamp:
            self.result.add_divergence("execution_timestamp faltante")
        
        # Verificar inmutabilidad (frozen)
        if not self.trace.model_config.get("frozen", False):
            self.result.add_divergence("Trace no es inmutable (frozen=False)")
    
    def _validate_temporal_coherence(self) -> None:
        """
        Valida coherencia temporal del trace.
        
        Verifica que:
        - Decisiones están ordenadas
        - No hay timestamps futuros
        - completed_at es posterior a execution_timestamp
        """
        now = datetime.utcnow()
        
        # Verificar que execution_timestamp no es futuro
        if self.trace.execution_timestamp > now:
            self.result.add_divergence(
                f"execution_timestamp es futuro: {self.trace.execution_timestamp}"
            )
        
        # Verificar orden de decisiones
        for i in range(1, len(self.trace.decisions)):
            if self.trace.decisions[i].timestamp < self.trace.decisions[i-1].timestamp:
                self.result.add_divergence(
                    f"Decisiones desordenadas: {self.trace.decisions[i].step_name} "
                    f"antes de {self.trace.decisions[i-1].step_name}"
                )
        
        # Verificar completed_at
        if self.trace.completed_at:
            if self.trace.completed_at < self.trace.execution_timestamp:
                self.result.add_divergence(
                    "completed_at es anterior a execution_timestamp"
                )
            
            # completed_at debe ser posterior a última decisión
            if self.trace.decisions:
                last_decision_ts = self.trace.decisions[-1].timestamp
                if self.trace.completed_at < last_decision_ts:
                    self.result.add_divergence(
                        "completed_at es anterior a última decisión"
                    )
    
    def _validate_evidence_integrity(self) -> None:
        """
        Valida integridad de evidencia registrada.
        
        Verifica que:
        - Todos los evidence_ids en decisiones están en chunk_ids
        - No hay evidence_ids huérfanos
        """
        # Recolectar todos los evidence_ids de decisiones
        evidence_ids_in_decisions = set()
        for decision in self.trace.decisions:
            evidence_ids_in_decisions.update(decision.evidence_ids)
        
        # Verificar que están registrados en chunk_ids
        trace_chunk_ids = set(self.trace.chunk_ids)
        
        orphan_evidence = evidence_ids_in_decisions - trace_chunk_ids
        if orphan_evidence:
            self.result.add_divergence(
                f"Evidence_ids sin registrar en chunk_ids: {orphan_evidence}"
            )
        
        # Verificar que legal_report_hash existe si hay chunk_ids
        if self.trace.chunk_ids and not self.trace.legal_report_hash:
            self.result.add_warning(
                "Hay chunk_ids pero no legal_report_hash (posible ejecución incompleta)"
            )
    
    def _validate_decisions(self) -> None:
        """
        Valida coherencia de decisiones.
        
        Verifica que:
        - Cada decisión tiene timestamp
        - description no está vacía
        - step_name es determinista
        """
        step_names_seen = set()
        
        for decision in self.trace.decisions:
            # Verificar timestamp
            if not decision.timestamp:
                self.result.add_divergence(
                    f"Decisión sin timestamp: {decision.step_name}"
                )
            
            # Verificar description
            if not decision.description or len(decision.description) < 10:
                self.result.add_divergence(
                    f"Decisión con description insuficiente: {decision.step_name}"
                )
            
            # Verificar step_name (debe ser único para determinismo)
            if decision.step_name in step_names_seen:
                self.result.add_warning(
                    f"step_name duplicado: {decision.step_name} (puede afectar replay)"
                )
            step_names_seen.add(decision.step_name)
    
    def _reconstruct_execution_flow(self) -> None:
        """
        Reconstruye el flujo de ejecución desde el trace.
        
        NO ejecuta lógica.
        SOLO reconstruye la secuencia de pasos.
        """
        flow = []
        
        # Inicio
        flow.append({
            "step": "execution_start",
            "timestamp": self.trace.execution_timestamp,
            "case_id": self.trace.case_id,
            "mode": self.trace.execution_mode.value,
        })
        
        # Decisiones
        for decision in self.trace.decisions:
            flow.append({
                "step": decision.step_name,
                "type": "decision",
                "decision_type": decision.decision_type.value,
                "timestamp": decision.timestamp,
                "evidence_count": len(decision.evidence_ids),
            })
        
        # Errores
        for error in self.trace.errors:
            flow.append({
                "step": error.step_name,
                "type": "error",
                "error_code": error.error_code,
                "timestamp": error.timestamp,
                "recovered": error.recovered,
            })
        
        # Finalización
        if self.trace.completed_at:
            flow.append({
                "step": "execution_completed",
                "timestamp": self.trace.completed_at,
            })
        else:
            flow.append({
                "step": "execution_aborted",
                "last_decision": self.trace.decisions[-1].step_name if self.trace.decisions else None,
            })
        
        # Ordenar por timestamp
        flow_with_ts = [f for f in flow if "timestamp" in f]
        flow_with_ts.sort(key=lambda x: x["timestamp"])
        
        self.result.reconstructed_flow = flow_with_ts


def replay_trace(trace: ExecutionTrace) -> ReplayResult:
    """
    Función helper para ejecutar replay de un trace.
    
    Args:
        trace: ExecutionTrace a replicar
        
    Returns:
        ReplayResult con resultado de validación
    """
    replayer = TraceReplayer(trace)
    return replayer.replay()

