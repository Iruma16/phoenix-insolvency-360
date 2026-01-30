"""
API — CAPA 3: Evidencia central del caso.

Permite:
- Evidencia documental (source_type=DOCUMENTO y document_id obligatorio)
- Evidencia no documental (CLIENTE/CONTABILIDAD/CRITERIO_PROFESIONAL)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.record_types import CANONICAL_RECORD_TYPES, ENTITY_ALLOWED, record_type_from_entity
from app.models.case import Case
from app.models.case_central import AuditAction, CaseRecordAudit, CaseRecordEvidence
from app.models.case_central import TemplateField
from app.models.document import Document


router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["case_evidence"])


def _require_case(db: Session, case_id: str) -> Case:
    c = db.query(Case).filter(Case.case_id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return c


class CreateEvidenceRequest(BaseModel):
    record_type: str = Field(..., min_length=2, max_length=50)
    record_id: Optional[str] = Field(None, max_length=36)

    source_type: str = Field(..., description="DOCUMENTO/CLIENTE/CONTABILIDAD/CRITERIO_PROFESIONAL")
    certainty_level: str = Field(..., description="CONSTA/NO_CONSTA/ESTIMADO")

    justification: str = Field(..., min_length=10, max_length=500)

    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    page: Optional[int] = Field(None, ge=1)
    excerpt: Optional[str] = None

    added_by: str = Field(..., min_length=2, max_length=100)

    model_config = {"extra": "forbid"}


class EvidenceSummary(BaseModel):
    evidence_id: str
    case_id: str
    record_type: str
    record_id: Optional[str] = None
    source_type: str
    certainty_level: str
    justification: str
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    page: Optional[int] = None
    excerpt: Optional[str] = None
    added_by: str
    added_at: str

    model_config = {"extra": "forbid"}


class ListEvidenceResponse(BaseModel):
    items: list[EvidenceSummary] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


@router.post("", response_model=EvidenceSummary, status_code=status.HTTP_201_CREATED)
def create_evidence(case_id: str, req: CreateEvidenceRequest, db: Session = Depends(get_db)) -> EvidenceSummary:
    _require_case(db, case_id)

    allowed_source = {"DOCUMENTO", "CLIENTE", "CONTABILIDAD", "CRITERIO_PROFESIONAL"}
    allowed_certainty = {"CONSTA", "NO_CONSTA", "ESTIMADO"}

    # Normalizar record_type a catálogo canónico.
    rt_in = (req.record_type or "").strip()
    if rt_in.upper() in ENTITY_ALLOWED:
        rt = record_type_from_entity(rt_in.upper())
    else:
        rt = rt_in.lower()
    if rt not in CANONICAL_RECORD_TYPES:
        raise HTTPException(status_code=422, detail=f"record_type inválido (canónico): {req.record_type}")

    st = (req.source_type or "").strip().upper()
    cl = (req.certainty_level or "").strip().upper()
    if st not in allowed_source:
        raise HTTPException(status_code=422, detail=f"source_type inválido: {req.source_type}")
    if cl not in allowed_certainty:
        raise HTTPException(status_code=422, detail=f"certainty_level inválido: {req.certainty_level}")

    # Regla dura: NO_CONSTA requiere justificación más fuerte
    if cl == "NO_CONSTA" and len((req.justification or "").strip()) < 20:
        raise HTTPException(
            status_code=422,
            detail="Evidencia inválida: certainty_level=NO_CONSTA requiere justification >= 20 caracteres",
        )

    # Regla dura: si source_type != DOCUMENTO -> document_id/chunk_id/page deben ser null
    if st != "DOCUMENTO":
        if req.document_id or req.chunk_id or req.page:
            raise HTTPException(
                status_code=422,
                detail="Evidencia inválida: source_type != DOCUMENTO requiere document_id/chunk_id/page null",
            )

    # Regla dura: record_id obligatorio para record_type conocido (excepto other)
    if rt != "other" and not (req.record_id or "").strip():
        raise HTTPException(status_code=422, detail="record_id es obligatorio para este record_type")

    # Validar que record_id pertenece al caso (cuando aplica)
    if rt in {"invoice", "loan", "asset", "public_debt", "court_claim"} and req.record_id:
        from app.models.situation import (
            SituationAsset,
            SituationCourtRecord,
            SituationCredit,
            SituationInvoice,
            SituationPublicDebt,
        )

        model_map = {
            "invoice": SituationInvoice,
            "loan": SituationCredit,
            "asset": SituationAsset,
            "public_debt": SituationPublicDebt,
            "court_claim": SituationCourtRecord,
        }
        model = model_map[rt]
        exists = db.query(model.record_id).filter(model.case_id == case_id, model.record_id == req.record_id).first()
        if not exists:
            raise HTTPException(status_code=422, detail="record_id no existe en el caso para ese record_type")

    if rt == "form_field" and req.record_id:
        # form_field: record_id canónico = TemplateField.field_id (no case-specific)
        exists = db.query(TemplateField.field_id).filter(TemplateField.field_id == req.record_id).first()
        if not exists:
            raise HTTPException(status_code=422, detail="record_id no existe (TemplateField.field_id)")

    if st == "DOCUMENTO":
        if not req.document_id:
            raise HTTPException(status_code=400, detail="document_id obligatorio cuando source_type=DOCUMENTO")
        # validar documento pertenece al caso
        doc = (
            db.query(Document.document_id)
            .filter(Document.case_id == case_id, Document.document_id == req.document_id, Document.deleted_at.is_(None))
            .first()
        )
        if not doc:
            raise HTTPException(status_code=400, detail="document_id no existe en el caso o está excluido")

    row = CaseRecordEvidence(
        case_id=case_id,
        record_type=rt,
        record_id=req.record_id,
        source_type=st,
        certainty_level=cl,
        justification=req.justification,
        document_id=req.document_id,
        chunk_id=req.chunk_id,
        page=req.page,
        excerpt=req.excerpt,
        added_by=req.added_by,
    )
    db.add(row)
    db.flush()  # asegurar evidence_id para auditoría
    # CAPA 4 (audit): insertar registro append-only para la creación de evidencia
    db.add(
        CaseRecordAudit(
            case_id=case_id,
            record_type=rt,
            logical_id=None,
            record_id=req.record_id,
            action=AuditAction.ADD_EVIDENCE.value,
            actor=req.added_by,
            justification=req.justification,
            before_json=None,
            after_json={
                "evidence_id": row.evidence_id,
                "document_id": req.document_id,
                "chunk_id": req.chunk_id,
                "page": req.page,
                "excerpt": (req.excerpt or "")[:300] if req.excerpt else None,
                "source_type": req.source_type,
                "certainty_level": req.certainty_level,
            },
        )
    )
    db.commit()
    db.refresh(row)
    return EvidenceSummary(
        evidence_id=row.evidence_id,
        case_id=row.case_id,
        record_type=row.record_type,
        record_id=row.record_id,
        source_type=row.source_type,
        certainty_level=row.certainty_level,
        justification=row.justification,
        document_id=row.document_id,
        chunk_id=row.chunk_id,
        page=row.page,
        excerpt=row.excerpt,
        added_by=row.added_by,
        added_at=row.added_at.isoformat(),
    )


@router.get("", response_model=ListEvidenceResponse)
def list_evidence(
    case_id: str,
    record_type: Optional[str] = Query(None),
    record_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> ListEvidenceResponse:
    _require_case(db, case_id)
    q = db.query(CaseRecordEvidence).filter(CaseRecordEvidence.case_id == case_id)
    if record_type:
        rt_in = (record_type or "").strip()
        if rt_in.upper() in ENTITY_ALLOWED:
            rt = record_type_from_entity(rt_in.upper())
        else:
            rt = rt_in.lower()
        if rt not in CANONICAL_RECORD_TYPES:
            raise HTTPException(status_code=422, detail=f"record_type inválido (canónico): {record_type}")
        q = q.filter(CaseRecordEvidence.record_type == rt)
    if record_id:
        q = q.filter(CaseRecordEvidence.record_id == record_id)
    rows = q.order_by(CaseRecordEvidence.added_at.desc()).limit(200).all()
    items: list[EvidenceSummary] = []
    for r in rows:
        items.append(
            EvidenceSummary(
                evidence_id=r.evidence_id,
                case_id=r.case_id,
                record_type=r.record_type,
                record_id=r.record_id,
                source_type=r.source_type,
                certainty_level=r.certainty_level,
                justification=r.justification,
                document_id=r.document_id,
                chunk_id=r.chunk_id,
                page=r.page,
                excerpt=r.excerpt,
                added_by=r.added_by,
                added_at=r.added_at.isoformat() if r.added_at else "",
            )
        )
    return ListEvidenceResponse(items=items)

