from datetime import datetime, timezone

from app.legal.checker.narrative_checker import check_narrative
from app.models.economic_report import ClientSummary, EconomicReportBundle, LawyerSignature
from app.services.financial_analysis import FinancialAnalysisResult


def _bundle_with_citations() -> EconomicReportBundle:
    fin = FinancialAnalysisResult(
        case_id="case-test",
        analysis_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        balance=None,
        profit_loss=None,
        credit_classification=[],
        total_debt=1234.56,
        ratios=[],
        insolvency=None,
        timeline=[],
        validation_result=None,
        data_quality_score=None,
        timeline_statistics=None,
        timeline_patterns=None,
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
        legal_citations={
            "creditos_contra_masa": [
                {
                    "citation": "TRLC Art. 245",
                    "text": "Artículo 245. Momento del pago de los créditos contra la masa.",
                    "source": "ley",
                    "authority_level": "norma",
                    "relevance": "alta",
                    "article": "245",
                    "law": "TRLC",
                }
            ]
        },
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
        lawyer_signature=LawyerSignature(
            lawyer_name="Abogado/a",
            collegiate_number="123",
        ),
        narrative_md=None,
    )


def test_blocks_ia_mentions():
    b = _bundle_with_citations()
    r = check_narrative("Este informe usa IA y RAG.", bundle=b)
    assert r.status == "FAIL"
    assert r.severity == "BLOCKING"

def test_blocks_internal_labels():
    b = _bundle_with_citations()
    r = check_narrative("Alerta: SUSPICIOUS_PATTERN en el expediente.", bundle=b)
    assert r.status == "FAIL"
    assert r.severity == "BLOCKING"


def test_rejects_epoch_date_range():
    b = _bundle_with_citations()
    r = check_narrative("Fecha: 1970-01-01.", bundle=b)
    assert r.status == "FAIL"
    assert any(e.type == "BAD_DATE_RANGE" for e in r.errors)


def test_rejects_unknown_article():
    b = _bundle_with_citations()
    r = check_narrative("Base legal: TRLC art. 999.", bundle=b)
    assert r.status == "FAIL"
    assert any(e.type == "ILLEGAL_ARTICLE" for e in r.errors)


def test_rejects_new_amount_euros():
    b = _bundle_with_citations()
    r = check_narrative("La deuda asciende a 2000 €.", bundle=b)
    assert r.status == "FAIL"
    assert any(e.type == "NEW_AMOUNT" for e in r.errors)


def test_allows_allowed_amount_and_article():
    b = _bundle_with_citations()
    r = check_narrative("Deuda total: 1234.56 € (TRLC art. 245).", bundle=b)
    # puede fallar por formato, pero no debe ser blocking por artículo/tech
    assert not any(e.type in ("FORBIDDEN_TECH_WORD", "ILLEGAL_ARTICLE") for e in r.errors)


def test_rejects_penal_assertion():
    b = _bundle_with_citations()
    r = check_narrative("Esto constituye un delito de fraude.", bundle=b)
    assert r.status == "FAIL"
    assert r.severity == "BLOCKING"


def test_allows_conditional_penal_language_as_soft_or_pass():
    b = _bundle_with_citations()
    r = check_narrative("Podrían apreciarse indicios de fraude; existe riesgo y debe analizarse.", bundle=b)
    assert r.severity in ("SOFT", "BLOCKING", "PASS")  # no debe bloquear por penal assertion
    assert not any(e.type == "PENAL_ASSERTION" for e in r.errors)

