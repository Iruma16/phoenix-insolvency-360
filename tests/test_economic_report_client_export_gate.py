from datetime import datetime, timezone

import pytest

from app.legal.checker.export_checker import check_export
from app.models.economic_report import ClientSummary, EconomicReportBundle
from app.services.financial_analysis import FinancialAnalysisResult


def _bundle_minimal(*, with_signature: bool) -> EconomicReportBundle:
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
            headline="Situación económica no determinable con la documentación actual.",
            situation="no_determinable",
            key_points=[],
            next_7_days=[],
            warnings=[],
        ),
        documents_presented=[],
        documents_missing=[],
        documents_recommended=[],
        lawyer_signature=None,
        narrative_md=None,
        narrative_contract=None,
    )
    if with_signature:
        b.lawyer_signature = {
            "lawyer_name": "Abogado/a",
            "collegiate_number": "12345",
            "bar_association": "ICAM",
            "law_firm": "Despacho",
            "office_city": "Madrid",
        }
    return b


def test_client_export_blocks_without_signature():
    b = _bundle_minimal(with_signature=False)
    report = check_export(b, audience="client")
    assert report.ok is False
    assert any(v.rule_id == "R3" and v.action == "BLOCK_CLIENT_OUTPUT" for v in report.violations)


def test_internal_allows_without_signature():
    b = _bundle_minimal(with_signature=False)
    report = check_export(b, audience="internal")
    assert report.ok is True

