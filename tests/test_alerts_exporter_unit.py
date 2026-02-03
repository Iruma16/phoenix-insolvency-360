from __future__ import annotations

from datetime import datetime

from app.models.alert import Alert
from app.models.alert_evidence import AlertEvidence
from app.services.alerts_exporter import export_validated_alerts_to_markdown


def test_export_only_includes_validated_statuses(db_session, tmp_path, monkeypatch):
    case_id = "case_export_1"

    # Redirect reports dir to temp
    from app import services as services_pkg

    # monkeypatch module constant
    import app.services.alerts_exporter as exporter

    monkeypatch.setattr(exporter, "REPORTS_BASE_DIR", tmp_path)

    # Seed 3 alerts: only 2 are exportable
    a1 = Alert(
        alert_id="a1",
        case_id=case_id,
        domain="TGSS",
        relevance="ALTA",
        title_human="A1",
        summary_human="s1",
        disclaimer_detail="d1",
        fingerprint="fp1",
        source_alert_ids=["t1"],
        status="revisada",
        lawyer_note="nota1",
        para_informe=False,
        changed_since_last_review=True,
        updated_by="abogado",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    a2 = Alert(
        alert_id="a2",
        case_id=case_id,
        domain="BANCO",
        relevance="MEDIA",
        title_human="A2",
        summary_human="s2",
        disclaimer_detail="d2",
        fingerprint="fp2",
        source_alert_ids=["t2"],
        status="para_informe",
        lawyer_note="",
        para_informe=True,
        changed_since_last_review=False,
        updated_by="abogado",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    a3 = Alert(
        alert_id="a3",
        case_id=case_id,
        domain="DOCS",
        relevance="BAJA",
        title_human="A3",
        summary_human="s3",
        disclaimer_detail="d3",
        fingerprint="fp3",
        source_alert_ids=["t3"],
        status="pendiente",
        lawyer_note="",
        para_informe=False,
        changed_since_last_review=False,
        updated_by="abogado",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add_all([a1, a2, a3])
    db_session.commit()

    db_session.add(
        AlertEvidence(
            evidence_id="e1",
            alert_id="a1",
            document_id="doc1",
            filename="f1.pdf",
            chunk_id="c1",
            page_start=1,
            page_end=1,
            start_char=0,
            end_char=10,
            snippet="snip",
        )
    )
    db_session.commit()

    res = export_validated_alerts_to_markdown(case_id=case_id, db=db_session)
    assert res.included_alerts == 2
    assert "A1" in res.markdown
    assert "A2" in res.markdown
    assert "A3" not in res.markdown
    # changed marker included
    assert "cambió desde la última revisión" in res.markdown
    # registry includes evidence
    assert any(ev.get("filename") == "f1.pdf" for ev in res.evidence_registry)
    # file written
    p = tmp_path / case_id / res.markdown_filename
    assert p.exists()

