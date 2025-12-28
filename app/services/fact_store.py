from typing import Optional
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models.fact import Fact
from app.models.fact_evidence import FactEvidence
from app.services.fact_fingerprint import build_fact_fingerprint


def upsert_fact_with_evidence(
    *,
    case_id: str,
    fact_type: str,
    title: str,
    details: Optional[str],
    date_iso: Optional[str],
    amount_cents: Optional[int],
    counterparty: Optional[str],
    document_id: str,
    chunk_id: Optional[str] = None,
    location_hint: Optional[str] = None,
    confidence: int = 70,
    session: Optional[Session] = None,
) -> str:
    """
    Crea o reutiliza un Fact (deduplicado por fingerprint) y añade evidencia.
    Devuelve fact_id.
    
    Args:
        session: Sesión de base de datos opcional. Si no se proporciona,
                se crea una nueva sesión.
    """
    fingerprint = build_fact_fingerprint(
        case_id=case_id,
        fact_type=fact_type,
        date_iso=date_iso,
        amount_cents=amount_cents,
        counterparty=counterparty,
    )

    # Si se proporciona una sesión, usarla; si no, crear una nueva
    if session is not None:
        return _upsert_fact_in_session(
            session=session,
            case_id=case_id,
            fact_type=fact_type,
            fingerprint=fingerprint,
            title=title,
            details=details,
            date_iso=date_iso,
            amount_cents=amount_cents,
            counterparty=counterparty,
            document_id=document_id,
            chunk_id=chunk_id,
            location_hint=location_hint,
            confidence=confidence,
        )
    else:
        with get_session() as new_session:
            return _upsert_fact_in_session(
                session=new_session,
                case_id=case_id,
                fact_type=fact_type,
                fingerprint=fingerprint,
                title=title,
                details=details,
                date_iso=date_iso,
                amount_cents=amount_cents,
                counterparty=counterparty,
                document_id=document_id,
                chunk_id=chunk_id,
                location_hint=location_hint,
                confidence=confidence,
            )


def _upsert_fact_in_session(
    *,
    session: Session,
    case_id: str,
    fact_type: str,
    fingerprint: str,
    title: str,
    details: Optional[str],
    date_iso: Optional[str],
    amount_cents: Optional[int],
    counterparty: Optional[str],
    document_id: str,
    chunk_id: Optional[str],
    location_hint: Optional[str],
    confidence: int,
) -> str:
    """Lógica interna de upsert usando una sesión existente."""
    existing = (
        session.query(Fact)
        .filter(Fact.case_id == case_id, Fact.fingerprint == fingerprint)
        .first()
    )

    if existing:
        fact = existing
        # Si llega mejor confianza, actualizamos score
        if confidence > (fact.score_confidence or 0):
            fact.score_confidence = confidence
        fact_id = fact.fact_id
    else:
        fact = Fact(
            case_id=case_id,
            fact_type=fact_type,
            fingerprint=fingerprint,
            title=title,
            details=details,
            date_iso=date_iso,
            amount_cents=amount_cents,
            counterparty=counterparty,
            score_confidence=confidence,
        )
        session.add(fact)
        session.flush()  # para obtener fact_id sin hacer commit
        fact_id = fact.fact_id

    # Verificar si la evidencia ya existe para evitar duplicados
    existing_ev = (
        session.query(FactEvidence)
        .filter(
            FactEvidence.fact_id == fact_id,
            FactEvidence.document_id == document_id,
            FactEvidence.chunk_id == chunk_id,
        )
        .first()
    )

    if not existing_ev:
        ev = FactEvidence(
            fact_id=fact_id,
            document_id=document_id,
            chunk_id=chunk_id,
            location_hint=location_hint,
        )
        session.add(ev)

    return fact_id
