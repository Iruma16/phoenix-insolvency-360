from datetime import datetime, timezone

from app.legal.checker.export_checker import check_export
from app.models.economic_report import (
    ClientSummary,
    DebtLegalApplication,
    DebtLegalOption,
    DebtRisk,
    EconomicReportBundle,
    LawyerSignature,
    NarrativeContract,
)
from app.services.financial_analysis import FinancialAnalysisResult


def _bundle_with_debt_option(*, narrative_md: str) -> EconomicReportBundle:
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

    debt = DebtLegalApplication(
        debt_id="debt_x_001",
        creditor_name="AEAT",
        creditor_type="public",
        source_section="financial",
        amount_eur=1000.0,
        amount_confidence="exact",
        period_start=None,
        period_end=None,
        period_note="No consta período exacto en la documentación aportada",
        has_security=None,
        security_type=None,
        security_note="No consta garantía real asociada en la documentación aportada",
        proposed_trlc_bucket="no_determinable",
        classification_basis="A determinar con documentación adicional.",
        classification_confidence="low",
        trlc_articles=[],
        legal_options=[
            DebtLegalOption(
                option_code="gather_docs",
                description="Completar documentación.",
                prerequisites="Requiere certificados.",
                legal_basis_refs=[],
                warnings=[],
            )
        ],
        practical_consequences=[],
        risks=[DebtRisk(risk_level="low", statement="Existe riesgo de recargos.", related_refs=[])],
        evidence_refs=[],
        client_ready_summary="Consta deuda con AEAT por importe de 1.000,00 €.",
    )

    contract = NarrativeContract(
        case={"case_id": "case-test", "case_name": "ACME SL", "debtor_type": "company"},
        client_summary={},
        documents={},
        financial={},
        insolvency_signals=[],
        alerts=[],
        allowed_recommendations=[],
        legal_citations={},
        debt_legal_applications=[debt],
    )

    return EconomicReportBundle(
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
        narrative_md=narrative_md,
        narrative_contract=contract,
    )


def test_r13_blocks_unauthorized_recommendation_in_client():
    b = _bundle_with_debt_option(narrative_md="Se recomienda vender activos para obtener liquidez.")
    rep = check_export(b, audience="client")
    assert rep.ok is False
    assert any(v.rule_id == "R13" and v.action == "BLOCK_CLIENT_OUTPUT" for v in rep.violations)


def test_r13_allows_allowed_gather_docs_recommendation():
    b = _bundle_with_debt_option(
        narrative_md="Se recomienda recopilar la documentación y obtener certificados del acreedor."
    )
    rep = check_export(b, audience="client")
    assert rep.ok is True
    assert not any(v.rule_id == "R13" for v in rep.violations)


def test_r13_does_not_block_warning_style_avoidance():
    b = _bundle_with_debt_option(
        narrative_md="Se recomienda evitar pagos selectivos mientras se ordena el expediente."
    )
    rep = check_export(b, audience="client")
    assert rep.ok is True
    assert not any(v.rule_id == "R13" for v in rep.violations)
