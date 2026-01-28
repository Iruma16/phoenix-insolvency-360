"""
Parser de documentos contables con extracción estructurada.

FASE 2A: INGESTA MULTI-FORMATO
Objetivo: Reconocer y extraer datos de estados financieros (Balance, P&G, Acreedores).

Métodos:
1. Heurísticas para reconocer tipo de hoja Excel
2. Extracción de cuentas clave por patrones
3. Cálculo automático de ratios

Casos de uso:
- Análisis de solvencia (ratio de liquidez, endeudamiento)
- Detección de fondos propios negativos
- Identificación de pérdidas recurrentes
"""
from __future__ import annotations

import re
from typing import Optional, List, Dict, Any
from decimal import Decimal

import pandas as pd

from app.models.financial_statement import (
    FinancialStatements,
    BalanceSheet,
    IncomeStatement,
    CreditorsList,
)


# Palabras clave para identificar tipo de documento
BALANCE_KEYWORDS = [
    'balance', 'activo', 'pasivo', 'patrimonio neto',
    'activo corriente', 'pasivo corriente',
]

INCOME_KEYWORDS = [
    'pérdidas y ganancias', 'p&g', 'pyg', 'cuenta de resultados',
    'ingresos', 'gastos', 'resultado',
]

CREDITORS_KEYWORDS = [
    'acreedores', 'listado de acreedores', 'relación de acreedores',
    'deudas', 'pasivo exigible',
]


def identify_statement_type(text: str, sheet_name: Optional[str] = None) -> str:
    """
    Identifica el tipo de estado financiero.
    
    Args:
        text: Texto del documento
        sheet_name: Nombre de la hoja (si es Excel)
        
    Returns:
        'BALANCE', 'PYGL', 'ACREEDORES', 'MAYOR', 'OTRO'
    """
    text_lower = text.lower()
    sheet_lower = sheet_name.lower() if sheet_name else ""
    
    combined = text_lower + " " + sheet_lower
    
    # Balance de Situación
    balance_score = sum(1 for kw in BALANCE_KEYWORDS if kw in combined)
    if balance_score >= 2:
        return 'BALANCE'
    
    # Cuenta de Pérdidas y Ganancias
    income_score = sum(1 for kw in INCOME_KEYWORDS if kw in combined)
    if income_score >= 2:
        return 'PYGL'
    
    # Listado de Acreedores
    creditors_score = sum(1 for kw in CREDITORS_KEYWORDS if kw in combined)
    if creditors_score >= 1:
        return 'ACREEDORES'
    
    # Libro Mayor
    if 'mayor' in combined or 'libro mayor' in combined:
        return 'MAYOR'
    
    return 'OTRO'


def extract_balance_from_text(text: str) -> Optional[BalanceSheet]:
    """
    Extrae Balance de Situación desde texto.
    
    Heurística: Busca patrones de cuentas contables españolas.
    """
    balance_data = {}
    
    # Patrones para cuentas clave
    patterns = {
        'activo_corriente': r'activo\s+corriente[:\s]+(\d+(?:\.\d{3})*(?:,\d{2})?)',
        'activo_no_corriente': r'activo\s+no\s+corriente[:\s]+(\d+(?:\.\d{3})*(?:,\d{2})?)',
        'total_activo': r'total\s+activo[:\s]+(\d+(?:\.\d{3})*(?:,\d{2})?)',
        'pasivo_corriente': r'pasivo\s+corriente[:\s]+(\d+(?:\.\d{3})*(?:,\d{2})?)',
        'pasivo_no_corriente': r'pasivo\s+no\s+corriente[:\s]+(\d+(?:\.\d{3})*(?:,\d{2})?)',
        'total_pasivo': r'total\s+pasivo[:\s]+(\d+(?:\.\d{3})*(?:,\d{2})?)',
        'patrimonio_neto': r'patrimonio\s+neto[:\s]+(\d+(?:\.\d{3})*(?:,\d{2})?)',
    }
    
    for field, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace('.', '').replace(',', '.')
            try:
                balance_data[field] = Decimal(amount_str)
            except Exception:
                pass
    
    if balance_data:
        return BalanceSheet(**balance_data)
    
    return None


def extract_income_from_text(text: str) -> Optional[IncomeStatement]:
    """
    Extrae Cuenta de Pérdidas y Ganancias desde texto.
    """
    income_data = {}
    
    patterns = {
        'ingresos_explotacion': r'ingresos?\s+(?:de\s+)?explotaci[óo]n[:\s]+(\d+(?:\.\d{3})*(?:,\d{2})?)',
        'gastos_explotacion': r'gastos?\s+(?:de\s+)?explotaci[óo]n[:\s]+(\d+(?:\.\d{3})*(?:,\d{2})?)',
        'resultado_neto': r'resultado\s+neto[:\s]+(-?\d+(?:\.\d{3})*(?:,\d{2})?)',
    }
    
    for field, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace('.', '').replace(',', '.')
            try:
                income_data[field] = Decimal(amount_str)
            except Exception:
                pass
    
    if income_data:
        return IncomeStatement(**income_data)
    
    return None


def parse_financial_statement_from_text(text: str) -> Optional[FinancialStatements]:
    """
    Parsea un estado financiero desde texto plano.
    
    Args:
        text: Texto del documento
        
    Returns:
        FinancialStatements o None
    """
    statement_type = identify_statement_type(text)
    
    if statement_type == 'OTRO':
        return None
    
    print(f"📊 [ACCOUNTING] Tipo detectado: {statement_type}")
    
    fields_extracted = 0
    total_fields = 0
    
    financial_stmt = FinancialStatements(
        statement_type=statement_type,
        extraction_method='regex',
        confidence=0.5,
    )
    
    if statement_type == 'BALANCE':
        balance = extract_balance_from_text(text)
        if balance:
            financial_stmt.balance = balance
            # Contar campos extraídos
            total_fields = 7
            fields_extracted = sum([
                balance.total_activo is not None,
                balance.total_pasivo is not None,
                balance.patrimonio_neto is not None,
                balance.activo_corriente is not None,
                balance.pasivo_corriente is not None,
                balance.activo_no_corriente is not None,
                balance.pasivo_no_corriente is not None,
            ])
            print(f"✅ [ACCOUNTING] Balance extraído: Total Activo={balance.total_activo}€")
    
    elif statement_type == 'PYGL':
        income = extract_income_from_text(text)
        if income:
            financial_stmt.income_statement = income
            # Contar campos extraídos
            total_fields = 3
            fields_extracted = sum([
                income.ingresos_explotacion is not None,
                income.gastos_explotacion is not None,
                income.resultado_neto is not None,
            ])
            print(f"✅ [ACCOUNTING] P&G extraído: Resultado Neto={income.resultado_neto}€")
    
    # Si no se extrajo nada útil, retornar None
    if not financial_stmt.balance and not financial_stmt.income_statement:
        return None
    
    # Calcular confidence basado en completitud
    if total_fields > 0:
        financial_stmt.confidence = 0.5 + (fields_extracted / total_fields) * 0.4
        print(f"📊 [ACCOUNTING] Confidence: {financial_stmt.confidence:.2f} ({fields_extracted}/{total_fields} campos)")
    
    # Detectar indicadores de insolvencia
    indicadores = financial_stmt.detectar_insolvencia()
    if indicadores:
        print(f"⚠️ [ACCOUNTING] Indicadores de insolvencia detectados:")
        for ind in indicadores:
            print(f"  - {ind}")
    
    return financial_stmt


def is_financial_statement(text: str) -> bool:
    """
    Detecta si un documento es un estado financiero.
    
    Args:
        text: Texto del documento
        
    Returns:
        True si parece un estado financiero
    """
    statement_type = identify_statement_type(text)
    return statement_type != 'OTRO'
