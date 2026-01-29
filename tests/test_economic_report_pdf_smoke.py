from datetime import datetime, timezone

from app.models.economic_report import ClientSummary, EconomicReportBundle, LawyerSignature
from app.reports.pdf.economic_pdf import generate_economic_report_pdf
from app.services.financial_analysis import FinancialAnalysisResult


def test_generate_economic_report_pdf_smoke():
    fin = FinancialAnalysisResult(
        case_id="case-test",
        analysis_date=datetime.now(timezone.utc),
        balance=None,
        profit_loss=None,
        credit_classification=[],
        total_debt=None,
        ratios=[],
        insolvency=None,
        timeline=[],
        validation_result=None,
        data_quality_score=None,
        timeline_statistics=None,
        timeline_patterns=None,
    )

    bundle = EconomicReportBundle(
        report_id="r1",
        case_id="case-test",
        case_name="ACME SL",
        generated_at=datetime.now(timezone.utc),
        debtor_type="company",
        financial_analysis=fin,
        alerts=[],
        legal_synthesis={},
        roadmap=[],
        legal_citations={},
        client_summary=ClientSummary(
            headline="Situación económica no determinable con la documentación actual.",
            situation="no_determinable",
            key_points=["No constan datos suficientes en el expediente."],
            next_7_days=["Aportar balance y lista de acreedores."],
            warnings=[],
        ),
        documents_presented=[],
        documents_missing=["Balance y cuenta de pérdidas y ganancias"],
        documents_recommended=["Listado de acreedores"],
        lawyer_signature=LawyerSignature(
            lawyer_name="Abogado/a de Prueba",
            collegiate_number="12345",
            bar_association="ICAM",
            law_firm="Despacho de Prueba",
            office_city="Madrid",
        ),
        narrative_md=None,
    )

    pdf_bytes = generate_economic_report_pdf(bundle)
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 1024

