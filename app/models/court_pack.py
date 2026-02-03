from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    not_started = "not_started"
    draft = "draft"
    generated = "generated"
    reviewed = "reviewed"
    final = "final"
    final_manual = "final_manual"
    blocked = "blocked"


class PackStatus(str, Enum):
    incomplete = "incomplete"
    ready_to_generate = "ready_to_generate"
    generated = "generated"
    ready_to_submit = "ready_to_submit"
    submitted_simulated = "submitted_simulated"


class DebtorFlags(BaseModel):
    debtor_type: Literal["juridica", "fisica"]
    has_workers: bool
    requires_audit: bool
    accounting_obligation: bool
    has_procurador: bool

    model_config = {"extra": "forbid"}


class Issue(BaseModel):
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    code: str
    message: str
    field_path: Optional[str] = None
    suggestion: Optional[str] = None

    model_config = {"extra": "forbid"}


class CourtDocumentState(BaseModel):
    doc_type: str
    display_name: str
    is_required: bool
    status: DocumentStatus
    inputs_hash: str
    generated_file_path: Optional[str] = None
    last_generated_at: Optional[str] = None
    ai_cache_key_generate: Optional[str] = None
    ai_cache_key_review: Optional[str] = None
    issues: list[Issue] = Field(default_factory=list)
    warnings_count: int
    errors_count: int

    model_config = {"extra": "forbid"}


class AttachmentState(BaseModel):
    attachment_id: str
    filename: str
    rel_path: str
    kind: Literal["escritura", "poder", "cuentas_anuales", "auditoria", "otro"]
    sha256: str
    size_bytes: int
    created_at: str

    model_config = {"extra": "forbid"}


class CourtPackState(BaseModel):
    case_id: str
    debtor_flags: DebtorFlags
    documents: list[CourtDocumentState] = Field(default_factory=list)
    attachments: list[AttachmentState] = Field(default_factory=list)
    pack_status: PackStatus
    created_at: str
    updated_at: str
    manual_overrides_count: int

    model_config = {"extra": "forbid"}
