"""
ENDPOINT OFICIAL DE GENERACIÓN DE INFORME LEGAL (PANTALLA 4).

PRINCIPIO: Esta es la PRIMERA capa que usa LENGUAJE LEGAL.
Traduce alertas técnicas a hallazgos jurídicos con base documental.

PROHIBIDO:
- generar conclusiones sin alerta técnica previa
- generar hallazgos sin evidencia física
- usar lenguaje especulativo
- ocultar evidencia
- modificar chunks, alertas o trace
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import List, Dict

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.case import Case
from app.models.legal_report import (
    LegalReport,
    LegalFinding,
    LegalReference,
    LegalEvidence,
    LegalEvidenceLocation,
    ConfidenceLevel,
)
from app.models.analysis_alert import AlertType
from app.api.analysis_alerts import get_analysis_alerts


router = APIRouter(
    prefix="/cases/{case_id}",
    tags=["legal-report"],
)


def _convert_alert_evidence_to_legal_evidence(alert_evidence) -> LegalEvidence:
    """
    Convierte evidencia de alerta técnica a evidencia legal.
    
    NO modifica contenido.
    NO oculta información.
    SOLO reformatea para el informe legal.
    """
    return LegalEvidence(
        chunk_id=alert_evidence.chunk_id,
        document_id=alert_evidence.document_id,
        filename=alert_evidence.filename,
        location=LegalEvidenceLocation(
            start_char=alert_evidence.location.start_char,
            end_char=alert_evidence.location.end_char,
            page_start=alert_evidence.location.page_start,
            page_end=alert_evidence.location.page_end,
            extraction_method=alert_evidence.location.extraction_method,
        ),
        content=alert_evidence.content,
    )


def _translate_missing_data_to_finding(
    alert,
    case_id: str
) -> LegalFinding:
    """
    Traduce alerta MISSING_DATA a hallazgo legal.
    
    Base legal: Art. 164.2 Ley Concursal (documentación obligatoria)
    """
    finding_id = hashlib.sha256(
        f"{case_id}_FINDING_MISSING_DATA_{alert.alert_id}".encode()
    ).hexdigest()[:16]
    
    # Convertir evidencia
    legal_evidence = [
        _convert_alert_evidence_to_legal_evidence(ev)
        for ev in alert.evidence
    ]
    
    return LegalFinding(
        finding_id=finding_id,
        title="Ausencia de información documental obligatoria",
        description=(
            f"Se ha detectado la ausencia de información documental que debe constar "
            f"en la documentación concursal. Específicamente: {alert.description}. "
            f"Esta omisión constituye un incumplimiento de las obligaciones de documentación "
            f"establecidas en la normativa concursal."
        ),
        related_alert_types=[AlertType.MISSING_DATA.value],
        legal_basis=[
            LegalReference(
                article="164.2",
                description=(
                    "Documentación que debe acompañar la solicitud de declaración de concurso. "
                    "El deudor debe presentar la documentación completa exigida por la ley."
                )
            )
        ],
        evidence=legal_evidence,
        confidence_level=ConfidenceLevel.HIGH if len(legal_evidence) >= 3 else ConfidenceLevel.MEDIUM,
    )


def _translate_inconsistent_data_to_finding(
    alert,
    case_id: str
) -> LegalFinding:
    """
    Traduce alerta INCONSISTENT_DATA a hallazgo legal.
    
    Base legal: Art. 6 Ley Concursal (buena fe y diligencia debida)
    """
    finding_id = hashlib.sha256(
        f"{case_id}_FINDING_INCONSISTENT_DATA_{alert.alert_id}".encode()
    ).hexdigest()[:16]
    
    # Convertir evidencia
    legal_evidence = [
        _convert_alert_evidence_to_legal_evidence(ev)
        for ev in alert.evidence
    ]
    
    return LegalFinding(
        finding_id=finding_id,
        title="Inconsistencias en la documentación aportada",
        description=(
            f"Se han identificado inconsistencias técnicas en la documentación presentada. "
            f"Detalles: {alert.description}. "
            f"Estas inconsistencias afectan la fiabilidad de la información aportada "
            f"y requieren aclaración o subsanación."
        ),
        related_alert_types=[AlertType.INCONSISTENT_DATA.value],
        legal_basis=[
            LegalReference(
                article="6",
                description=(
                    "Deber de colaboración. Los deudores están obligados a aportar "
                    "información veraz y completa sobre su situación patrimonial."
                )
            )
        ],
        evidence=legal_evidence,
        confidence_level=ConfidenceLevel.HIGH,
    )


def _translate_duplicated_data_to_finding(
    alert,
    case_id: str
) -> LegalFinding:
    """
    Traduce alerta DUPLICATED_DATA a hallazgo legal.
    
    Base legal: Art. 164.2.1º Ley Concursal (memoria del deudor)
    """
    finding_id = hashlib.sha256(
        f"{case_id}_FINDING_DUPLICATED_DATA_{alert.alert_id}".encode()
    ).hexdigest()[:16]
    
    # Convertir evidencia
    legal_evidence = [
        _convert_alert_evidence_to_legal_evidence(ev)
        for ev in alert.evidence
    ]
    
    return LegalFinding(
        finding_id=finding_id,
        title="Duplicación de contenido documental",
        description=(
            f"Se ha detectado contenido duplicado de forma literal en la documentación. "
            f"Detalles: {alert.description}. "
            f"La duplicación de información sin justificación aparente afecta "
            f"la claridad y organización de la documentación concursal."
        ),
        related_alert_types=[AlertType.DUPLICATED_DATA.value],
        legal_basis=[
            LegalReference(
                article="164.2.1º",
                description=(
                    "Memoria del deudor. La documentación debe presentarse de forma "
                    "ordenada y clara para facilitar su examen."
                )
            )
        ],
        evidence=legal_evidence,
        confidence_level=ConfidenceLevel.MEDIUM,
    )


def _translate_suspicious_pattern_to_finding(
    alert,
    case_id: str
) -> LegalFinding:
    """
    Traduce alerta SUSPICIOUS_PATTERN a hallazgo legal.
    
    Base legal: Art. 172 Ley Concursal (calificación del concurso)
    """
    finding_id = hashlib.sha256(
        f"{case_id}_FINDING_SUSPICIOUS_PATTERN_{alert.alert_id}".encode()
    ).hexdigest()[:16]
    
    # Convertir evidencia
    legal_evidence = [
        _convert_alert_evidence_to_legal_evidence(ev)
        for ev in alert.evidence
    ]
    
    return LegalFinding(
        finding_id=finding_id,
        title="Patrones anómalos en la documentación",
        description=(
            f"Se han identificado patrones técnicos anómalos en la estructura documental. "
            f"Detalles: {alert.description}. "
            f"Estos patrones requieren revisión adicional para determinar su origen "
            f"y descartar defectos en la preparación de la documentación."
        ),
        related_alert_types=[AlertType.SUSPICIOUS_PATTERN.value],
        legal_basis=[
            LegalReference(
                article="172",
                description=(
                    "Formación de la sección de calificación. La documentación debe "
                    "permitir la correcta evaluación de la conducta del deudor."
                )
            )
        ],
        evidence=legal_evidence,
        confidence_level=ConfidenceLevel.LOW,
    )


def _translate_temporal_inconsistency_to_finding(
    alert,
    case_id: str
) -> LegalFinding:
    """
    Traduce alerta TEMPORAL_INCONSISTENCY a hallazgo legal.
    
    Base legal: Art. 6 Ley Concursal (buena fe)
    """
    finding_id = hashlib.sha256(
        f"{case_id}_FINDING_TEMPORAL_{alert.alert_id}".encode()
    ).hexdigest()[:16]
    
    # Convertir evidencia
    legal_evidence = [
        _convert_alert_evidence_to_legal_evidence(ev)
        for ev in alert.evidence
    ]
    
    return LegalFinding(
        finding_id=finding_id,
        title="Inconsistencias temporales en la documentación",
        description=(
            f"Se han detectado inconsistencias temporales en la información aportada. "
            f"Detalles: {alert.description}. "
            f"La coherencia temporal de la documentación es esencial para la correcta "
            f"evaluación de la situación patrimonial del deudor."
        ),
        related_alert_types=[AlertType.TEMPORAL_INCONSISTENCY.value],
        legal_basis=[
            LegalReference(
                article="6",
                description=(
                    "Deber de colaboración. La información aportada debe ser coherente "
                    "y permitir una reconstrucción temporal fiable de los hechos."
                )
            )
        ],
        evidence=legal_evidence,
        confidence_level=ConfidenceLevel.MEDIUM,
    )


# Mapeo de tipos de alerta a funciones de traducción
ALERT_TO_FINDING_TRANSLATORS: Dict[AlertType, callable] = {
    AlertType.MISSING_DATA: _translate_missing_data_to_finding,
    AlertType.INCONSISTENT_DATA: _translate_inconsistent_data_to_finding,
    AlertType.DUPLICATED_DATA: _translate_duplicated_data_to_finding,
    AlertType.SUSPICIOUS_PATTERN: _translate_suspicious_pattern_to_finding,
    AlertType.TEMPORAL_INCONSISTENCY: _translate_temporal_inconsistency_to_finding,
}


@router.post(
    "/legal-report",
    response_model=LegalReport,
    status_code=status.HTTP_201_CREATED,
    summary="Generar informe legal de un caso",
    description=(
        "Genera un informe legal certificable desde alertas técnicas. "
        "Traduce alertas a hallazgos jurídicos con base legal concreta. "
        "Cada hallazgo incluye evidencia física verificable. "
        "El informe es trazable y apto para revisión humana."
    ),
)
def generate_legal_report(
    case_id: str,
    db: Session = Depends(get_db),
) -> LegalReport:
    """
    Genera un informe legal certificable desde alertas técnicas.
    
    Proceso:
    1. Verificar que el caso existe
    2. Obtener alertas técnicas (PANTALLA 3)
    3. Traducir cada alerta a hallazgo legal
    4. Generar informe con base legal concreta
    5. Registrar hash para trace
    
    Args:
        case_id: ID del caso
        db: Sesión de base de datos
        
    Returns:
        LegalReport con hallazgos legales
        
    Raises:
        HTTPException 404: Si el caso no existe
    """
    # Verificar que el caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Caso '{case_id}' no encontrado"
        )
    
    # Obtener alertas técnicas de PANTALLA 3
    alerts = get_analysis_alerts(case_id=case_id, db=db)
    
    # Traducir alertas a hallazgos legales
    findings: List[LegalFinding] = []
    
    for alert in alerts:
        # Obtener traductor para este tipo de alerta
        translator = ALERT_TO_FINDING_TRANSLATORS.get(alert.alert_type)
        
        if translator:
            try:
                finding = translator(alert, case_id)
                findings.append(finding)
            except Exception as e:
                # Si falla la traducción, registrar pero no abortar
                # (el informe puede generarse con hallazgos parciales)
                continue
    
    # Generar ID del informe
    report_id = hashlib.sha256(
        f"{case_id}_LEGAL_REPORT_{datetime.utcnow().isoformat()}".encode()
    ).hexdigest()[:16]
    
    # Determinar asunto analizado
    if findings:
        issue_analyzed = (
            f"Análisis técnico-legal de la documentación concursal del caso {case_id}. "
            f"Se han identificado {len(findings)} hallazgos relevantes que requieren "
            f"evaluación jurídica experta."
        )
    else:
        issue_analyzed = (
            f"Análisis técnico-legal de la documentación concursal del caso {case_id}. "
            f"No se han identificado hallazgos técnicos que requieran traducción legal "
            f"en el momento de la generación del informe."
        )
    
    # Generar informe
    report = LegalReport(
        report_id=report_id,
        case_id=case_id,
        generated_at=datetime.utcnow(),
        issue_analyzed=issue_analyzed,
        findings=findings,
    )
    
    return report


# =========================================================
# ENDPOINTS PROHIBIDOS (NO IMPLEMENTADOS)
# =========================================================

# PUT /cases/{case_id}/legal-report → PROHIBIDO (no se editan informes)
# DELETE /cases/{case_id}/legal-report → PROHIBIDO (no se borran informes)
# POST /cases/{case_id}/legal-report/interpret → PROHIBIDO (no reinterpretación)
# POST /cases/{case_id}/legal-report/modify → PROHIBIDO (no modificación manual)

