"""
Parser de facturas con extracción estructurada.

FASE 2A: INGESTA MULTI-FORMATO
Objetivo: Extraer campos clave de facturas para análisis automatizado.

Métodos:
1. Regex + heurísticas (facturas españolas estándar)
2. GPT-4 Vision (facturas en PDF/imagen)
3. Extracción de tablas (facturas en Excel)

Casos de uso:
- Análisis de saldos pendientes
- Detección de facturas vencidas
- Timeline de pagos/impagos
- Cálculo de deuda total
"""
from __future__ import annotations

import re
import json
from typing import Optional, Dict, Any
from decimal import Decimal
from datetime import datetime

from app.models.invoice import StructuredInvoice, InvoiceLineItem


# Patrones regex para facturas españolas
INVOICE_NUMBER_PATTERNS = [
    r'N[úu]mero\s*(?:de\s*)?[Ff]actura[:\s]+([A-Z0-9\-/]+)',
    r'Factura\s+N[úu]m[:\.\s]+([A-Z0-9\-/]+)',
    r'Factura[:\s]+([A-Z0-9\-/]+)',
    r'N[°º]\s*Factura[:\s]+([A-Z0-9\-/]+)',
]

DATE_PATTERNS = [
    r'Fecha\s*(?:de\s*)?[Ee]misi[óo]n[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    r'Fecha[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
]

TOTAL_PATTERNS = [
    r'Total[:\s]+(\d+[.,]\d{2})\s*€?',
    r'Importe\s+Total[:\s]+(\d+[.,]\d{2})\s*€?',
    r'TOTAL[:\s]+(\d+[.,]\d{2})\s*€?',
]

NIF_PATTERN = r'[A-Z]?\d{7,8}[A-Z]?'


def extract_invoice_with_regex(text: str) -> Optional[StructuredInvoice]:
    """
    Extrae datos de factura usando regex y heurísticas.
    
    Args:
        text: Texto de la factura
        
    Returns:
        StructuredInvoice o None si no se detecta factura
    """
    # Detectar si es una factura
    if not re.search(r'factura|invoice', text, re.IGNORECASE):
        return None
    
    invoice_data = {
        'extraction_method': 'regex',
        'confidence': 0.6,  # Regex tiene confianza media
    }
    
    # Extraer número de factura
    for pattern in INVOICE_NUMBER_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            invoice_data['invoice_number'] = match.group(1).strip()
            break
    
    # Extraer fechas
    dates_found = []
    for pattern in DATE_PATTERNS:
        matches = re.findall(pattern, text)
        dates_found.extend(matches)
    
    if dates_found:
        # Primera fecha suele ser emisión
        invoice_data['issue_date'] = dates_found[0]
        if len(dates_found) > 1:
            # Segunda fecha puede ser vencimiento
            invoice_data['due_date'] = dates_found[1]
    
    # Extraer total
    for pattern in TOTAL_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(',', '.')
            try:
                invoice_data['total_amount'] = Decimal(amount_str)
            except Exception:
                pass
            break
    
    # Extraer NIFs (heurística: primer NIF = proveedor, segundo = cliente)
    nifs = re.findall(NIF_PATTERN, text)
    if nifs:
        invoice_data['supplier_tax_id'] = nifs[0]
        if len(nifs) > 1:
            invoice_data['customer_tax_id'] = nifs[1]
    
    # Si no tenemos total, no es una factura válida
    if 'total_amount' not in invoice_data:
        return None
    
    try:
        return StructuredInvoice(**invoice_data)
    except Exception as e:
        print(f"⚠️ [INVOICE] Error creando StructuredInvoice: {e}")
        return None


def extract_invoice_with_llm(text: str, use_vision: bool = False, image_bytes: Optional[bytes] = None) -> Optional[StructuredInvoice]:
    """
    Extrae datos de factura usando GPT-4 (o GPT-4 Vision).
    
    Args:
        text: Texto de la factura
        use_vision: Si True, usa GPT-4 Vision con imagen
        image_bytes: Bytes de la imagen (si use_vision=True)
        
    Returns:
        StructuredInvoice o None
    """
    try:
        from openai import OpenAI
        from app.core.config import settings
        
        if not settings.openai_api_key:
            print("⚠️ [INVOICE] OpenAI API key no configurada")
            return None
        
        client = OpenAI(api_key=settings.openai_api_key)
        
        # Prompt para extracción estructurada
        system_prompt = """Eres un experto en extracción de datos de facturas.
Extrae la siguiente información de la factura proporcionada:
- invoice_number: Número de factura
- issue_date: Fecha de emisión (formato YYYY-MM-DD)
- due_date: Fecha de vencimiento (formato YYYY-MM-DD)
- supplier_name: Nombre del proveedor
- supplier_tax_id: NIF/CIF del proveedor
- customer_name: Nombre del cliente
- customer_tax_id: NIF/CIF del cliente
- subtotal: Base imponible (número decimal)
- tax_amount: Importe IVA (número decimal)
- total_amount: Importe total (número decimal)

Responde SOLO con un JSON válido con estos campos. Si un campo no está presente, usa null."""

        if use_vision and image_bytes:
            # GPT-4 Vision
            import base64
            
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            response = client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                }
                            },
                            {
                                "type": "text",
                                "text": "Extrae los datos de esta factura."
                            }
                        ]
                    }
                ],
                max_tokens=1000,
                temperature=0.0,
            )
        else:
            # GPT-4 estándar
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Factura:\n\n{text[:4000]}"}  # Limitar a 4000 chars
                ],
                max_tokens=1000,
                temperature=0.0,
            )
        
        # Parsear respuesta JSON
        content = response.choices[0].message.content
        
        # Limpiar respuesta (a veces GPT añade markdown)
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]
        
        invoice_data = json.loads(content.strip())
        invoice_data['extraction_method'] = 'llm_vision' if use_vision else 'llm'
        invoice_data['confidence'] = 0.9  # LLM tiene alta confianza
        
        return StructuredInvoice(**invoice_data)
        
    except Exception as e:
        print(f"❌ [INVOICE] Error en extracción con LLM: {e}")
        return None


def parse_invoice_from_text(text: str) -> Optional[StructuredInvoice]:
    """
    Parsea una factura desde texto plano.
    
    Intenta primero regex, luego LLM si está disponible.
    
    Args:
        text: Texto de la factura
        
    Returns:
        StructuredInvoice o None
    """
    # Intentar regex primero (más rápido y barato)
    invoice = extract_invoice_with_regex(text)
    
    if invoice:
        # Calcular confidence basado en campos completados
        fields_found = sum([
            invoice.invoice_number is not None,
            invoice.issue_date is not None,
            invoice.total_amount is not None,
            invoice.supplier_tax_id is not None,
            invoice.customer_tax_id is not None,
        ])
        # Ajustar: 0.5 base + 0.1 por campo
        invoice.confidence = 0.5 + (fields_found * 0.1)
        
        if invoice.confidence > 0.8:
            print(f"✅ [INVOICE] Factura extraída con regex (confianza={invoice.confidence:.2f})")
            return invoice
    
    # Si regex falla o tiene baja confianza, intentar LLM
    print("🤖 [INVOICE] Intentando extracción con LLM...")
    invoice_llm = extract_invoice_with_llm(text)
    
    if invoice_llm:
        print(f"✅ [INVOICE] Factura extraída con LLM (confianza={invoice_llm.confidence})")
        return invoice_llm
    
    # Si LLM también falla, retornar resultado de regex (aunque sea parcial)
    return invoice


def parse_invoice_from_image(image_bytes: bytes) -> Optional[StructuredInvoice]:
    """
    Parsea una factura desde imagen usando GPT-4 Vision.
    
    Args:
        image_bytes: Bytes de la imagen
        
    Returns:
        StructuredInvoice o None
    """
    print("🤖 [INVOICE] Extrayendo factura de imagen con GPT-4 Vision...")
    return extract_invoice_with_llm("", use_vision=True, image_bytes=image_bytes)


def is_likely_invoice(text: str) -> bool:
    """
    Detecta si un documento es probablemente una factura.
    
    Heurística simple basada en palabras clave.
    
    Args:
        text: Texto del documento
        
    Returns:
        True si parece una factura
    """
    text_lower = text.lower()
    
    # Palabras clave que indican factura
    invoice_keywords = ['factura', 'invoice', 'n° factura', 'número de factura']
    amount_keywords = ['total', 'importe', 'base imponible', 'iva']
    
    has_invoice_keyword = any(kw in text_lower for kw in invoice_keywords)
    has_amount_keyword = any(kw in text_lower for kw in amount_keywords)
    
    return has_invoice_keyword and has_amount_keyword
