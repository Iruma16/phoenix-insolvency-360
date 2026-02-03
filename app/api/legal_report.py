"""
ENDPOINT DE GENERACIÓN DE INFORME LEGAL (VERSIÓN SIMPLIFICADA).

Genera informe legal básico desde alertas técnicas del caso.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.analysis_alerts import get_analysis_alerts
from app.core.database import get_db
from app.models.case import Case
from app.models.legal_output import (
    DocumentalEvidence,
    EvidenceLocation,
    ExtractionMethod,
    LegalFinding,
    LegalReport,
)

router = APIRouter(
    prefix="/cases/{case_id}",
    tags=["legal-report"],
)


def _convert_alert_to_finding(alert, case_id: str) -> LegalFinding:
    """
    Convierte alerta técnica a hallazgo legal simplificado.
    """
    # Construir evidencias desde la alerta
    evidence_list = []

    for alert_ev in alert.evidence[:3]:  # Máximo 3 evidencias
        try:
            evidence = DocumentalEvidence(
                chunk_id=alert_ev.chunk_id,
                document_id=alert_ev.document_id,
                location=EvidenceLocation(
                    page_start=alert_ev.location.page_start,
                    page_end=alert_ev.location.page_end,
                    start_char=alert_ev.location.start_char,
                    end_char=alert_ev.location.end_char,
                    extraction_method=ExtractionMethod(alert_ev.location.extraction_method),
                ),
                content=alert_ev.content,
                filename=alert_ev.filename,
            )
            evidence_list.append(evidence)
        except Exception:
            # Si falla una evidencia, continuar con las demás
            continue

    if not evidence_list:
        # Si no hay evidencias válidas, crear una dummy
        evidence_list = [
            DocumentalEvidence(
                chunk_id="unknown",
                document_id="unknown",
                location=EvidenceLocation(
                    start_char=0, end_char=1, extraction_method=ExtractionMethod.UNKNOWN
                ),
                content="Evidencia no disponible",
                filename="N/A",
            )
        ]

    # Generar statement desde descripción de alerta
    statement = f"Se detectó: {alert.description}"

    # Nota de confianza
    confidence_note = (
        f"Alerta técnica tipo {alert.alert_type.value} con nivel {alert.alert_level.value}"
    )

    return LegalFinding(
        statement=statement, evidence=evidence_list, confidence_note=confidence_note
    )


@router.post(
    "/legal-report",
    response_model=LegalReport,
    status_code=status.HTTP_201_CREATED,
    summary="Generar informe legal de un caso",
    description="Genera informe legal simplificado desde alertas técnicas del caso.",
)
def generate_legal_report(
    case_id: str,
    db: Session = Depends(get_db),
) -> LegalReport:
    """
    Genera informe legal simplificado desde alertas técnicas.

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
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado"
        )

    # Obtener alertas técnicas
    alerts = get_analysis_alerts(case_id=case_id, db=db)

    # Convertir alertas a hallazgos
    findings: list[LegalFinding] = []

    for alert in alerts:
        try:
            finding = _convert_alert_to_finding(alert, case_id)
            findings.append(finding)
        except Exception as e:
            # Si falla la conversión, continuar con las demás
            print(f"Error convirtiendo alerta {alert.alert_id}: {e}")
            continue

    # Si no hay hallazgos, crear uno por defecto
    if not findings:
        findings = [
            LegalFinding(
                statement="No se detectaron alertas técnicas significativas en el análisis preliminar del caso.",
                evidence=[
                    DocumentalEvidence(
                        chunk_id="system",
                        document_id="system",
                        location=EvidenceLocation(
                            start_char=0, end_char=1, extraction_method=ExtractionMethod.UNKNOWN
                        ),
                        content="Análisis del sistema",
                        filename="Sistema Phoenix Legal",
                    )
                ],
                confidence_note="Resultado del análisis automatizado completo",
            )
        ]

    # Construir asunto analizado
    issue_analyzed = (
        f"Análisis técnico-legal preliminar de la documentación concursal del caso '{case.name}' (ID: {case_id}). "
        f"Se han identificado {len(findings)} hallazgo(s) relevante(s) que requieren evaluación legal experta."
    )

    # Generar informe
    report = LegalReport(
        case_id=case_id,
        issue_analyzed=issue_analyzed,
        findings=findings,
        generated_at=datetime.utcnow(),
        total_documents_analyzed=len(case.documents) if hasattr(case, "documents") else 0,
    )

    return report
