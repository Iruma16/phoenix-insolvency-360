from __future__ import annotations

from typing import TypedDict, List, Optional


class AuditState(TypedDict):
    """
    Estado compartido entre nodos del Auditor.
    """
    case_id: str
    documents_processed: List[str]
    events_detected: List[str]
    risks: List[str]
    notes: Optional[str]
