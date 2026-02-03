from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from app.core.database import get_session
from app.legal.checker.export_checker import check_export
from app.models.economic_report import LawyerSignature
from app.reports.pdf.economic_pdf import generate_economic_report_pdf
from app.services.economic_report_builder import build_economic_report_bundle
from app.services.financial_analysis import (
    CreditClassification,
    CreditType,
    Evidence,
    FinancialAnalysisResult,
    TimelineEvent,
)


def test_client_export_allows_undetermined_date_and_pdf_has_prd_blocks(tmp_path: Path):
    case_id = "f620a0ce-02c7-48cb-9d28-5744a148640d"

    ev = Evidence(
        document_id="doc",
        filename="doc.txt",
        chunk_id=None,
        page=None,
        start_char=0,
        end_char=40,
        excerpt="Deuda AEAT según expediente.",
        extraction_method="txt",
        extraction_confidence=0.9,
    )

    fin = FinancialAnalysisResult(
        case_id=case_id,
        analysis_date=datetime.now(timezone.utc),
        balance=None,
        profit_loss=None,
        credit_classification=[
            CreditClassification(
                credit_type=CreditType.PRIVILEGED_GENERAL,
                amount=15000.0,
                creditor_name="AEAT",
                description="Deuda AEAT",
                evidence=ev,
            )
        ],
        total_debt=15000.0,
        ratios=[],
        insolvency=None,
        timeline=[
            TimelineEvent(
                date=None,
                event_type="otro",
                description="Fecha no determinada: hecho relevante a contextualizar.",
                amount=None,
                evidence=ev,
            )
        ],
        validation_result=None,
        data_quality_score=None,
        timeline_statistics=None,
        timeline_patterns=None,
    )

    with get_session() as db:
        bundle = build_economic_report_bundle(db, case_id=case_id, financial_analysis=fin)

    # Simular firma completa
    bundle.lawyer_signature = LawyerSignature(
        lawyer_name="Abogada Senior",
        collegiate_number="12345",
        bar_association="ICAM",
        law_firm="Phoenix Legal",
        office_city="Madrid",
        signature_date="2026-01-29",
    )

    rep = check_export(bundle, audience="client")
    assert rep.ok is True

    pdf_bytes = generate_economic_report_pdf(bundle, audience="client")
    out = tmp_path / "client.pdf"
    out.write_bytes(pdf_bytes)

    text = "\n".join((p.extract_text() or "") for p in PdfReader(str(out)).pages)

    # PRD: 9 bloques y sin bloque extra de alertas
    assert "1. RESUMEN EJECUTIVO" in text
    assert "2. EVOLUCIÓN DE LA SITUACIÓN (LÍNEA TEMPORAL)" in text
    assert "3. INVENTARIO DOCUMENTAL" in text
    assert "4. SITUACIÓN ECONÓMICA" in text
    assert "5. CLASIFICACIÓN DE LAS DEUDAS" in text
    assert "6. RIESGOS POR INACCIÓN" in text
    assert "7. PROCESO CONCURSAL Y OPERATIVA PRÁCTICA" in text
    assert "8. HOJA DE RUTA" in text
    assert "9. FIRMA DEL ABOGADO" in text
    assert "ALERTAS DEL EXPEDIENTE" not in text

    # PRD: sin dashboard/tecnicismos
    assert "Puntos clave" not in text
    assert "Qué hacer en 7 días" not in text
    assert "Confianza:" not in text
