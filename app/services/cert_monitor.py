"""
CERT MONITOR - Monitorización centralizada de eventos [CERT]

Centraliza los logs [CERT] del sistema PHOENIX (RAG + PROSECUTOR)
en un schema estructurado normalizado.

NO modifica comportamiento. SOLO captura y estructura eventos.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class CertComponent(str, Enum):
    """Componentes del sistema que emiten eventos [CERT]."""

    RAG = "RAG"
    PROSECUTOR = "PROSECUTOR"


class CertEventType(str, Enum):
    """Tipos de eventos [CERT] normalizados."""

    # RAG Events
    LLM_CALL_START = "LLM_CALL_START"
    CONTEXT_CHUNKS = "CONTEXT_CHUNKS"
    CITED_CHUNKS = "CITED_CHUNKS"

    # PROSECUTOR Events
    ACCUSATION_START = "ACCUSATION_START"
    ACCUSATION_STRUCTURE_OK = "ACCUSATION_STRUCTURE_OK"
    NO_ACCUSATION = "NO_ACCUSATION"
    EVIDENCE_CHUNKS = "EVIDENCE_CHUNKS"

    # Guardrails
    NARRATIVE_DETECTED = "NARRATIVE_DETECTED"


class CertSeverity(str, Enum):
    """Severidad operativa del evento."""

    INFO = "INFO"  # Ejecución normal esperada
    WARNING = "WARNING"  # Bloqueo controlado, requiere atención
    ERROR = "ERROR"  # Fallo grave, requiere intervención inmediata


@dataclass
class CertEvent:
    """Evento [CERT] normalizado."""

    timestamp: str
    component: CertComponent
    event_type: CertEventType
    severity: CertSeverity
    case_id: Optional[str] = None
    reason: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None

    def to_json(self) -> str:
        """Serializa evento a JSON."""
        return json.dumps(asdict(self), ensure_ascii=False)

    def to_structured_log(self) -> str:
        """Genera línea de log estructurado."""
        parts = [
            "[CERT]",
            f"timestamp={self.timestamp}",
            f"component={self.component.value}",
            f"event={self.event_type.value}",
            f"severity={self.severity.value}",
        ]

        if self.case_id:
            parts.append(f"case_id={self.case_id}")

        if self.reason:
            parts.append(f"reason={self.reason}")

        if self.metadata:
            metadata_str = json.dumps(self.metadata, ensure_ascii=False)
            parts.append(f"metadata={metadata_str}")

        return " ".join(parts)


# ============================
# CLASIFICACIÓN DE SEVERIDAD
# ============================

SEVERITY_MAP: dict[tuple[CertComponent, CertEventType, Optional[str]], CertSeverity] = {
    # RAG - Ejecución normal
    (CertComponent.RAG, CertEventType.LLM_CALL_START, None): CertSeverity.INFO,
    (CertComponent.RAG, CertEventType.CONTEXT_CHUNKS, None): CertSeverity.INFO,
    (CertComponent.RAG, CertEventType.CITED_CHUNKS, None): CertSeverity.INFO,
    # PROSECUTOR - Ejecución normal
    (CertComponent.PROSECUTOR, CertEventType.ACCUSATION_START, None): CertSeverity.INFO,
    (CertComponent.PROSECUTOR, CertEventType.ACCUSATION_STRUCTURE_OK, None): CertSeverity.INFO,
    (CertComponent.PROSECUTOR, CertEventType.EVIDENCE_CHUNKS, None): CertSeverity.INFO,
    # PROSECUTOR - Bloqueos controlados (WARNING)
    (CertComponent.PROSECUTOR, CertEventType.NO_ACCUSATION, "NO_EVIDENCE"): CertSeverity.WARNING,
    (
        CertComponent.PROSECUTOR,
        CertEventType.NO_ACCUSATION,
        "PARTIAL_EVIDENCE",
    ): CertSeverity.WARNING,
    (CertComponent.PROSECUTOR, CertEventType.NO_ACCUSATION, "LOW_CONFIDENCE"): CertSeverity.WARNING,
    (
        CertComponent.PROSECUTOR,
        CertEventType.NO_ACCUSATION,
        "MISSING_KEY_DOCUMENTS",
    ): CertSeverity.WARNING,
    # Guardrails - Fallos graves (ERROR)
    (CertComponent.PROSECUTOR, CertEventType.NARRATIVE_DETECTED, None): CertSeverity.ERROR,
}


def classify_severity(
    component: CertComponent,
    event_type: CertEventType,
    reason: Optional[str] = None,
) -> CertSeverity:
    """
    Clasifica la severidad operativa de un evento.

    Args:
        component: Componente que emite el evento
        event_type: Tipo de evento
        reason: Razón específica (si aplica)

    Returns:
        Severidad operativa del evento
    """
    key = (component, event_type, reason)
    return SEVERITY_MAP.get(key, CertSeverity.INFO)


# ============================
# CREACIÓN DE EVENTOS
# ============================


def create_rag_llm_call_event(case_id: str) -> CertEvent:
    """Crea evento LLM_CALL_START del RAG."""
    return CertEvent(
        timestamp=datetime.utcnow().isoformat(),
        component=CertComponent.RAG,
        event_type=CertEventType.LLM_CALL_START,
        severity=CertSeverity.INFO,
        case_id=case_id,
    )


def create_rag_context_chunks_event(case_id: str, chunk_ids: list[str]) -> CertEvent:
    """Crea evento CONTEXT_CHUNKS del RAG."""
    return CertEvent(
        timestamp=datetime.utcnow().isoformat(),
        component=CertComponent.RAG,
        event_type=CertEventType.CONTEXT_CHUNKS,
        severity=CertSeverity.INFO,
        case_id=case_id,
        metadata={"chunk_ids": chunk_ids, "count": len(chunk_ids)},
    )


def create_rag_cited_chunks_event(case_id: str, chunk_ids: list[str]) -> CertEvent:
    """Crea evento CITED_CHUNKS del RAG."""
    return CertEvent(
        timestamp=datetime.utcnow().isoformat(),
        component=CertComponent.RAG,
        event_type=CertEventType.CITED_CHUNKS,
        severity=CertSeverity.INFO,
        case_id=case_id,
        metadata={"chunk_ids": chunk_ids, "count": len(chunk_ids)},
    )


def create_prosecutor_accusation_start_event(
    case_id: str,
    articulo: str,
) -> CertEvent:
    """Crea evento ACCUSATION_START del PROSECUTOR."""
    return CertEvent(
        timestamp=datetime.utcnow().isoformat(),
        component=CertComponent.PROSECUTOR,
        event_type=CertEventType.ACCUSATION_START,
        severity=CertSeverity.INFO,
        case_id=case_id,
        metadata={"articulo": articulo},
    )


def create_prosecutor_no_accusation_event(
    case_id: str,
    reason: str,
    ground: Optional[str] = None,
    missing: Optional[list[str]] = None,
) -> CertEvent:
    """Crea evento NO_ACCUSATION del PROSECUTOR."""
    severity = classify_severity(
        CertComponent.PROSECUTOR,
        CertEventType.NO_ACCUSATION,
        reason,
    )

    metadata = {}
    if ground:
        metadata["ground"] = ground
    if missing:
        metadata["missing"] = missing

    return CertEvent(
        timestamp=datetime.utcnow().isoformat(),
        component=CertComponent.PROSECUTOR,
        event_type=CertEventType.NO_ACCUSATION,
        severity=severity,
        case_id=case_id,
        reason=reason,
        metadata=metadata if metadata else None,
    )


def create_prosecutor_structure_ok_event(case_id: str) -> CertEvent:
    """Crea evento ACCUSATION_STRUCTURE_OK del PROSECUTOR."""
    return CertEvent(
        timestamp=datetime.utcnow().isoformat(),
        component=CertComponent.PROSECUTOR,
        event_type=CertEventType.ACCUSATION_STRUCTURE_OK,
        severity=CertSeverity.INFO,
        case_id=case_id,
    )


def create_prosecutor_evidence_chunks_event(
    case_id: str,
    chunk_ids: list[str],
) -> CertEvent:
    """Crea evento EVIDENCE_CHUNKS del PROSECUTOR."""
    return CertEvent(
        timestamp=datetime.utcnow().isoformat(),
        component=CertComponent.PROSECUTOR,
        event_type=CertEventType.EVIDENCE_CHUNKS,
        severity=CertSeverity.INFO,
        case_id=case_id,
        metadata={"chunk_ids": chunk_ids, "count": len(chunk_ids)},
    )


def create_narrative_detected_event(component: CertComponent, case_id: str) -> CertEvent:
    """Crea evento NARRATIVE_DETECTED (ERROR grave)."""
    return CertEvent(
        timestamp=datetime.utcnow().isoformat(),
        component=component,
        event_type=CertEventType.NARRATIVE_DETECTED,
        severity=CertSeverity.ERROR,
        case_id=case_id,
    )


# ============================
# MAPEO EVENTO → ACCIÓN
# ============================


@dataclass
class OperationalAction:
    """Acción operativa recomendada para un evento."""

    event_type: str
    severity: str
    business_meaning: str
    recommended_action: str
    responsible: str
    prohibited: str


OPERATIONAL_MAP: dict[tuple[CertComponent, CertEventType, Optional[str]], OperationalAction] = {
    # RAG - Ejecución normal
    (CertComponent.RAG, CertEventType.LLM_CALL_START, None): OperationalAction(
        event_type="RAG: LLM llamado",
        severity="INFO",
        business_meaning="El sistema está generando una respuesta con evidencia suficiente.",
        recommended_action="Ninguna. Ejecución normal.",
        responsible="Sistema",
        prohibited="NO interrumpir el flujo.",
    ),
    # PROSECUTOR - Bloqueo por falta de evidencia
    (CertComponent.PROSECUTOR, CertEventType.NO_ACCUSATION, "NO_EVIDENCE"): OperationalAction(
        event_type="PROSECUTOR: Sin evidencia",
        severity="WARNING",
        business_meaning="No hay documentación suficiente para evaluar responsabilidades.",
        recommended_action="Solicitar al cliente los documentos listados en 'evidencia_requerida'.",
        responsible="Analista legal",
        prohibited="NO generar informe hasta recibir documentos.",
    ),
    (CertComponent.PROSECUTOR, CertEventType.NO_ACCUSATION, "PARTIAL_EVIDENCE"): OperationalAction(
        event_type="PROSECUTOR: Evidencia parcial",
        severity="WARNING",
        business_meaning="Hay indicios pero faltan documentos clave para concluir.",
        recommended_action="Solicitar específicamente los documentos listados en 'missing'.",
        responsible="Analista legal",
        prohibited="NO acusar ni emitir conclusiones hasta completar evidencia.",
    ),
    (CertComponent.PROSECUTOR, CertEventType.NO_ACCUSATION, "LOW_CONFIDENCE"): OperationalAction(
        event_type="PROSECUTOR: Baja confianza",
        severity="WARNING",
        business_meaning="La calidad de los documentos aportados es insuficiente.",
        recommended_action="Solicitar documentos originales o con mayor calidad (legibles, completos).",
        responsible="Analista legal",
        prohibited="NO proceder con documentos de baja calidad.",
    ),
    # PROSECUTOR - Acusación generada
    (CertComponent.PROSECUTOR, CertEventType.ACCUSATION_START, None): OperationalAction(
        event_type="PROSECUTOR: Acusación iniciada",
        severity="INFO",
        business_meaning="Se ha identificado un posible incumplimiento con evidencia completa.",
        recommended_action="Revisar la acusación generada. Validar severidad y evidencias citadas.",
        responsible="Abogado senior",
        prohibited="NO asumir culpabilidad automática. La acusación requiere revisión legal.",
    ),
    # Guardrail - Narrativa detectada
    (CertComponent.PROSECUTOR, CertEventType.NARRATIVE_DETECTED, None): OperationalAction(
        event_type="PROSECUTOR: Narrativa detectada",
        severity="ERROR",
        business_meaning="El sistema intentó generar texto especulativo (violación de protocolo).",
        recommended_action="Escalar a ingeniería. Revisar logs. NO usar la salida generada.",
        responsible="Tech lead + Legal",
        prohibited="NO entregar al cliente. NO usar como evidencia.",
    ),
}


def get_operational_action(
    component: CertComponent,
    event_type: CertEventType,
    reason: Optional[str] = None,
) -> Optional[OperationalAction]:
    """
    Obtiene la acción operativa recomendada para un evento.

    Args:
        component: Componente que emite el evento
        event_type: Tipo de evento
        reason: Razón específica (si aplica)

    Returns:
        Acción operativa o None si no está mapeada
    """
    key = (component, event_type, reason)
    return OPERATIONAL_MAP.get(key)
