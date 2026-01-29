from datetime import datetime, timezone

from app.core.database import get_session
from app.services.economic_report_builder import build_economic_report_bundle
from app.services.financial_analysis import CreditClassification, CreditType, Evidence, FinancialAnalysisResult


def test_debt_legal_applications_smoke():
    case_id = "f620a0ce-02c7-48cb-9d28-5744a148640d"

    ev = Evidence(
        document_id="doc",
        filename="doc.txt",
        chunk_id=None,
        page=None,
        start_char=0,
        end_char=10,
        excerpt="Deuda AEAT",
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
                description="Deuda con AEAT",
                evidence=ev,
            )
        ],
        total_debt=15000.0,
        ratios=[],
        insolvency=None,
        timeline=[],
        validation_result=None,
        data_quality_score=None,
        timeline_statistics=None,
        timeline_patterns=None,
    )

    with get_session() as db:
        bundle = build_economic_report_bundle(db, case_id=case_id, financial_analysis=fin)

    assert bundle.narrative_contract is not None
    apps = bundle.narrative_contract.debt_legal_applications
    assert len(apps) >= 1
    assert apps[0].creditor_name.upper() == "AEAT"
    assert apps[0].creditor_type == "public"
