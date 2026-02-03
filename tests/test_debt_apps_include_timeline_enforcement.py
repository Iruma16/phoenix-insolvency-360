from datetime import datetime, timezone

from app.core.database import get_session
from app.services.economic_report_builder import build_economic_report_bundle
from app.services.financial_analysis import Evidence, FinancialAnalysisResult, TimelineEvent


def test_debt_legal_applications_includes_timeline_enforcement():
    case_id = "f620a0ce-02c7-48cb-9d28-5744a148640d"
    ev = Evidence(
        document_id="doc",
        filename="embargo.txt",
        chunk_id=None,
        page=None,
        start_char=0,
        end_char=40,
        excerpt="Embargo AEAT",
        extraction_method="txt",
        extraction_confidence=0.9,
    )
    fin = FinancialAnalysisResult(
        case_id=case_id,
        analysis_date=datetime.now(timezone.utc),
        balance=None,
        profit_loss=None,
        credit_classification=[],
        total_debt=None,
        ratios=[],
        insolvency=None,
        timeline=[
            TimelineEvent(
                date=None,
                event_type="embargo",
                description="Embargo AEAT",
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

    assert bundle.narrative_contract is not None
    apps = bundle.narrative_contract.debt_legal_applications
    assert any(a.source_section == "timeline" for a in apps)
