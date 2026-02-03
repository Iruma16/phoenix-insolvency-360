from __future__ import annotations

from datetime import datetime

from app.api.analysis_alerts import (
    _detect_accounting_alerts,
    _detect_bank_alerts,
    _detect_duplicate_documents_sha256,
    _detect_tgss_alerts,
)
from app.models.analysis_alert import AlertType
from app.models.case import Case
from app.models.document import Document
from app.models.document_chunk import DocumentChunk, ExtractionMethod


def _seed_case(db_session, case_id: str = "case_u1"):
    db_session.add(Case(case_id=case_id, name="Caso Unit"))
    db_session.commit()


def _seed_doc(
    db_session,
    *,
    case_id: str,
    document_id: str,
    filename: str,
    sha256_hash: str,
    doc_type: str,
):
    db_session.add(
        Document(
            document_id=document_id,
            case_id=case_id,
            filename=filename,
            sha256_hash=sha256_hash,
            file_size_bytes=10,
            mime_type="application/pdf",
            uploaded_at=datetime.utcnow(),
            doc_type=doc_type,
            doc_type_confidence=1.0,
            doc_type_source="inferred",
            source="test",
            date_start=datetime.utcnow(),
            date_end=datetime.utcnow(),
            reliability="original",
            file_format="pdf",
            storage_path=f"/tmp/{filename}",
            created_at=datetime.utcnow(),
            deleted_at=None,
        )
    )
    db_session.commit()


def _seed_chunk(
    db_session,
    *,
    chunk_id: str,
    case_id: str,
    document_id: str,
    content: str,
    extraction_method: ExtractionMethod = ExtractionMethod.PDF_TEXT,
    page_start: int | None = 1,
):
    db_session.add(
        DocumentChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            case_id=case_id,
            chunk_index=0,
            content=content,
            start_char=0,
            end_char=max(50, len(content)),
            extraction_method=extraction_method,
            page_start=page_start,
            page_end=page_start,
        )
    )
    db_session.commit()


def test_detector_duplicate_sha256_creates_duplicated_data_alert(db_session):
    case_id = "case_dup_sha"
    _seed_case(db_session, case_id)
    sha = "a" * 64

    _seed_doc(
        db_session,
        case_id=case_id,
        document_id="doc_a",
        filename="a.pdf",
        sha256_hash=sha,
        doc_type="OTRO",
    )
    _seed_doc(
        db_session,
        case_id=case_id,
        document_id="doc_b",
        filename="b.pdf",
        sha256_hash=sha,
        doc_type="OTRO",
    )
    _seed_chunk(
        db_session,
        chunk_id="chunk_a",
        case_id=case_id,
        document_id="doc_a",
        content="Contenido suficiente " + ("x" * 120),
        page_start=1,
    )
    _seed_chunk(
        db_session,
        chunk_id="chunk_b",
        case_id=case_id,
        document_id="doc_b",
        content="Contenido suficiente " + ("y" * 120),
        page_start=1,
    )

    chunks = db_session.query(DocumentChunk).filter(DocumentChunk.case_id == case_id).all()
    alerts = _detect_duplicate_documents_sha256(case_id, chunks, db_session)
    assert any(a.alert_type == AlertType.DUPLICATED_DATA for a in alerts)
    assert any("sha256" in (a.description or "").lower() for a in alerts)


def test_detector_accounting_mispaid_creates_inconsistent_data_alert(db_session):
    case_id = "case_mispaid"
    _seed_case(db_session, case_id)

    _seed_doc(
        db_session,
        case_id=case_id,
        document_id="doc_inv",
        filename="factura.pdf",
        sha256_hash=("b" * 64),
        doc_type="FACTURA",
    )

    inv = "AB-2024-000123"
    _seed_chunk(
        db_session,
        chunk_id="chunk_total",
        case_id=case_id,
        document_id="doc_inv",
        content=f"Factura {inv}\nTOTAL: 1.000,00 €",
        page_start=1,
    )
    _seed_chunk(
        db_session,
        chunk_id="chunk_paid",
        case_id=case_id,
        document_id="doc_inv",
        content=f"{inv}\nImporte pagado: 500,00 €",
        page_start=1,
    )

    chunks = db_session.query(DocumentChunk).filter(DocumentChunk.case_id == case_id).all()
    alerts = _detect_accounting_alerts(case_id, chunks, db_session)
    assert any(a.alert_type == AlertType.INCONSISTENT_DATA for a in alerts)
    assert any("discrepancia" in (a.description or "").lower() for a in alerts)


def test_detector_tgss_extracts_periods_and_amount(db_session):
    case_id = "case_tgss_1"
    _seed_case(db_session, case_id)

    _seed_doc(
        db_session,
        case_id=case_id,
        document_id="doc_tgss",
        filename="tgss_apremio.pdf",
        sha256_hash=("c" * 64),
        doc_type="TGSS",
    )

    content = (
        "TGSS Providencia de apremio. Importe principal reclamado: 1.234,56 €.\n"
        "Periodo reclamado 2024-01 2024-02 2024-03."
    )
    _seed_chunk(
        db_session,
        chunk_id="chunk_tgss",
        case_id=case_id,
        document_id="doc_tgss",
        content=content,
        page_start=1,
    )

    chunks = db_session.query(DocumentChunk).filter(DocumentChunk.case_id == case_id).all()
    alerts = _detect_tgss_alerts(case_id, chunks, db_session)
    assert alerts, "debe generar al menos una alerta TGSS"
    # alerta principal con importe + periodos
    assert any("importe principal aproximado" in (a.description or "").lower() for a in alerts)
    assert any("periodos detectados" in (a.description or "").lower() for a in alerts)


def test_detector_tgss_bank_window_correlation_flag(db_session):
    case_id = "case_tgss_bank"
    _seed_case(db_session, case_id)

    _seed_doc(
        db_session,
        case_id=case_id,
        document_id="doc_tgss",
        filename="tgss.pdf",
        sha256_hash=("d" * 64),
        doc_type="TGSS",
    )
    _seed_doc(
        db_session,
        case_id=case_id,
        document_id="doc_bank",
        filename="extracto_bancario.pdf",
        sha256_hash=("e" * 64),
        doc_type="EXTRACTO_BANCARIO",
    )

    # Ancla TGSS: DMY
    _seed_chunk(
        db_session,
        chunk_id="chunk_tgss_date",
        case_id=case_id,
        document_id="doc_tgss",
        content="Tesorería General de la Seguridad Social. Fecha: 01/02/2024",
        page_start=1,
    )
    # Movimiento banco dentro de ventana 60-180 días + vinculada needle + ISO date
    _seed_chunk(
        db_session,
        chunk_id="chunk_bank",
        case_id=case_id,
        document_id="doc_bank",
        content="2024-06-15 Transferencia a B-99112233 (Grupo XYZ) 1.000,00 €",
        page_start=2,
    )

    chunks = db_session.query(DocumentChunk).filter(DocumentChunk.case_id == case_id).all()
    alerts = _detect_bank_alerts(case_id, chunks, db_session)
    assert alerts, "debe generar alerta banco"
    assert any("tgss↔banco" in (a.description or "").lower() for a in alerts)

