from __future__ import annotations

from datetime import datetime

from app.models.analysis_alert import AlertEvidence, AlertEvidenceLocation, AlertType, AnalysisAlert
from app.models.case import Case
from app.services.alerts_generator import generate_persisted_alerts_for_case
from app.services.assistant_alert_voice import VoiceOutput


def _make_analysis_alert(
    *,
    case_id: str,
    alert_id: str,
    chunk_id: str,
    page_start: int | None,
):
    ev = AlertEvidence(
        chunk_id=chunk_id,
        document_id="doc_1",
        filename="f1.pdf",
        location=AlertEvidenceLocation(
            start_char=0,
            end_char=120,
            page_start=page_start,
            page_end=page_start,
            extraction_method="pdf_text",
        ),
        content="contenido evidencia",
    )
    return AnalysisAlert(
        alert_id=alert_id,
        case_id=case_id,
        alert_type=AlertType.SUSPICIOUS_PATTERN,
        description="Patrón técnico objetivo con evidencia",
        evidence=[ev],
        created_at=datetime.utcnow(),
    )


def test_regenerate_preserves_status_and_note_and_sets_changed_flag(db_session, monkeypatch):
    case_id = "case_regen_1"
    db_session.add(Case(case_id=case_id, name="Caso Regen"))
    db_session.commit()

    # Patch voice (avoid LLM)
    def _fake_voice(*_args, **_kwargs):
        return VoiceOutput(
            title_human="Ojo con TGSS (apremio/periodos)",
            summary_human="Esto no es concluyente.\n\nYo revisaría el soporte.",
            to_clarify=[],
            disclaimer_detail="Nota",
        )

    monkeypatch.setattr("app.services.alerts_generator.generate_voice_llm", _fake_voice)

    # Patch technical source to control stability and “material change”
    a1 = _make_analysis_alert(case_id=case_id, alert_id="tech_1", chunk_id="c1", page_start=1)
    monkeypatch.setattr("app.services.alerts_generator.get_analysis_alerts", lambda **_: [a1])

    # First generation
    n1 = generate_persisted_alerts_for_case(case_id=case_id, db=db_session)
    db_session.commit()
    assert n1 == 1

    # Mark as reviewed + add lawyer note
    from app.models.alert import Alert as AlertORM

    row = db_session.query(AlertORM).filter(AlertORM.case_id == case_id).first()
    assert row is not None
    row.status = "revisada"
    row.lawyer_note = "nota"
    row.updated_by = "abogado"
    db_session.commit()

    # Second generation with same alert_id but changed evidence material -> fingerprint changes
    # (we keep alert_id stable via monkeypatch; fingerprint changes because page_start changes)
    a2 = _make_analysis_alert(case_id=case_id, alert_id="tech_1", chunk_id="c1", page_start=2)
    monkeypatch.setattr("app.services.alerts_generator.get_analysis_alerts", lambda **_: [a2])

    n2 = generate_persisted_alerts_for_case(case_id=case_id, db=db_session)
    db_session.commit()
    assert n2 == 1

    row2 = db_session.query(AlertORM).filter(AlertORM.case_id == case_id).first()
    assert row2 is not None
    # Preserva editorial
    assert row2.status == "revisada"
    assert row2.lawyer_note == "nota"
    # Señala cambio
    assert bool(row2.changed_since_last_review) is True
