"""
Servicio de disclaimers legales para mitigar riesgos.

Este módulo centraliza todos los disclaimers que deben aparecer
en outputs de Phoenix Legal para protección legal y claridad.

REGLA CRÍTICA:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phoenix Legal proporciona ASISTENCIA AUTOMATIZADA, no asesoramiento legal.
Todos los outputs deben incluir disclaimer adecuado.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# ════════════════════════════════════════════════════════════════
# DISCLAIMERS ESTÁNDAR
# ════════════════════════════════════════════════════════════════

DISCLAIMER_TECHNICAL = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  IMPORTANTE — NATURALEZA DEL SISTEMA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Este documento ha sido generado por Phoenix Legal, un sistema de asistencia 
técnica automatizada para el análisis preliminar de riesgos legales concursales.

• NO constituye asesoramiento legal ni dictamen jurídico.
• NO sustituye la revisión por parte de asesor legal cualificado.
• Las conclusiones se basan en reglas deterministas y análisis automatizado.
• Se recomienda validación profesional antes de tomar decisiones legales.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()


DISCLAIMER_UI_DEMO = """
⚠️ **DEMO TÉCNICA — NO CONSTITUYE ASESORAMIENTO LEGAL**

Este sistema es una demostración técnica de capacidades de análisis automatizado.
Los resultados deben ser validados por asesor legal cualificado.
""".strip()


DISCLAIMER_DEGRADED = """
⚠️  ANÁLISIS GENERADO SIN MODELO DE LENGUAJE

Las conclusiones presentadas se basan exclusivamente en reglas legales 
deterministas y no incluyen interpretación contextualizada por modelo de lenguaje.
""".strip()


DISCLAIMER_SHORT = """
IMPORTANTE: Este análisis es preliminar y requiere validación por asesor legal.
""".strip()


# ════════════════════════════════════════════════════════════════
# FUNCIONES DE APLICACIÓN
# ════════════════════════════════════════════════════════════════

def add_disclaimer_to_text(
    text: str,
    *,
    disclaimer_type: str = "technical",
    position: str = "end"
) -> str:
    """
    Añade disclaimer a un texto.
    
    Args:
        text: Texto original
        disclaimer_type: Tipo de disclaimer ("technical", "short", "degraded")
        position: Posición ("start" o "end")
    
    Returns:
        Texto con disclaimer añadido
    """
    # Seleccionar disclaimer
    if disclaimer_type == "technical":
        disclaimer = DISCLAIMER_TECHNICAL
    elif disclaimer_type == "short":
        disclaimer = DISCLAIMER_SHORT
    elif disclaimer_type == "degraded":
        disclaimer = DISCLAIMER_DEGRADED
    else:
        disclaimer = DISCLAIMER_TECHNICAL
    
    # Añadir según posición
    if position == "start":
        return f"{disclaimer}\n\n{text}"
    else:  # end
        return f"{text}\n\n{disclaimer}"


def get_disclaimer(disclaimer_type: str = "technical") -> str:
    """
    Obtiene disclaimer por tipo.
    
    Args:
        disclaimer_type: Tipo de disclaimer
    
    Returns:
        Texto del disclaimer
    """
    if disclaimer_type == "technical":
        return DISCLAIMER_TECHNICAL
    elif disclaimer_type == "ui_demo":
        return DISCLAIMER_UI_DEMO
    elif disclaimer_type == "degraded":
        return DISCLAIMER_DEGRADED
    elif disclaimer_type == "short":
        return DISCLAIMER_SHORT
    else:
        return DISCLAIMER_TECHNICAL


# ════════════════════════════════════════════════════════════════
# POST-PROCESADO DE LENGUAJE (MITIGACIÓN DE RIESGO)
# ════════════════════════════════════════════════════════════════

# Mapeo de expresiones absolutas → lenguaje cauteloso
LANGUAGE_REPLACEMENTS = {
    # Verbos de certeza absoluta
    "incumple": "podría incumplir",
    "incumplió": "indicios de incumplimiento de",
    "viola": "posible vulneración de",
    "violó": "indicios de vulneración de",
    "demuestra": "sugiere",
    "demostró": "indicios que sugieren",
    "prueba": "indica",
    "probó": "evidencia que sugiere",
    
    # Juicios categóricos
    "es culpable": "existen indicios que requieren revisión sobre",
    "es responsable de": "posible responsabilidad en",
    "causó": "indicios de que pudo causar",
    "cometió": "posible comisión de",
    
    # Expresiones de certeza
    "sin duda": "según los datos disponibles",
    "definitivamente": "muy probablemente",
    "claramente": "aparentemente",
    "obviamente": "según indicios",
    "es evidente": "los datos sugieren",
    
    # Conclusiones definitivas
    "se concluye que": "los indicios apuntan a que",
    "se determina que": "se identifica como posible que",
    "se establece que": "se observa que",
}


def apply_cautious_language_policy(text: str) -> str:
    """
    Aplica política de lenguaje cauteloso para mitigar riesgo legal.
    
    Reemplaza expresiones absolutas por lenguaje cauteloso:
    - "incumple" → "podría incumplir"
    - "es culpable" → "existen indicios"
    - etc.
    
    Args:
        text: Texto original
    
    Returns:
        Texto con lenguaje cauteloso aplicado
    """
    processed_text = text
    
    for absolute_phrase, cautious_phrase in LANGUAGE_REPLACEMENTS.items():
        # Reemplazar case-insensitive
        import re
        pattern = re.compile(re.escape(absolute_phrase), re.IGNORECASE)
        processed_text = pattern.sub(cautious_phrase, processed_text)
    
    return processed_text


def process_llm_output_safe(
    llm_output: str,
    *,
    add_disclaimer: bool = True,
    apply_language_policy: bool = True
) -> str:
    """
    Procesa output de LLM para hacerlo legalmente seguro.
    
    Args:
        llm_output: Texto generado por LLM
        add_disclaimer: Si True, añade disclaimer
        apply_language_policy: Si True, aplica lenguaje cauteloso
    
    Returns:
        Texto procesado y seguro
    """
    processed = llm_output
    
    # Aplicar política de lenguaje cauteloso
    if apply_language_policy:
        processed = apply_cautious_language_policy(processed)
    
    # Añadir disclaimer
    if add_disclaimer:
        processed = add_disclaimer_to_text(processed, disclaimer_type="short")
    
    return processed


# ════════════════════════════════════════════════════════════════
# VALIDACIÓN DE OUTPUT
# ════════════════════════════════════════════════════════════════

FORBIDDEN_PHRASES = [
    "es culpable",
    "se demuestra la culpabilidad",
    "está probado que",
    "sin lugar a dudas",
    "definitivamente culpable",
    "incumplió intencionalmente",
    "actuó con mala fe demostrada"
]


def validate_output_language(text: str) -> tuple[bool, list[str]]:
    """
    Valida que el texto NO contenga expresiones prohibidas.
    
    Args:
        text: Texto a validar
    
    Returns:
        (is_valid, found_forbidden_phrases)
    """
    found_forbidden = []
    
    for forbidden in FORBIDDEN_PHRASES:
        if forbidden.lower() in text.lower():
            found_forbidden.append(forbidden)
    
    is_valid = len(found_forbidden) == 0
    
    return is_valid, found_forbidden

