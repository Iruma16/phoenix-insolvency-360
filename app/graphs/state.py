from typing import Any, Optional, TypedDict


class Document(TypedDict):
    doc_id: str
    doc_type: str
    content: str
    date: Optional[str]


class TimelineEvent(TypedDict):
    date: str
    description: str
    source_doc_id: Optional[str]


class Risk(TypedDict):
    risk_type: str
    severity: str
    explanation: str
    evidence: list[str]


class AuditState(TypedDict):
    case_id: str

    # Identidad del caso
    company_profile: dict[str, Any]

    # Datos
    documents: list[Document]
    timeline: list[TimelineEvent]

    # Análisis
    risks: list[Risk]
    missing_documents: list[str]
    legal_findings: list[dict[str, Any]]

    # Análisis LLM (opcional)
    auditor_llm: Optional[dict[str, Any]]
    prosecutor_llm: Optional[dict[str, Any]]

    # Rule Engine
    rule_based_findings: Optional[list[dict[str, Any]]]

    # Salida
    notes: Optional[str]
    report: Optional[dict[str, Any]]
