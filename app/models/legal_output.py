"""
CONTRATO DE SALIDA LEGAL FORMAL (FASE 5 - ENDURECIMIENTO 5).

PRINCIPIO: Toda afirmación jurídica DEBE estar respaldada por evidencia documental.
NO se permite texto especulativo, interpretativo u opinativo.

Este modelo es el ÚNICO formato válido para conclusiones legales del sistema.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field, field_validator

from app.core.exceptions import PhoenixException, ErrorSeverity


LEGAL_OUTPUT_SCHEMA_VERSION = "1.0.0"


class ExtractionMethod(str, Enum):
    """Método de extracción del texto (debe coincidir con DocumentChunk)."""
    PDF_TEXT = "pdf_text"
    OCR = "ocr"
    TABLE = "table"
    DOCX_TEXT = "docx_text"
    TXT = "txt"
    UNKNOWN = "unknown"


class EvidenceLocation(BaseModel):
    """
    Ubicación física exacta de la evidencia en el documento original.
    
    OBLIGATORIO: Toda evidencia debe ser localizable físicamente.
    """
    page_start: Optional[int] = Field(
        None,
        description="Página de inicio (1-indexed, None solo si formato no lo permite)",
        ge=1
    )
    page_end: Optional[int] = Field(
        None,
        description="Página de fin (1-indexed)",
        ge=1
    )
    start_char: int = Field(
        ...,
        description="Offset de inicio en texto original (OBLIGATORIO)",
        ge=0
    )
    end_char: int = Field(
        ...,
        description="Offset de fin en texto original (OBLIGATORIO)",
        ge=0
    )
    extraction_method: ExtractionMethod = Field(
        ...,
        description="Método de extracción del texto (OBLIGATORIO)"
    )
    
    @field_validator('end_char')
    @classmethod
    def validate_char_range(cls, v: int, info) -> int:
        """REGLA DURA: start_char < end_char"""
        start_char = info.data.get('start_char')
        if start_char is not None and v <= start_char:
            raise ValueError(f"end_char ({v}) debe ser > start_char ({start_char})")
        return v
    
    @field_validator('page_end')
    @classmethod
    def validate_page_range(cls, v: Optional[int], info) -> Optional[int]:
        """REGLA DURA: page_start <= page_end (si ambos existen)"""
        if v is None:
            return v
        page_start = info.data.get('page_start')
        if page_start is not None and v < page_start:
            raise ValueError(f"page_end ({v}) debe ser >= page_start ({page_start})")
        return v
    
    model_config = {"extra": "forbid"}


class DocumentalEvidence(BaseModel):
    """
    Evidencia documental que respalda una afirmación legal.
    
    CONTRATO DURO:
    - Toda evidencia debe tener chunk_id, document_id y location
    - Location debe ser completa y válida
    - content debe ser el texto literal extraído
    """
    chunk_id: str = Field(
        ...,
        description="ID único del chunk (trazabilidad)",
        min_length=1
    )
    document_id: str = Field(
        ...,
        description="ID del documento origen",
        min_length=1
    )
    location: EvidenceLocation = Field(
        ...,
        description="Ubicación física exacta en el documento"
    )
    content: str = Field(
        ...,
        description="Texto literal extraído del documento",
        min_length=1
    )
    filename: Optional[str] = Field(
        None,
        description="Nombre del archivo origen (para auditoría)"
    )
    
    model_config = {"extra": "forbid"}


class LegalFinding(BaseModel):
    """
    Hallazgo legal: afirmación objetiva respaldada por evidencia documental.
    
    REGLAS DURAS:
    - statement NO puede ser interpretativo ni especulativo
    - evidence NO puede estar vacía
    - Toda afirmación debe ser verificable físicamente en los documentos
    """
    statement: str = Field(
        ...,
        description="Afirmación objetiva, verificable y no interpretativa",
        min_length=10
    )
    evidence: List[DocumentalEvidence] = Field(
        ...,
        description="Evidencias documentales que respaldan la afirmación",
        min_length=1
    )
    confidence_note: Optional[str] = Field(
        None,
        description="Nota sobre limitaciones de la evidencia (opcional)"
    )
    
    @field_validator('evidence')
    @classmethod
    def validate_evidence_not_empty(cls, v: List[DocumentalEvidence]) -> List[DocumentalEvidence]:
        """REGLA DURA: Todo finding debe tener al menos una evidencia"""
        if not v or len(v) == 0:
            raise ValueError("Finding sin evidencia no permitido")
        return v
    
    model_config = {"extra": "forbid"}


class LegalReport(BaseModel):
    """
    Reporte legal formal: salida estructurada del sistema Phoenix Legal.
    
    CONTRATO DURO:
    - Toda afirmación debe estar respaldada por evidencia documental
    - NO se permiten conclusiones sin evidencia
    - La salida debe ser reproducible y auditable
    
    Este es el ÚNICO formato válido para conclusiones legales del sistema.
    """
    case_id: str = Field(
        ...,
        description="ID del caso analizado",
        min_length=1
    )
    issue_analyzed: str = Field(
        ...,
        description="Cuestión jurídica o consulta concreta analizada",
        min_length=10
    )
    findings: List[LegalFinding] = Field(
        ...,
        description="Lista estructurada y ordenada de hallazgos",
        min_length=1
    )
    
    # Metadatos de auditoría (OBLIGATORIOS)
    generated_at: datetime = Field(
        ...,
        description="Timestamp de generación (auditoría)"
    )
    schema_version: str = Field(
        default=LEGAL_OUTPUT_SCHEMA_VERSION,
        description="Versión del esquema de salida"
    )
    source_system: str = Field(
        default="phoenix_legal",
        description="Sistema que generó el reporte"
    )
    
    # Metadatos adicionales (opcionales)
    total_documents_analyzed: Optional[int] = Field(
        None,
        description="Número total de documentos consultados",
        ge=0
    )
    total_chunks_used: Optional[int] = Field(
        None,
        description="Número total de chunks usados como evidencia",
        ge=0
    )
    
    @field_validator('findings')
    @classmethod
    def validate_findings_not_empty(cls, v: List[LegalFinding]) -> List[LegalFinding]:
        """REGLA DURA: Reporte sin findings no es válido"""
        if not v or len(v) == 0:
            raise ValueError("Reporte sin findings no permitido")
        return v
    
    model_config = {"extra": "forbid"}
    
    def get_all_evidence_ids(self) -> List[str]:
        """
        Retorna lista de todos los chunk_ids usados como evidencia.
        
        Útil para auditoría y trazabilidad.
        """
        evidence_ids = []
        for finding in self.findings:
            for evidence in finding.evidence:
                evidence_ids.append(evidence.chunk_id)
        return evidence_ids
    
    def get_summary_stats(self) -> dict:
        """
        Retorna estadísticas del reporte para auditoría.
        """
        total_findings = len(self.findings)
        total_evidences = sum(len(f.evidence) for f in self.findings)
        unique_chunks = len(set(self.get_all_evidence_ids()))
        unique_documents = len(set(
            e.document_id
            for f in self.findings
            for e in f.evidence
        ))
        
        return {
            "total_findings": total_findings,
            "total_evidences": total_evidences,
            "unique_chunks_used": unique_chunks,
            "unique_documents_used": unique_documents,
            "avg_evidences_per_finding": round(total_evidences / total_findings, 2) if total_findings > 0 else 0,
        }


class LegalOutputError(PhoenixException):
    """
    Excepción cuando la salida legal no cumple el contrato.
    
    FASE 5 (ENDURECIMIENTO 5):
    - Finding sin evidencia → excepción
    - Evidencia sin location → excepción
    - Referencia a chunk inexistente → excepción
    """
    
    def __init__(self, reason: str, **kwargs):
        super().__init__(
            code="LEGAL_OUTPUT_ERROR",
            message=f"Salida legal inválida: {reason}",
            details={"reason": reason},
            severity=ErrorSeverity.CRITICAL,
            **kwargs
        )

