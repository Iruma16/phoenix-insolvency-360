"""
CONSTRUCTOR DE SALIDA LEGAL FORMAL (FASE 5 - ENDURECIMIENTO 5).

PRINCIPIO: La salida legal debe ser construida y validada ANTES de ser entregada.
NO se permite salida parcial, degradada o sin validación.

Este módulo valida que toda afirmación tenga respaldo documental verificable.
"""
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.models.legal_output import (
    LegalReport,
    LegalFinding,
    DocumentalEvidence,
    EvidenceLocation,
    ExtractionMethod,
    LegalOutputError,
)
from app.models.document_chunk import DocumentChunk


def validate_chunk_exists(db: Session, chunk_id: str, case_id: str) -> DocumentChunk:
    """
    Valida que un chunk existe y pertenece al caso.
    
    FAIL HARD si:
    - Chunk no existe
    - Chunk no pertenece al case_id
    
    Args:
        db: Sesión de base de datos
        chunk_id: ID del chunk a validar
        case_id: ID del caso
        
    Returns:
        DocumentChunk validado
        
    Raises:
        LegalOutputError: Si chunk no existe o no pertenece al caso
    """
    chunk = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.chunk_id == chunk_id,
            DocumentChunk.case_id == case_id,
        )
        .first()
    )
    
    if not chunk:
        raise LegalOutputError(
            reason=f"Chunk {chunk_id} no existe o no pertenece al caso {case_id}"
        )
    
    return chunk


def build_evidence_from_chunk(chunk: DocumentChunk) -> DocumentalEvidence:
    """
    Construye DocumentalEvidence desde un DocumentChunk validado.
    
    FAIL HARD si:
    - Chunk no tiene location completa
    - Offsets inválidos
    
    Args:
        chunk: DocumentChunk con location válida
        
    Returns:
        DocumentalEvidence construida
        
    Raises:
        LegalOutputError: Si chunk no tiene location válida
    """
    # Validar que chunk tiene location
    if chunk.start_char is None:
        raise LegalOutputError(
            reason=f"Chunk {chunk.chunk_id} sin start_char"
        )
    
    if chunk.end_char is None:
        raise LegalOutputError(
            reason=f"Chunk {chunk.chunk_id} sin end_char"
        )
    
    if not chunk.extraction_method:
        raise LegalOutputError(
            reason=f"Chunk {chunk.chunk_id} sin extraction_method"
        )
    
    # Construir location
    try:
        location = EvidenceLocation(
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            extraction_method=ExtractionMethod(chunk.extraction_method),
        )
    except ValueError as e:
        raise LegalOutputError(
            reason=f"Location inválida en chunk {chunk.chunk_id}: {e}"
        )
    
    # Obtener filename si existe
    filename = None
    if chunk.document and hasattr(chunk.document, 'filename'):
        filename = chunk.document.filename
    
    # Construir evidencia
    return DocumentalEvidence(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        location=location,
        content=chunk.content,
        filename=filename,
    )


def build_legal_report(
    db: Session,
    case_id: str,
    issue_analyzed: str,
    findings_data: List[Dict[str, Any]],
) -> LegalReport:
    """
    Construye y valida un LegalReport completo.
    
    FAIL HARD si:
    - Algún finding no tiene evidencia
    - Alguna evidencia referencia chunk inexistente
    - Algún chunk no tiene location completa
    
    Args:
        db: Sesión de base de datos
        case_id: ID del caso
        issue_analyzed: Cuestión jurídica analizada
        findings_data: Lista de findings con formato:
            [
                {
                    "statement": "Afirmación objetiva",
                    "evidence_chunk_ids": ["chunk_001", "chunk_002"],
                    "confidence_note": "Nota opcional"
                },
                ...
            ]
            
    Returns:
        LegalReport validado
        
    Raises:
        LegalOutputError: Si alguna validación falla
    """
    # Validar que hay findings
    if not findings_data or len(findings_data) == 0:
        raise LegalOutputError(
            reason="No se pueden generar findings sin datos"
        )
    
    # Construir findings
    findings = []
    total_chunks_used = set()
    
    for idx, finding_data in enumerate(findings_data):
        statement = finding_data.get("statement")
        evidence_chunk_ids = finding_data.get("evidence_chunk_ids", [])
        confidence_note = finding_data.get("confidence_note")
        
        # Validar statement
        if not statement or len(statement.strip()) < 10:
            raise LegalOutputError(
                reason=f"Finding {idx+1} con statement inválido o muy corto"
            )
        
        # Validar que hay chunk_ids
        if not evidence_chunk_ids or len(evidence_chunk_ids) == 0:
            raise LegalOutputError(
                reason=f"Finding {idx+1} sin evidencia (chunk_ids vacío)"
            )
        
        # Construir evidencias
        evidences = []
        for chunk_id in evidence_chunk_ids:
            # Validar que chunk existe y pertenece al caso
            chunk = validate_chunk_exists(db, chunk_id, case_id)
            
            # Construir evidencia desde chunk
            evidence = build_evidence_from_chunk(chunk)
            evidences.append(evidence)
            total_chunks_used.add(chunk_id)
        
        # Construir finding
        finding = LegalFinding(
            statement=statement.strip(),
            evidence=evidences,
            confidence_note=confidence_note,
        )
        findings.append(finding)
    
    # Construir reporte
    report = LegalReport(
        case_id=case_id,
        issue_analyzed=issue_analyzed.strip(),
        findings=findings,
        generated_at=datetime.utcnow(),
        total_chunks_used=len(total_chunks_used),
    )
    
    return report


def validate_legal_report(report: LegalReport) -> None:
    """
    Valida que un LegalReport cumple todos los requisitos.
    
    FAIL HARD si:
    - Reporte sin findings
    - Finding sin evidencia
    - Evidencia sin location completa
    
    Args:
        report: LegalReport a validar
        
    Raises:
        LegalOutputError: Si validación falla
    """
    # Validar que hay findings
    if not report.findings or len(report.findings) == 0:
        raise LegalOutputError(
            reason="Reporte sin findings"
        )
    
    # Validar cada finding
    for idx, finding in enumerate(report.findings):
        # Validar statement
        if not finding.statement or len(finding.statement.strip()) < 10:
            raise LegalOutputError(
                reason=f"Finding {idx+1} con statement inválido"
            )
        
        # Validar que hay evidencia
        if not finding.evidence or len(finding.evidence) == 0:
            raise LegalOutputError(
                reason=f"Finding {idx+1} sin evidencia"
            )
        
        # Validar cada evidencia
        for ev_idx, evidence in enumerate(finding.evidence):
            # Validar IDs
            if not evidence.chunk_id or not evidence.document_id:
                raise LegalOutputError(
                    reason=f"Finding {idx+1}, evidencia {ev_idx+1} sin IDs"
                )
            
            # Validar location
            if not evidence.location:
                raise LegalOutputError(
                    reason=f"Finding {idx+1}, evidencia {ev_idx+1} sin location"
                )
            
            # Validar offsets
            if evidence.location.start_char >= evidence.location.end_char:
                raise LegalOutputError(
                    reason=f"Finding {idx+1}, evidencia {ev_idx+1} con offsets inválidos"
                )
            
            # Validar content
            if not evidence.content or len(evidence.content.strip()) == 0:
                raise LegalOutputError(
                    reason=f"Finding {idx+1}, evidencia {ev_idx+1} sin content"
                )

