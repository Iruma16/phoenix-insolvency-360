from app.core.doc_types import infer_doc_type


def test_infer_doc_type_prioriza_aeat():
    inf = infer_doc_type(
        filename="notificacion_aeat_modelo_303.pdf",
        raw_text_preview="Agencia Tributaria AEAT - Modelo 303 IVA",
    )
    assert inf.doc_type == "AEAT"
    assert 0.0 <= inf.confidence <= 1.0


def test_infer_doc_type_prioriza_tgss():
    inf = infer_doc_type(
        filename="tgss_liquidacion.pdf",
        raw_text_preview="Tesorería General de la Seguridad Social (TGSS) - Liquidación de cuotas",
    )
    assert inf.doc_type == "TGSS"


def test_infer_doc_type_providencia_apremio():
    inf = infer_doc_type(
        filename="providencia_apremio.pdf",
        raw_text_preview="Providencia de apremio. Recaudación ejecutiva.",
    )
    assert inf.doc_type == "PROVIDENCIA_APREMIO"


def test_infer_doc_type_extracto_manda_sobre_factura():
    inf = infer_doc_type(
        filename="extracto_banco_concepto_factura.pdf",
        raw_text_preview="Extracto bancario. IBAN ES12... Saldo. Concepto: factura 123",
    )
    assert inf.doc_type == "EXTRACTO_BANCARIO"
