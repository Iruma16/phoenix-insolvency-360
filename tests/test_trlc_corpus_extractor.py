from app.legal.trlc_corpus import get_trlc_article


def test_trlc_article_extraction_smoke():
    art = get_trlc_article(245)
    assert art is not None
    assert art.number == 245
    assert "Artículo 245" in art.text
    # Debe incluir referencia a "créditos contra la masa" en el propio artículo
    assert "créditos contra la masa" in art.text.lower()


def test_trlc_article_extraction_key_articles_smoke():
    # Clasificación y pago
    assert get_trlc_article(280) is not None  # privilegio general
    assert get_trlc_article(433) is not None  # pago ordinarios
    # Calificación del concurso
    assert get_trlc_article(441) is not None
    # Exoneración
    assert get_trlc_article(489) is not None

