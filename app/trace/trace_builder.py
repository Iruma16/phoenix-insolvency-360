"""
CONSTRUCTOR DE TRACE AUTORITATIVO (FASE 6 - ENDURECIMIENTO 6).

PRINCIPIO: Todo lo que ocurre debe quedar registrado.
NO se permite ejecución sin trace.

Este módulo construye el trace de forma determinista e inmutable.
"""
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from app.trace.models import (
    ExecutionTrace,
    TraceDecision,
    TraceError,
    DecisionType,
    ExecutionMode,
    generate_trace_id,
)

if TYPE_CHECKING:
    from app.models.legal_output import LegalReport


class TraceBuilder:
    """
    Constructor de trace autoritativo.
    
    Patrón builder para construcción incremental del trace.
    Una vez completado, el trace es INMUTABLE.
    """
    
    def __init__(self, case_id: str, execution_mode: ExecutionMode, system_version: str):
        """
        Inicializa builder de trace.
        
        Args:
            case_id: ID del caso
            execution_mode: STRICT o PERMISSIVE
            system_version: Versión del sistema
        """
        self.case_id = case_id
        self.execution_mode = execution_mode
        self.system_version = system_version
        self.execution_timestamp = datetime.utcnow()
        
        self.decisions: List[TraceDecision] = []
        self.errors: List[TraceError] = []
        self.chunk_ids: set = set()
        self.document_ids: set = set()
        self.input_summary: Dict[str, str] = {}
        self.legal_report_hash: Optional[str] = None
        self.completed_at: Optional[datetime] = None
    
    def record_decision(
        self,
        step_name: str,
        decision_type: DecisionType,
        description: str,
        evidence_ids: Optional[List[str]] = None,
        validation_applied: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Registra una decisión en el trace.
        
        Args:
            step_name: Nombre del paso (determinista)
            decision_type: Tipo de decisión
            description: Descripción objetiva
            evidence_ids: IDs de evidencia implicados
            validation_applied: Validación aplicada
            metadata: Metadata adicional
        """
        decision = TraceDecision(
            step_name=step_name,
            decision_type=decision_type,
            description=description,
            evidence_ids=evidence_ids or [],
            validation_applied=validation_applied,
            timestamp=datetime.utcnow(),
            metadata=metadata or {},
        )
        
        self.decisions.append(decision)
        
        # Registrar evidence_ids
        if evidence_ids:
            for ev_id in evidence_ids:
                if ev_id.startswith("chunk_"):
                    self.chunk_ids.add(ev_id)
    
    def record_error(
        self,
        error_code: str,
        error_message: str,
        step_name: str,
        recovered: bool = False,
    ) -> None:
        """
        Registra un error en el trace.
        
        Args:
            error_code: Código del error
            error_message: Mensaje del error
            step_name: Paso donde ocurrió
            recovered: Si el error fue recuperado
        """
        error = TraceError(
            error_code=error_code,
            error_message=error_message,
            step_name=step_name,
            timestamp=datetime.utcnow(),
            recovered=recovered,
        )
        
        self.errors.append(error)
    
    def set_input_summary(self, question: str, filters: Optional[Dict[str, Any]] = None) -> None:
        """
        Registra resumen del input (hashes, NO texto libre).
        
        Args:
            question: Pregunta original
            filters: Filtros aplicados (doc_types, dates, etc.)
        """
        # Hash de la pregunta (NO el texto literal)
        question_hash = hashlib.sha256(question.encode()).hexdigest()
        
        self.input_summary = {
            "question_hash": question_hash,
            "question_length": str(len(question)),  # Convertir a string para Dict[str, str]
        }
        
        if filters:
            self.input_summary["filters"] = str(filters)
    
    def register_chunks_used(self, chunk_ids: List[str]) -> None:
        """
        Registra chunks utilizados en la ejecución.
        
        Args:
            chunk_ids: Lista de chunk_ids
        """
        self.chunk_ids.update(chunk_ids)
    
    def register_documents_consulted(self, document_ids: List[str]) -> None:
        """
        Registra documentos consultados.
        
        Args:
            document_ids: Lista de document_ids
        """
        self.document_ids.update(document_ids)
    
    def register_legal_report(self, report: "LegalReport") -> None:
        """
        Registra reporte legal generado.
        
        Calcula hash del reporte para integridad.
        
        Args:
            report: LegalReport generado
        """
        # Serializar reporte a JSON
        report_json = report.json()
        
        # Calcular hash
        self.legal_report_hash = hashlib.sha256(report_json.encode()).hexdigest()
        
        # Extraer evidence_ids del reporte
        evidence_ids = report.get_all_evidence_ids()
        self.register_chunks_used(evidence_ids)
    
    def mark_completed(self) -> None:
        """
        Marca la ejecución como completada.
        """
        self.completed_at = datetime.utcnow()
    
    def build(self) -> ExecutionTrace:
        """
        Construye el trace final INMUTABLE.
        
        Returns:
            ExecutionTrace validado e inmutable
            
        Raises:
            ValueError: Si el trace no es válido
        """
        # Generar trace_id
        trace_id = generate_trace_id(self.case_id, self.execution_timestamp)
        
        # Construir trace (será inmutable)
        trace = ExecutionTrace(
            trace_id=trace_id,
            case_id=self.case_id,
            execution_timestamp=self.execution_timestamp,
            input_summary=self.input_summary,
            chunk_ids=sorted(list(self.chunk_ids)),  # Ordenado para determinismo
            document_ids=sorted(list(self.document_ids)),  # Ordenado
            legal_report_hash=self.legal_report_hash,
            decisions=self.decisions,  # Ya ordenado por timestamp (validado en modelo)
            errors=self.errors,
            execution_mode=self.execution_mode,
            system_version=self.system_version,
            completed_at=self.completed_at,
        )
        
        return trace


def compute_legal_report_hash(report: "LegalReport") -> str:
    """
    Calcula hash de un LegalReport para integridad.
    
    Args:
        report: LegalReport a hashear
        
    Returns:
        Hash SHA256 hex
    """
    report_json = report.json()
    return hashlib.sha256(report_json.encode()).hexdigest()

