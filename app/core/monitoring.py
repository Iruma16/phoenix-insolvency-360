"""
Sistema de monitoreo básico para Phoenix Legal.

Instrumenta tiempos de ejecución, errores LLM y fallos RAG.
"""
import time
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, field

from app.core.logger import get_logger

logger = get_logger()


@dataclass
class MetricsSummary:
    """Resumen de métricas del sistema."""
    total_cases_analyzed: int = 0
    total_errors: int = 0
    avg_execution_time_ms: float = 0.0
    llm_calls: int = 0
    llm_errors: int = 0
    rag_queries: int = 0
    rag_errors: int = 0
    phase_times: Dict[str, List[float]] = field(default_factory=dict)


class PerformanceMonitor:
    """
    Monitor de rendimiento para auditoría y observabilidad.
    
    Registra:
    - Tiempos de ejecución por fase
    - Errores de LLM
    - Fallos de RAG
    - Métricas agregadas
    """
    
    def __init__(self):
        """Inicializa el monitor."""
        self.metrics = MetricsSummary()
        self._current_case_start: Optional[float] = None
    
    @contextmanager
    def track_phase(
        self,
        phase_name: str,
        case_id: Optional[str] = None,
        **extra
    ):
        """
        Context manager para trackear tiempo de ejecución de una fase.
        
        Args:
            phase_name: Nombre de la fase (ej: "analyze_timeline")
            case_id: ID del caso (opcional)
            **extra: Datos adicionales para logging
        
        Usage:
            with monitor.track_phase("analyze_timeline", case_id="CASE_001"):
                # ... código de la fase ...
                pass
        """
        start_time = time.time()
        
        logger.info(
            f"Iniciando fase: {phase_name}",
            case_id=case_id,
            action=f"phase_start_{phase_name}",
            **extra
        )
        
        error_occurred = False
        error_obj = None
        
        try:
            yield
        except Exception as e:
            error_occurred = True
            error_obj = e
            self.metrics.total_errors += 1
            logger.error(
                f"Error en fase: {phase_name}",
                case_id=case_id,
                action=f"phase_error_{phase_name}",
                error=e,
                **extra
            )
            raise
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Registrar tiempo de fase
            if phase_name not in self.metrics.phase_times:
                self.metrics.phase_times[phase_name] = []
            self.metrics.phase_times[phase_name].append(elapsed_ms)
            
            # Log de finalización
            logger.info(
                f"Fase completada: {phase_name}",
                case_id=case_id,
                action=f"phase_end_{phase_name}",
                duration_ms=round(elapsed_ms, 2),
                status="error" if error_occurred else "success",
                **extra
            )
    
    @contextmanager
    def track_case_analysis(self, case_id: str):
        """
        Context manager para trackear análisis completo de un caso.
        
        Args:
            case_id: ID del caso
        
        Usage:
            with monitor.track_case_analysis("CASE_001"):
                # ... análisis del caso ...
                pass
        """
        self._current_case_start = time.time()
        self.metrics.total_cases_analyzed += 1
        
        logger.info(
            f"Iniciando análisis de caso",
            case_id=case_id,
            action="case_analysis_start"
        )
        
        try:
            yield
        except Exception as e:
            self.metrics.total_errors += 1
            logger.error(
                f"Error en análisis de caso",
                case_id=case_id,
                action="case_analysis_error",
                error=e
            )
            raise
        finally:
            if self._current_case_start:
                elapsed_ms = (time.time() - self._current_case_start) * 1000
                
                # Actualizar promedio
                total = self.metrics.total_cases_analyzed
                current_avg = self.metrics.avg_execution_time_ms
                self.metrics.avg_execution_time_ms = (
                    (current_avg * (total - 1) + elapsed_ms) / total
                )
                
                logger.info(
                    f"Análisis de caso completado",
                    case_id=case_id,
                    action="case_analysis_end",
                    duration_ms=round(elapsed_ms, 2),
                    avg_duration_ms=round(self.metrics.avg_execution_time_ms, 2)
                )
                
                self._current_case_start = None
    
    def track_llm_call(
        self,
        agent_name: str,
        case_id: Optional[str] = None,
        success: bool = True,
        duration_ms: Optional[float] = None,
        error: Optional[Exception] = None
    ):
        """
        Registra una llamada a LLM.
        
        Args:
            agent_name: Nombre del agente (ej: "auditor", "prosecutor")
            case_id: ID del caso
            success: Si la llamada fue exitosa
            duration_ms: Duración en milisegundos
            error: Excepción si hubo error
        """
        self.metrics.llm_calls += 1
        
        if success:
            logger.info(
                f"Llamada LLM exitosa: {agent_name}",
                case_id=case_id,
                action="llm_call",
                agent=agent_name,
                duration_ms=duration_ms
            )
        else:
            self.metrics.llm_errors += 1
            logger.error(
                f"Error en llamada LLM: {agent_name}",
                case_id=case_id,
                action="llm_error",
                agent=agent_name,
                error=error
            )
    
    def track_rag_query(
        self,
        rag_type: str,
        case_id: Optional[str] = None,
        success: bool = True,
        num_results: Optional[int] = None,
        duration_ms: Optional[float] = None,
        error: Optional[Exception] = None
    ):
        """
        Registra una consulta RAG.
        
        Args:
            rag_type: Tipo de RAG ("case" o "legal")
            case_id: ID del caso
            success: Si la consulta fue exitosa
            num_results: Número de resultados recuperados
            duration_ms: Duración en milisegundos
            error: Excepción si hubo error
        """
        self.metrics.rag_queries += 1
        
        if success:
            logger.info(
                f"Consulta RAG exitosa: {rag_type}",
                case_id=case_id,
                action="rag_query",
                rag_type=rag_type,
                num_results=num_results,
                duration_ms=duration_ms
            )
        else:
            self.metrics.rag_errors += 1
            logger.error(
                f"Error en consulta RAG: {rag_type}",
                case_id=case_id,
                action="rag_error",
                rag_type=rag_type,
                error=error
            )
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Obtiene métricas agregadas del sistema.
        
        Returns:
            Diccionario con métricas
        """
        # Calcular promedios por fase
        phase_avgs = {}
        for phase, times in self.metrics.phase_times.items():
            if times:
                phase_avgs[phase] = {
                    'avg_ms': round(sum(times) / len(times), 2),
                    'min_ms': round(min(times), 2),
                    'max_ms': round(max(times), 2),
                    'count': len(times)
                }
        
        return {
            'total_cases_analyzed': self.metrics.total_cases_analyzed,
            'total_errors': self.metrics.total_errors,
            'avg_execution_time_ms': round(self.metrics.avg_execution_time_ms, 2),
            'llm': {
                'total_calls': self.metrics.llm_calls,
                'errors': self.metrics.llm_errors,
                'success_rate': (
                    round((self.metrics.llm_calls - self.metrics.llm_errors) / self.metrics.llm_calls * 100, 2)
                    if self.metrics.llm_calls > 0 else 100.0
                )
            },
            'rag': {
                'total_queries': self.metrics.rag_queries,
                'errors': self.metrics.rag_errors,
                'success_rate': (
                    round((self.metrics.rag_queries - self.metrics.rag_errors) / self.metrics.rag_queries * 100, 2)
                    if self.metrics.rag_queries > 0 else 100.0
                )
            },
            'phase_times': phase_avgs,
            'generated_at': datetime.utcnow().isoformat() + 'Z'
        }
    
    def reset_metrics(self):
        """Resetea todas las métricas."""
        self.metrics = MetricsSummary()
        logger.info("Métricas reseteadas", action="metrics_reset")


# Monitor global
_global_monitor: Optional[PerformanceMonitor] = None


def get_monitor() -> PerformanceMonitor:
    """Obtiene el monitor global."""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor


# Atajos
monitor = get_monitor()

