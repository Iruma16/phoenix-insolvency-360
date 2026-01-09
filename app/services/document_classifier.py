"""
Clasificador de documentos para priorizar parsers.

FASE 2A: Separa lógica de detección de lógica de parsing.
Reduce complejidad de ingesta.py y facilita testing.
"""
from typing import Literal
from dataclasses import dataclass


DocumentType = Literal[
    'FINANCIAL_STATEMENT',  # Balance, P&G
    'INVOICE',              # Facturas
    'LEGAL_DOCUMENT',       # Denuncias, embargos
    'EMAIL',                # Emails
    'IMAGE_SCANNED',        # Requiere OCR
    'GENERIC',              # Texto genérico
]


@dataclass
class DocumentClassification:
    """Resultado de clasificación de documento."""
    
    document_type: DocumentType
    confidence: float  # 0-1
    reason: str  # Por qué se clasificó así


def classify_document(
    text: str,
    filename: str = "",
    file_extension: str = "",
    is_scanned: bool = False,
) -> DocumentClassification:
    """
    Clasifica un documento según su contenido y tipo de archivo.
    
    ORDEN DE PRIORIDAD:
    1. IMAGE_SCANNED (si is_scanned=True)
    2. EMAIL (si extensión .eml/.msg)
    3. FINANCIAL_STATEMENT (keywords específicos)
    4. INVOICE (keywords específicos)
    5. LEGAL_DOCUMENT (keywords específicos)
    6. GENERIC (fallback)
    
    Args:
        text: Contenido del documento
        filename: Nombre del archivo (opcional)
        file_extension: Extensión (.pdf, .txt, etc.)
        is_scanned: Si es PDF escaneado o imagen
        
    Returns:
        DocumentClassification con tipo, confianza y razón
    """
    text_lower = text.lower()
    
    # 1. OCR necesario
    if is_scanned:
        return DocumentClassification(
            document_type='IMAGE_SCANNED',
            confidence=1.0,
            reason="PDF escaneado o imagen detectada"
        )
    
    # 2. Email
    if file_extension.lower() in ['.eml', '.msg']:
        return DocumentClassification(
            document_type='EMAIL',
            confidence=1.0,
            reason=f"Extensión de email: {file_extension}"
        )
    
    # 3. Estados financieros (PRIORIDAD ALTA)
    financial_keywords = ['balance', 'activo', 'pasivo', 'patrimonio neto']
    financial_score = sum(1 for kw in financial_keywords if kw in text_lower)
    
    if financial_score >= 2:
        return DocumentClassification(
            document_type='FINANCIAL_STATEMENT',
            confidence=0.7 + (financial_score * 0.075),
            reason=f"Keywords financieros: {financial_score}/4"
        )
    
    # 4. Facturas (PRIORIDAD MEDIA)
    invoice_keywords = ['factura', 'invoice', 'total', 'importe', 'iva']
    invoice_score = sum(1 for kw in invoice_keywords if kw in text_lower)
    
    if invoice_score >= 2:
        return DocumentClassification(
            document_type='INVOICE',
            confidence=0.6 + (invoice_score * 0.08),
            reason=f"Keywords factura: {invoice_score}/5"
        )
    
    # 5. Documentos legales (PRIORIDAD BAJA)
    legal_keywords = ['juzgado', 'demanda', 'embargo', 'notificación', 'denuncia']
    legal_score = sum(1 for kw in legal_keywords if kw in text_lower)
    
    if legal_score >= 1:
        return DocumentClassification(
            document_type='LEGAL_DOCUMENT',
            confidence=0.5 + (legal_score * 0.1),
            reason=f"Keywords legales: {legal_score}/5"
        )
    
    # 6. Genérico (fallback)
    return DocumentClassification(
        document_type='GENERIC',
        confidence=0.3,
        reason="No match con patrones conocidos"
    )
