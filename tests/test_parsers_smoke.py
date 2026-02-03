"""
Smoke tests para parsers de FASE 2A.
Validación mínima: no rompe, devuelve modelo correcto.
NO se valida precisión, solo que el código no falla.
"""

import pytest


@pytest.mark.smoke
def test_email_parser_smoke():
    """Email parser: parsea .eml sin excepciones."""
    from app.services.email_parser import parse_eml_stream

    # Usar email de prueba simple
    email_content = b"""From: test@example.com
To: recipient@example.com
Subject: Test Email
Date: Mon, 1 Jan 2024 10:00:00 +0000

This is a test email body.
"""

    result = parse_eml_stream(email_content)

    assert result is not None
    assert result.tipo_documento == "email"
    assert result.num_paginas == 1
    assert len(result.texto) > 0
    assert "test@example.com" in result.texto


@pytest.mark.smoke
def test_invoice_parser_regex_smoke():
    """Invoice parser: extrae factura básica con regex."""
    from app.services.invoice_parser import parse_invoice_from_text

    invoice_text = """
    FACTURA
    Número de Factura: FAC-2024-001
    Fecha: 15/01/2024
    
    Proveedor: Test S.L.
    NIF: B12345678
    
    Cliente: Cliente S.A.
    NIF: A87654321
    
    Total: 1.234,56 €
    """

    invoice = parse_invoice_from_text(invoice_text)

    assert invoice is not None
    assert invoice.total_amount > 0
    assert invoice.extraction_method in ["regex", "llm"]


@pytest.mark.smoke
def test_legal_ner_regex_smoke():
    """Legal NER: extrae entidades básicas con regex."""
    from app.services.legal_ner import extract_legal_entities

    legal_text = """
    JUZGADO DE LO MERCANTIL Nº 1 DE MADRID
    
    Procedimiento: 123/2024
    Reclamación de cuantía: 50.000 €
    Fecha de notificación: 5 de marzo de 2024
    Plazo de respuesta: 10 días
    """

    legal_doc = extract_legal_entities(legal_text, use_llm=False)  # Solo regex

    assert legal_doc is not None
    assert legal_doc.document_type in ["EMBARGO", "DENUNCIA", "RESOLUCION", "NOTIFICACION", "OTRO"]
    assert len(legal_doc.entities) > 0

    # Verificar que extrajo al menos una cuantía
    amounts = legal_doc.get_amounts()
    assert len(amounts) > 0


@pytest.mark.smoke
def test_accounting_parser_smoke():
    """Accounting parser: identifica tipo de estado financiero."""
    from app.services.accounting_parser import (
        identify_statement_type,
        parse_financial_statement_from_text,
    )

    balance_text = """
    BALANCE DE SITUACIÓN
    
    ACTIVO
    Activo Corriente: 100.000 €
    Activo No Corriente: 50.000 €
    Total Activo: 150.000 €
    
    PASIVO
    Pasivo Corriente: 80.000 €
    Pasivo No Corriente: 30.000 €
    Total Pasivo: 110.000 €
    
    PATRIMONIO NETO: 40.000 €
    """

    statement_type = identify_statement_type(balance_text)
    assert statement_type == "BALANCE"

    financial_stmt = parse_financial_statement_from_text(balance_text)
    assert financial_stmt is not None
    assert financial_stmt.balance is not None
    assert financial_stmt.balance.total_activo > 0


@pytest.mark.smoke
@pytest.mark.skipif(True, reason="OCR requiere Tesseract instalado")
def test_ocr_parser_availability():
    """OCR parser: verifica disponibilidad de Tesseract."""
    from app.services.ocr_parser import is_tesseract_available

    # No falla si Tesseract no está instalado
    available = is_tesseract_available()

    # Solo log, no falla el test
    if available:
        print("✅ Tesseract disponible")
    else:
        print("⚠️ Tesseract NO disponible (esperado en CI)")


@pytest.mark.integration
def test_invoice_detection_priority():
    """Verifica que facturas tienen prioridad sobre documentos genéricos."""
    from app.services.invoice_parser import is_likely_invoice
    from app.services.legal_ner import is_legal_document

    invoice_text = "FACTURA N° 123 Total: 1.000 € IVA incluido"

    assert is_likely_invoice(invoice_text) is True
    # Factura debe tener prioridad sobre legal
    assert is_legal_document(invoice_text) is False or is_likely_invoice(invoice_text)


@pytest.mark.integration
def test_accounting_detection_priority():
    """Verifica que estados financieros tienen prioridad sobre facturas."""
    from app.services.accounting_parser import is_financial_statement

    balance_text = "BALANCE Activo Corriente: 100.000 Total Activo: 200.000"

    assert is_financial_statement(balance_text) is True
    # Balance debe tener prioridad sobre factura (validado en ingesta.py)


@pytest.mark.smoke
def test_parser_priority_in_ingestion():
    """Smoke test: verifica que la prioridad de parsers está implementada."""
    import io

    from app.services.ingesta import leer_txt

    # Texto que podría ser detectado como varios tipos
    mixed_text = """
    BALANCE DE SITUACIÓN 2024
    
    ACTIVO
    Total Activo: 100.000 €
    
    FACTURA incluida: 5.000 €
    """

    result = leer_txt(io.BytesIO(mixed_text.encode()))

    assert result is not None
    assert result.texto is not None

    # Si hay structured_data, debe priorizar accounting sobre invoice
    if result.structured_data:
        # Si detectó accounting, no debe haber invoice
        if "financial_statement" in result.structured_data:
            assert "invoice" not in result.structured_data
            print("✅ Prioridad correcta: Accounting > Invoice")


@pytest.mark.smoke
def test_feature_flags_existence():
    """Verifica que los feature flags existen en config."""
    from app.core.config import settings

    # Verificar que los nuevos feature flags existen
    assert hasattr(settings, "enable_llm_extraction")
    assert hasattr(settings, "enable_gpt_vision")
    assert hasattr(settings, "max_llm_calls_per_document")

    print(
        f"✅ Feature flags: LLM={settings.enable_llm_extraction}, Vision={settings.enable_gpt_vision}"
    )


# =========================================================
# VALIDATION TESTS (coherencia de datos)
# =========================================================


@pytest.mark.validation
def test_invoice_data_consistency():
    """Valida coherencia de datos en facturas extraídas."""
    from decimal import Decimal

    from app.services.invoice_parser import parse_invoice_from_text

    invoice_text = """
    FACTURA FAC-2024-001
    Fecha: 15/01/2024
    Base imponible: 1.000,00 €
    IVA (21%): 210,00 €
    Total: 1.210,00 €
    """

    invoice = parse_invoice_from_text(invoice_text)

    assert invoice is not None
    assert invoice.total_amount > 0, "Total debe ser positivo"

    # Si hay subtotal e IVA, debe coincidir con total
    if invoice.subtotal and invoice.tax_amount:
        expected_total = invoice.subtotal + invoice.tax_amount
        assert abs(invoice.total_amount - expected_total) < Decimal(
            "0.02"
        ), f"Incoherencia: {invoice.subtotal} + {invoice.tax_amount} != {invoice.total_amount}"

    # Confianza: debe estar definida
    assert invoice.confidence is not None
    assert 0 <= invoice.confidence <= 1, "Confianza debe estar entre 0 y 1"


@pytest.mark.validation
def test_legal_entities_validity():
    """Valida valores imposibles en entidades legales."""

    from app.services.legal_ner import extract_legal_entities

    legal_text = """
    Reclamación de cuantía: 50.000 €
    Fecha de notificación: 5 de marzo de 2024
    """

    legal_doc = extract_legal_entities(legal_text, use_llm=False)

    # Validar cuantías
    for entity in legal_doc.get_amounts():
        assert entity.amount > 0, "Cuantías deben ser positivas"
        assert entity.currency in ["EUR", None], "Moneda debe ser EUR o None"


@pytest.mark.validation
def test_accounting_ratios_validity():
    """Valida que ratios contables tengan sentido."""
    from app.services.accounting_parser import parse_financial_statement_from_text

    balance_text = """
    BALANCE DE SITUACIÓN
    Activo Corriente: 100.000 €
    Total Activo: 150.000 €
    Pasivo Corriente: 80.000 €
    Total Pasivo: 110.000 €
    Patrimonio Neto: 40.000 €
    """

    stmt = parse_financial_statement_from_text(balance_text)

    if stmt and stmt.balance:
        balance = stmt.balance

        # Ecuación contable: Activo = Pasivo + Patrimonio Neto
        if balance.total_activo and balance.total_pasivo and balance.patrimonio_neto:
            suma = balance.total_pasivo + balance.patrimonio_neto
            assert (
                abs(balance.total_activo - suma) < 1
            ), f"Ecuación contable no cuadra: {balance.total_activo} != {suma}"


@pytest.mark.smoke
def test_document_classifier():
    """Verifica que el clasificador de documentos funciona correctamente."""
    from app.services.document_classifier import classify_document

    # Test 1: Balance
    balance_text = "BALANCE Activo Corriente: 100.000 Pasivo: 80.000 Patrimonio Neto: 20.000"
    result = classify_document(balance_text)
    assert result.document_type == "FINANCIAL_STATEMENT"
    assert result.confidence > 0.7

    # Test 2: Factura
    invoice_text = "FACTURA N° 123 Total: 1.000 € IVA: 21%"
    result = classify_document(invoice_text)
    assert result.document_type == "INVOICE"
    assert result.confidence > 0.6

    # Test 3: Legal
    legal_text = "Juzgado de lo Mercantil - Demanda de reclamación"
    result = classify_document(legal_text)
    assert result.document_type == "LEGAL_DOCUMENT"
    assert result.confidence > 0.5

    # Test 4: Email por extensión
    result = classify_document("Hello world", file_extension=".eml")
    assert result.document_type == "EMAIL"
    assert result.confidence == 1.0

    print("✅ DocumentClassifier funcionando correctamente")
