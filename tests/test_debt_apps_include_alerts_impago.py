from datetime import datetime, timezone

from app.core.database import get_session
from app.services.economic_report_builder import build_economic_report_bundle
from app.services.financial_analysis import Evidence, FinancialAnalysisResult, InsolvencyDetection, InsolvencySignal


def test_debt_legal_applications_includes_impago_signal_as_alert_debt():
    case_id = "f620a0ce-02c7-48cb-9d28-5744a148640d"
    ev = Evidence(
        document_id="doc",
        filename="reclamacion.txt",
        chunk_id=None,
        page=None,
        start_char=0,
        end_char=60,
        excerpt="Reclamación de acreedor / embargo",
        extraction_method="txt",
        extraction_confidence=0.9,
    )
    ins = InsolvencyDetection(
        signals_contables=[],
        signals_exigibilidad=[],
        signals_impago=[
            InsolvencySignal(
                signal_type="impago_efectivo",
                description="Reclamación de acreedor con posible embargo (AEAT)",
                evidence=ev,
                severity="concerning",
                amount=None,
            )
        ],
        overall_assessment="Señales de impago.",
        critical_missing_docs=[],
        confidence_level="medium",
    )

    fin = FinancialAnalysisResult(
        case_id=case_id,
        analysis_date=datetime.now(timezone.utc),
        balance=None,
        profit_loss=None,
        credit_classification=[],
        total_debt=None,
        ratios=[],
        insolvency=ins,
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
    assert any(a.source_section == "alerts" for a in apps)

