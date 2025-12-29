from typing import TypedDict, List, Optional, Dict, Any


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
    evidence: List[str]


class AuditState(TypedDict):
    case_id: str

    # Identidad del caso
    company_profile: Dict[str, Any]

    # Datos
    documents: List[Document]
    timeline: List[TimelineEvent]

    # Análisis
    risks: List[Risk]
    missing_documents: List[str]
    legal_findings: List[Dict[str, Any]]

    # Salida
    notes: Optional[str]
    report: Optional[Dict[str, Any]]

