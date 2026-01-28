"""
Contrato del Informe de Situación Económica (cliente).

Objetivo:
- Explicar al cliente su situación económica (datos fríos + interpretación)
- Mostrar alertas y evidencias
- Proponer opciones y hoja de ruta (determinista)
- Aportar base legal con citas recuperadas por RAG (cuando exista corpus)

Nota:
Este contrato es el "source of truth" (bundle) y se usa para:
1) renderizar PDF
2) (opcional) redacción con LLM
3) indexación en RAG del caso (colección "reports")
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.analysis_alert import AnalysisAlert
from app.services.financial_analysis import FinancialAnalysisResult


class LegalCitation(BaseModel):
    citation: str
    text: str
    source: Literal["ley", "jurisprudencia", "aeat_tgss"] = "ley"
    authority_level: Optional[str] = None  # "norma" | "jurisprudencia"
    relevance: Optional[str] = None  # "alta" | "media" | "baja"
    article: Optional[str] = None
    law: Optional[str] = None
    court: Optional[str] = None
    date: Optional[str] = None

    class Config:
        extra = "forbid"


class EvidenceRef(BaseModel):
    document_id: str
    filename: str
    chunk_id: Optional[str] = None
    page: Optional[int] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    excerpt: Optional[str] = None
    extraction_method: Optional[str] = None

    class Config:
        extra = "forbid"


class RoadmapItem(BaseModel):
    phase: str
    step: str
    priority: Literal["INMEDIATA", "ALTA", "MEDIA", "BAJA"] = "MEDIA"
    status: Literal["pendiente", "en_curso", "completado", "no_determinable"] = "pendiente"
    rationale: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    legal_basis: list[LegalCitation] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class ClientSummary(BaseModel):
    headline: str
    situation: Literal["critica", "preocupante", "estable", "no_determinable"] = "no_determinable"
    key_points: list[str] = Field(default_factory=list)
    next_7_days: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class EconomicReportBundle(BaseModel):
    report_id: str
    case_id: str
    case_name: str
    generated_at: datetime
    schema_version: str = "1.0.0"
    source_system: str = "phoenix_legal"

    debtor_type: Literal["company", "person", "unknown"] = "unknown"

    # Núcleo: datos fríos (finanzas) + alertas
    financial_analysis: FinancialAnalysisResult
    alerts: list[AnalysisAlert] = Field(default_factory=list)

    # Síntesis jurídica determinista (dict serializable)
    legal_synthesis: dict = Field(default_factory=dict)

    # Hoja de ruta (pasos)
    roadmap: list[RoadmapItem] = Field(default_factory=list)

    # Base legal recuperada por RAG (si existe)
    legal_citations: dict[str, list[LegalCitation]] = Field(
        default_factory=dict,
        description="Citas por sección: exoneracion, credito_publico, opciones_pago, concurso, etc.",
    )

    # Resumen para cliente (puede ser determinista; LLM opcional lo puede reescribir)
    client_summary: ClientSummary

    # Textos opcionales generados por LLM (para auditoría e indexado)
    narrative_md: Optional[str] = None

    class Config:
        extra = "forbid"

