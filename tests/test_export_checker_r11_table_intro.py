from datetime import datetime, timezone

from app.legal.checker.export_checker import check_export
from app.models.economic_report import ClientSummary, EconomicReportBundle, LawyerSignature, NarrativeContract
from app.services.financial_analysis import FinancialAnalysisResult


def test_r11_flags_table_without_intro_in_narrative():
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

    b = EconomicReportBundle(
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
            headline="Resumen.",
            situation="no_determinable",
            key_points=[],
            next_7_days=[],
            warnings=[],
        ),
        documents_presented=[],
        documents_missing=[],
        documents_recommended=[],
        lawyer_signature=LawyerSignature(
            lawyer_name="Abogada Senior",
            collegiate_number="12345",
            law_firm="Phoenix Legal",
            signature_date="2026-01-29",
        ),
        narrative_md="Hecho | Base legal | Consecuencia\nX | TRLC art. 280 | Y",
        narrative_contract=NarrativeContract(
            case={"case_id": "case-test", "case_name": "ACME SL", "debtor_type": "company"},
            client_summary={},
            documents={},
            financial={},
            insolvency_signals=[],
            alerts=[],
            allowed_recommendations=[],
            legal_citations={},
            debt_legal_applications=[],
        ),
    )

    rep = check_export(b, audience="client")
    assert rep.ok is True  # R11 es blando (retry), no bloquea export
    assert any(v.rule_id == "R11" for v in rep.violations)

