"""
Lógica principal del Agente Legal.
"""

import json
import logging
import re
from typing import Dict, Any, Optional, List, Set

from openai import OpenAI

from app.core.variables import RAG_LLM_MODEL, RAG_TEMPERATURE
from .prompt import LEGAL_AGENT_PROMPT

logger = logging.getLogger(__name__)


def _extract_allowed_articles(legal_context: str) -> Set[str]:
    """
    Extrae una lista de artículos permitidos del contexto legal.
    
    Usa regex tolerante para capturar diferentes formatos:
    - Art. 165 LC
    - Artículo 165
    - Art 165
    - Art.165 LC
    
    Args:
        legal_context: Contexto legal completo
        
    Returns:
        Set de strings normalizados con los artículos encontrados (ej: "165", "166")
    """
    if not legal_context:
        return set()
    
    # Patrón regex para capturar números de artículos en diferentes formatos
    # Captura: Art., Artículo, Art seguido de número
    patterns = [
        r'Art\.?\s*(\d+)',  # Art. 165, Art 165, Art.165
        r'Artículo\s*(\d+)',  # Artículo 165
        r'ART\.?\s*(\d+)',  # ART. 165 (mayúsculas)
    ]
    
    # Validación defensiva
    if not legal_context or not isinstance(legal_context, str):
        return set()
    
    allowed_articles = set()
    for pattern in patterns:
        matches = re.findall(pattern, legal_context, re.IGNORECASE)
        allowed_articles.update(matches)
    
    return allowed_articles


def _normalize_article_reference(article_str: str) -> Optional[str]:
    """
    Normaliza una referencia a artículo a un formato estándar.
    
    Ejemplos:
    - "Art. 165 LC" -> "165"
    - "Artículo 166" -> "166"
    - "Art 165" -> "165"
    
    Args:
        article_str: Referencia de artículo en cualquier formato
        
    Returns:
        Número del artículo como string, o None si no se puede extraer
    """
    if not article_str:
        return None
    
    # Intentar extraer el número del artículo
    patterns = [
        r'Art\.?\s*(\d+)',
        r'Artículo\s*(\d+)',
        r'ART\.?\s*(\d+)',
        r'(\d+)',  # Solo número
    ]
    
    for pattern in patterns:
        match = re.search(pattern, article_str, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


def _filter_legal_articles(
    legal_articles: List[str],
    allowed_articles: Set[str],
    legal_context: str
) -> tuple[List[str], List[str]]:
    """
    Filtra artículos legales, dejando solo los permitidos.
    
    Args:
        legal_articles: Lista de artículos citados por el LLM
        allowed_articles: Set de números de artículos permitidos
        legal_context: Contexto legal original (para logging)
        
    Returns:
        Tupla (artículos_válidos, artículos_descartados)
    """
    valid_articles = []
    discarded_articles = []
    
    for article_ref in legal_articles:
        normalized = _normalize_article_reference(article_ref)
        if normalized and normalized in allowed_articles:
            valid_articles.append(article_ref)
        else:
            discarded_articles.append(article_ref)
            logger.warning(
                f"Artículo descartado por no estar en contexto legal: {article_ref}"
            )
    
    return valid_articles, discarded_articles


def legal_agent_logic(
    question: str,
    legal_context: str,
    auditor_summary: Optional[str] = None,
    auditor_risks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Lógica principal del Agente Legal.

    Args:
        question: Pregunta legal específica
        legal_context: Contexto legal obtenido del RAG Legal
        auditor_summary: Resumen del Auditor (opcional)
        auditor_risks: Riesgos detectados por el Auditor (opcional)

    Returns:
        Dict con el resultado del análisis legal
    """
    # Construir contexto del Auditor si está disponible
    auditor_context_parts = []
    if auditor_summary:
        auditor_context_parts.append(f"Resumen del Auditor: {auditor_summary}")
    if auditor_risks:
        auditor_context_parts.append(f"Riesgos detectados: {', '.join(auditor_risks)}")
    
    auditor_context = "\n".join(auditor_context_parts) if auditor_context_parts else "No hay contexto previo del Auditor disponible."

    # Extraer artículos permitidos del contexto legal
    allowed_articles = _extract_allowed_articles(legal_context)
    has_legal_context = bool(legal_context and legal_context.strip() and legal_context != "No hay base legal disponible en el sistema.")

    # Construir el prompt completo
    prompt = LEGAL_AGENT_PROMPT.format(
        auditor_context=auditor_context,
        question=question,
        legal_context=legal_context if legal_context else "No hay base legal disponible en el sistema.",
    )

    # Llamar al LLM
    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model=RAG_LLM_MODEL,
            temperature=RAG_TEMPERATURE,
            messages=[
                {"role": "system", "content": "Eres un experto en Ley Concursal española. Responde siempre con JSON válido."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Respuesta vacía del LLM")

        # Parsear JSON
        result_data = json.loads(content)

        # Validar estructura básica
        if "legal_risks" not in result_data:
            result_data["legal_risks"] = []
        if "legal_conclusion" not in result_data:
            result_data["legal_conclusion"] = "No se pudo generar conclusión legal."
        if "confidence_level" not in result_data:
            result_data["confidence_level"] = "indeterminado"
        if "missing_data" not in result_data:
            result_data["missing_data"] = []
        if "legal_basis" not in result_data:
            result_data["legal_basis"] = []

        # Filtrar artículos legales y detectar alucinaciones
        total_discarded_articles = []
        force_indeterminado = False

        # Si no hay contexto legal, forzar indeterminado
        if not has_legal_context:
            force_indeterminado = True
            result_data["missing_data"].append("Base legal insuficiente: no hay contexto legal disponible.")

        # Validar y normalizar legal_risks
        validated_risks = []
        for risk_data in result_data.get("legal_risks", []):
            # Asegurar campos obligatorios
            if "risk_type" not in risk_data:
                risk_data["risk_type"] = "otro"
            if "description" not in risk_data:
                risk_data["description"] = "Riesgo no especificado"
            if "severity" not in risk_data:
                risk_data["severity"] = "indeterminado"
            if "evidence_status" not in risk_data:
                risk_data["evidence_status"] = "falta"
            if "recommendation" not in risk_data:
                risk_data["recommendation"] = "Revisar documentación"
            if "legal_articles" not in risk_data:
                risk_data["legal_articles"] = []
            if "jurisprudence" not in risk_data:
                risk_data["jurisprudence"] = []

            # Filtrar artículos legales citados
            original_articles = risk_data.get("legal_articles", [])
            valid_articles, discarded_articles = _filter_legal_articles(
                original_articles,
                allowed_articles,
                legal_context
            )
            risk_data["legal_articles"] = valid_articles
            
            # Si se descartaron artículos, forzar indeterminado y ajustar evidence_status
            if discarded_articles:
                force_indeterminado = True
                total_discarded_articles.extend(discarded_articles)
                if risk_data["evidence_status"] in ("suficiente", "insuficiente"):
                    risk_data["evidence_status"] = "insuficiente"
                else:
                    risk_data["evidence_status"] = "falta"
            
            # Si no quedan artículos válidos, ajustar evidence_status
            if not valid_articles and original_articles:
                if risk_data["evidence_status"] not in ("insuficiente", "falta"):
                    risk_data["evidence_status"] = "insuficiente"

            validated_risks.append(risk_data)

        result_data["legal_risks"] = validated_risks

        # Filtrar legal_basis global
        original_basis = result_data.get("legal_basis", [])
        valid_basis, discarded_basis = _filter_legal_articles(
            original_basis,
            allowed_articles,
            legal_context
        )
        result_data["legal_basis"] = valid_basis
        
        if discarded_basis:
            total_discarded_articles.extend(discarded_basis)
            force_indeterminado = True

        # Añadir avisos de artículos descartados
        if total_discarded_articles:
            unique_discarded = list(set(total_discarded_articles))
            discard_msg = f"Artículos citados no presentes en el contexto legal: {', '.join(unique_discarded)}"
            if discard_msg not in result_data["missing_data"]:
                result_data["missing_data"].append(discard_msg)

        # Forzar confidence_level a indeterminado si hay problemas
        if force_indeterminado or not has_legal_context:
            result_data["confidence_level"] = "indeterminado"

        return result_data

    except json.JSONDecodeError as e:
        logger.error(f"Error parseando JSON del LLM: {e}")
        return {
            "legal_risks": [],
            "legal_conclusion": "Error al procesar la respuesta del sistema legal.",
            "confidence_level": "indeterminado",
            "missing_data": ["Error técnico en el procesamiento"],
            "legal_basis": [],
        }
    except Exception as e:
        logger.error(f"Error en legal_agent_logic: {e}")
        return {
            "legal_risks": [],
            "legal_conclusion": f"Error al analizar el caso: {str(e)}",
            "confidence_level": "indeterminado",
            "missing_data": ["Error técnico en el análisis"],
            "legal_basis": [],
        }
