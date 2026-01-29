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
    actor: Literal["cliente", "abogado", "administracion_concursal", "no_determinable"] = "no_determinable"
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


class DocumentItem(BaseModel):
    """
    Documento aportado al expediente (inventario).

    Se usa para reflejar al cliente qué se ha revisado (y cuándo) y para
    detectar faltantes/recomendados en el informe.
    """

    document_id: str
    filename: str
    doc_type: Optional[str] = None
    created_at: Optional[str] = None
    status: Optional[str] = None

    class Config:
        extra = "forbid"


class LawyerSignature(BaseModel):
    """
    Firma del abogado responsable del informe.

    Debe provenir de configuración del despacho (NO del análisis).
    """

    lawyer_name: str
    collegiate_number: str
    bar_association: Optional[str] = None
    law_firm: Optional[str] = None
    office_city: Optional[str] = None
    signature_date: Optional[str] = None  # YYYY-MM-DD (obligatoria en audience=client)

    class Config:
        extra = "forbid"


class FactLawConsequence(BaseModel):
    """
    Mapa visible: Hecho → base legal (TRLC) → consecuencia práctica.
    """

    fact: str
    legal_basis: list[LegalCitation] = Field(default_factory=list)
    consequence: str
    risk_if_inaction: Optional[str] = None
    evidence: list[EvidenceRef] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class RisksByInaction(BaseModel):
    """
    Riesgos si no se actúa (redacción conservadora).
    """

    legal: list[str] = Field(default_factory=list)
    economic: list[str] = Field(default_factory=list)
    personal: list[str] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class DebtTrlcArticleRef(BaseModel):
    article_ref: str  # "TRLC art. 242" / "TRLC arts. 270 y ss."
    topic: str
    relevance: str

    class Config:
        extra = "forbid"


class DebtLegalOption(BaseModel):
    option_code: Literal[
        "include_in_concurso",
        "negotiate_payment_plan",
        "seek_deferral",
        "secure_financing",
        "challenge_claim",
        "verify_collateral",
        "gather_docs",
    ]
    description: str
    prerequisites: str
    legal_basis_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class DebtRisk(BaseModel):
    risk_level: Literal["low", "medium", "high"]
    statement: str
    related_refs: list[str] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class DebtEvidenceRef(BaseModel):
    document_id: Optional[str] = None
    document_name: str
    page: Optional[int] = None
    excerpt: str

    class Config:
        extra = "forbid"


class DebtLegalApplication(BaseModel):
    # Identificación
    debt_id: str
    creditor_name: str
    creditor_type: Literal[
        "public",
        "bank",
        "supplier",
        "employee",
        "landlord",
        "related_party",
        "other",
    ]
    source_section: Literal["inventory", "financial", "legal", "timeline", "alerts"]

    # Importe y período
    amount_eur: Optional[float] = None
    amount_confidence: Literal["exact", "approx", "unknown"] = "unknown"
    period_start: Optional[str] = None  # YYYY-MM-DD
    period_end: Optional[str] = None  # YYYY-MM-DD
    period_note: str

    # Garantías / naturaleza
    has_security: Optional[bool] = None
    security_type: Optional[Literal["mortgage", "pledge", "reservation_of_title", "other"]] = None
    security_note: str

    # Clasificación concursal (propuesta prudente)
    proposed_trlc_bucket: Literal[
        "contra_la_masa",
        "privilegio_especial",
        "privilegio_general",
        "ordinario",
        "subordinado",
        "no_determinable",
    ] = "no_determinable"
    classification_basis: str
    classification_confidence: Literal["high", "medium", "low"] = "low"

    # Base legal (solo artículos permitidos por extractor TRLC local)
    trlc_articles: list[DebtTrlcArticleRef] = Field(default_factory=list)

    # Opciones a considerar (acciones posibles)
    legal_options: list[DebtLegalOption] = Field(default_factory=list)

    # Consecuencias prácticas (cliente)
    practical_consequences: list[str] = Field(default_factory=list)

    # Riesgos asociados
    risks: list[DebtRisk] = Field(default_factory=list)

    # Evidencia / trazabilidad
    evidence_refs: list[DebtEvidenceRef] = Field(default_factory=list)

    # Mensaje cliente listo para insertar
    client_ready_summary: str

    class Config:
        extra = "forbid"


class NarrativeContract(BaseModel):
    """
    Contrato explícito para cualquier redacción narrativa (LLM o humana).

    Regla: la narrativa solo puede usar lo que esté aquí dentro.
    """

    case: dict
    client_summary: dict
    documents: dict
    financial: dict
    insolvency_signals: list[str] = Field(default_factory=list)
    alerts: list[dict] = Field(default_factory=list)
    allowed_recommendations: list[str] = Field(default_factory=list)
    legal_citations: dict[str, list[LegalCitation]] = Field(default_factory=dict)
    debt_legal_applications: list[DebtLegalApplication] = Field(default_factory=list)
    fact_law_map: list[FactLawConsequence] = Field(default_factory=list)
    risks_by_inaction: RisksByInaction = Field(default_factory=RisksByInaction)
    lawyer_signature: Optional[LawyerSignature] = None

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

    # Inventario documental (presentados / faltantes / recomendados)
    documents_presented: list[DocumentItem] = Field(default_factory=list)
    documents_missing: list[str] = Field(default_factory=list)
    documents_recommended: list[str] = Field(default_factory=list)

    # Firma del abogado (configurable). Si no existe, el PDF mostrará “no configurado”.
    lawyer_signature: Optional[LawyerSignature] = None

    # Textos opcionales generados por LLM (para auditoría e indexado)
    narrative_md: Optional[str] = None

    # Contrato explícito para narrativa (por sección) + mapa hecho→artículo→consecuencia
    narrative_contract: Optional[NarrativeContract] = None

    class Config:
        extra = "forbid"

