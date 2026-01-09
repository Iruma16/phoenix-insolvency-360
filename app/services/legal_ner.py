"""
Named Entity Recognition para documentos legales.

FASE 2A: INGESTA MULTI-FORMATO
Objetivo: Extraer entidades clave de documentos legales (avisos, denuncias, resoluciones).

Entidades a extraer:
- Cuantías reclamadas
- Fechas de notificación/vencimiento
- Acreedores/demandantes
- Juzgados/procedimientos
- Plazos de respuesta

Métodos:
1. Regex + heurísticas (patrones legales españoles)
2. GPT-4 (para casos complejos)
"""
from __future__ import annotations

import re
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, date

from app.models.legal_entity import LegalEntity, LegalDocument


# Patrones regex para entidades legales españolas

# Cuantías
AMOUNT_PATTERNS = [
    r'(\d+(?:\.\d{3})*(?:,\d{2})?)\s*€',  # 1.234,56 €
    r'(\d+(?:\.\d{3})*(?:,\d{2})?)\s*euros?',  # 1.234,56 euros
    r'cuant[íi]a\s+de\s+(\d+(?:\.\d{3})*(?:,\d{2})?)',  # cuantía de 1.234,56
    r'importe\s+de\s+(\d+(?:\.\d{3})*(?:,\d{2})?)',  # importe de 1.234,56
    r'reclamaci[óo]n\s+de\s+(\d+(?:\.\d{3})*(?:,\d{2})?)',  # reclamación de 1.234,56
]

# Fechas
DATE_PATTERNS = [
    r'(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})',
    r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})',
]

# Plazos
DEADLINE_PATTERNS = [
    r'plazo\s+de\s+(\d+)\s+d[íi]as?',
    r'en\s+el\s+plazo\s+de\s+(\d+)\s+d[íi]as?',
    r'dentro\s+de\s+(?:los\s+)?(\d+)\s+d[íi]as?',
]

# Juzgados
COURT_PATTERNS = [
    r'Juzgado\s+(?:de\s+)?(?:lo\s+)?([A-Za-z]+(?:\s+[A-Za-z]+)*)\s+(?:n[úu]mero\s+)?(\d+)\s+de\s+([A-Za-z\s]+)',
    r'Tribunal\s+([A-Za-z\s]+)',
]

MONTHS_ES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
}


def extract_amounts_regex(text: str) -> List[LegalEntity]:
    """Extrae cuantías monetarias con regex."""
    entities = []
    
    for pattern in AMOUNT_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            amount_str = match.group(1).replace('.', '').replace(',', '.')
            
            try:
                amount = Decimal(amount_str)
                
                # Contexto (50 chars antes y después)
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]
                
                entity = LegalEntity(
                    entity_type='AMOUNT',
                    value=match.group(0),
                    normalized_value=f"{amount} EUR",
                    amount=amount,
                    currency='EUR',
                    context=context,
                    confidence=0.8,
                    extraction_method='regex',
                    start_char=match.start(),
                    end_char=match.end(),
                )
                entities.append(entity)
            except Exception:
                pass
    
    return entities


def extract_dates_regex(text: str) -> List[LegalEntity]:
    """Extrae fechas con regex."""
    entities = []
    
    # Patrón: "5 de marzo de 2024"
    pattern1 = r'(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})'
    for match in re.finditer(pattern1, text, re.IGNORECASE):
        day = int(match.group(1))
        month = MONTHS_ES[match.group(2).lower()]
        year = int(match.group(3))
        
        try:
            date_value = date(year, month, day)
            
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end]
            
            entity = LegalEntity(
                entity_type='DATE',
                value=match.group(0),
                normalized_value=date_value.isoformat(),
                date_value=date_value,
                context=context,
                confidence=0.9,
                extraction_method='regex',
                start_char=match.start(),
                end_char=match.end(),
            )
            entities.append(entity)
        except Exception:
            pass
    
    # Patrón: "15/03/2024" o "15-03-2024"
    pattern2 = r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})'
    for match in re.finditer(pattern2, text):
        try:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
            
            # Ajustar año de 2 dígitos
            if year < 100:
                year += 2000 if year < 50 else 1900
            
            date_value = date(year, month, day)
            
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end]
            
            entity = LegalEntity(
                entity_type='DATE',
                value=match.group(0),
                normalized_value=date_value.isoformat(),
                date_value=date_value,
                context=context,
                confidence=0.7,  # Menor confianza (formato ambiguo)
                extraction_method='regex',
                start_char=match.start(),
                end_char=match.end(),
            )
            entities.append(entity)
        except Exception:
            pass
    
    return entities


def extract_deadlines_regex(text: str) -> List[LegalEntity]:
    """Extrae plazos con regex."""
    entities = []
    
    for pattern in DEADLINE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            days = match.group(1)
            
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end]
            
            entity = LegalEntity(
                entity_type='DEADLINE',
                value=match.group(0),
                normalized_value=f"{days} días",
                context=context,
                confidence=0.85,
                extraction_method='regex',
                start_char=match.start(),
                end_char=match.end(),
            )
            entities.append(entity)
    
    return entities


def extract_courts_regex(text: str) -> List[LegalEntity]:
    """Extrae juzgados/tribunales con regex."""
    entities = []
    
    for pattern in COURT_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 30)
            context = text[start:end]
            
            entity = LegalEntity(
                entity_type='COURT',
                value=match.group(0),
                normalized_value=match.group(0),
                context=context,
                confidence=0.8,
                extraction_method='regex',
                start_char=match.start(),
                end_char=match.end(),
            )
            entities.append(entity)
    
    return entities


def extract_entities_with_llm(text: str) -> List[LegalEntity]:
    """Extrae entidades usando GPT-4."""
    try:
        from openai import OpenAI
        from app.core.config import settings
        import json
        
        if not settings.openai_api_key:
            return []
        
        client = OpenAI(api_key=settings.openai_api_key)
        
        system_prompt = """Eres un experto en análisis de documentos legales españoles.
Extrae las siguientes entidades del texto:
- AMOUNT: Cuantías monetarias (reclamaciones, deudas, embargos)
- DATE: Fechas relevantes (notificación, vencimiento)
- CREDITOR: Acreedores/demandantes
- DEBTOR: Deudores/demandados
- COURT: Juzgados/tribunales
- DEADLINE: Plazos de respuesta

Responde SOLO con un JSON array de objetos con:
{
  "entity_type": "AMOUNT|DATE|CREDITOR|DEBTOR|COURT|DEADLINE",
  "value": "texto original",
  "normalized_value": "valor normalizado",
  "context": "frase donde aparece"
}"""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Documento:\n\n{text[:3000]}"}  # Limitar a 3000 chars
            ],
            max_tokens=1500,
            temperature=0.0,
        )
        
        content = response.choices[0].message.content
        
        # Limpiar respuesta
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]
        
        entities_data = json.loads(content.strip())
        
        entities = []
        for data in entities_data:
            data['extraction_method'] = 'llm'
            data['confidence'] = 0.9
            try:
                entities.append(LegalEntity(**data))
            except Exception:
                pass
        
        return entities
        
    except Exception as e:
        print(f"⚠️ [NER] Error en extracción con LLM: {e}")
        return []


def extract_legal_entities(text: str, use_llm: bool = True) -> LegalDocument:
    """
    Extrae entidades legales de un documento.
    
    Args:
        text: Texto del documento
        use_llm: Si True, complementa regex con LLM
        
    Returns:
        LegalDocument con entidades extraídas
    """
    print("⚖️ [NER] Extrayendo entidades legales...")
    
    entities = []
    
    # Regex (rápido y determinista)
    entities.extend(extract_amounts_regex(text))
    entities.extend(extract_dates_regex(text))
    entities.extend(extract_deadlines_regex(text))
    entities.extend(extract_courts_regex(text))
    
    print(f"✅ [NER] Regex extrajo {len(entities)} entidades")
    
    # LLM (para entidades complejas)
    if use_llm:
        llm_entities = extract_entities_with_llm(text)
        entities.extend(llm_entities)
        print(f"✅ [NER] LLM extrajo {len(llm_entities)} entidades adicionales")
    
    # Detectar tipo de documento
    text_lower = text.lower()
    if 'embargo' in text_lower or 'embargado' in text_lower:
        doc_type = 'EMBARGO'
    elif 'denuncia' in text_lower or 'demanda' in text_lower:
        doc_type = 'DENUNCIA'
    elif 'resoluci' in text_lower or 'sentencia' in text_lower:
        doc_type = 'RESOLUCION'
    elif 'notificaci' in text_lower:
        doc_type = 'NOTIFICACION'
    else:
        doc_type = 'OTRO'
    
    return LegalDocument(
        document_type=doc_type,
        entities=entities,
    )


def is_legal_document(text: str) -> bool:
    """Detecta si un documento es legal."""
    text_lower = text.lower()
    
    legal_keywords = [
        'juzgado', 'tribunal', 'sentencia', 'resolución',
        'demanda', 'denuncia', 'embargo', 'notificación',
        'procedimiento', 'reclamación', 'acreedor', 'deudor',
    ]
    
    return any(kw in text_lower for kw in legal_keywords)
