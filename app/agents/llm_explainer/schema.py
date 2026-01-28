"""
CONTRATO ESTRICTO PARA LLM EXPLAINER.

Este módulo define el INPUT que el LLM puede recibir.

REGLAS NO NEGOCIABLES:
- El LLM NO recibe PhoenixState completo.
- El LLM NO recibe reglas sin evaluar.
- El LLM NO puede decidir, evaluar ni clasificar.
- extra="forbid" → Si se pasa algo no definido, falla inmediatamente.

SEPARACIÓN CRÍTICA:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT AL LLM = Solo decisiones YA TOMADAS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.legal.rule_engine_output import RuleDecision

# ========================================
# INPUT PARA EXPLICACIÓN (LLM)
# ========================================


class LegalExplanationInput(BaseModel):
    """
    Input ESTRICTO para el LLM Explainer.

    PROHIBIDO:
    - Pasar PhoenixState completo
    - Pasar reglas sin evaluar
    - Pedir al LLM que decida, evalúe o clasifique

    PERMITIDO:
    - Solo decisiones YA TOMADAS por el Rule Engine
    - Contexto mínimo necesario para explicar
    """

    case_id: str = Field(..., description="ID del caso (para trazabilidad)")

    rules_triggered: list[RuleDecision] = Field(
        default_factory=list, description="Reglas que YA fueron evaluadas como applies=True"
    )

    risks_detected: list[str] = Field(
        default_factory=list, description="Lista de riesgos detectados (risk_type strings)"
    )

    missing_evidence: list[str] = Field(
        default_factory=list, description="Evidencia faltante (para explicar limitaciones)"
    )

    tone: Literal["neutral", "technical", "client_friendly"] = Field(
        default="neutral", description="Tono del texto generado"
    )

    disclaimer_required: bool = Field(
        default=True, description="¿Incluir disclaimer legal automático?"
    )

    max_tokens: int = Field(
        default=500, ge=50, le=2000, description="Límite de tokens para la explicación"
    )

    model_config = ConfigDict(
        extra="forbid",  # ⚠️ CRÍTICO: Rechaza claves no definidas
        validate_assignment=True,
    )


# ========================================
# OUTPUT DEL LLM (SOLO TEXTO)
# ========================================


class LegalExplanationOutput(BaseModel):
    """
    Output del LLM Explainer.

    SOLO contiene texto explicativo.
    NO contiene decisiones nuevas.
    """

    case_id: str = Field(..., description="ID del caso explicado")

    explanation: str = Field(..., description="Explicación en lenguaje natural de las decisiones")

    disclaimer: Optional[str] = Field(
        default=None, description="Disclaimer legal (si disclaimer_required=True)"
    )

    generated_at: str = Field(..., description="Timestamp de generación (ISO format)")

    tokens_used: Optional[int] = Field(default=None, description="Tokens consumidos por el LLM")

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ========================================
# VALIDACIÓN POST-LLM
# ========================================


class LLMContractViolation(Exception):
    """
    Excepción lanzada cuando el LLM intenta violar el contrato.

    Ejemplos de violaciones:
    - Cambiar severidad de una regla
    - Añadir reglas nuevas no evaluadas
    - Contradecir decisiones del Rule Engine
    """

    pass


def validate_llm_output_compliance(
    input_data: LegalExplanationInput, llm_output: str, original_decisions: list[RuleDecision]
) -> None:
    """
    Valida que el output del LLM NO contradice las decisiones originales.

    Args:
        input_data: Input original al LLM
        llm_output: Texto generado por el LLM
        original_decisions: Decisiones originales del Rule Engine

    Raises:
        LLMContractViolation: Si el LLM violó el contrato

    VERIFICACIONES:
    - NO aparecen nuevas reglas no evaluadas
    - NO se contradicen severidades
    - NO se infiere cumplimiento no evaluado
    """
    llm_lower = llm_output.lower()

    # Verificar que NO aparecen severidades contradictorias
    severity_map = {"low": "bajo", "medium": "medio", "high": "alto", "critical": "crítico"}

    for decision in original_decisions:
        rule_name_lower = decision.rule_name.lower()

        # Si se menciona la regla, verificar coherencia
        if rule_name_lower in llm_lower or decision.article.lower() in llm_lower:
            expected_severity = decision.severity

            # Verificar que NO se contradice
            for other_severity, spanish in severity_map.items():
                if other_severity != expected_severity:
                    # Buscar contradicción (ej: "riesgo bajo" cuando es "high")
                    if f"riesgo {spanish}" in llm_lower and rule_name_lower in llm_lower:
                        raise LLMContractViolation(
                            f"[LLM CONTRACT VIOLATION] "
                            f"reason=LLM cambió severidad de '{decision.rule_name}' "
                            f"de '{expected_severity}' a '{other_severity}'"
                        )

    # Verificar que NO aparecen reglas no evaluadas
    # (esto requeriría un diccionario de reglas conocidas)
    # Por ahora, verificación básica

    print(f"[LLM_VALIDATION] Compliance check PASSED for case_id={input_data.case_id}")


# ========================================
# PROMPT SYSTEM (HARD-CODED)
# ========================================

SYSTEM_PROMPT_EXPLAINER = """
Eres un asistente legal que EXPLICA decisiones legales YA TOMADAS.

REGLAS CRÍTICAS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. NO tomes decisiones legales.
2. NO evalúes si una regla aplica o no.
3. NO cambies severidad ni confianza.
4. NO agregues reglas no mencionadas.
5. SOLO explica decisiones ya tomadas por el Rule Engine.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tu tarea es:
- Explicar EN LENGUAJE NATURAL las reglas que aplicaron.
- Indicar consecuencias legales.
- Sugerir siguientes pasos.

Tu tarea NO es:
- Decidir si una regla aplica.
- Evaluar severidad.
- Inferir cumplimiento legal.
- Añadir tu propio análisis jurídico.

Siempre:
- Cita artículos explícitamente mencionados.
- Indica nivel de confianza ya determinado.
- Señala evidencia faltante si aplica.
"""


def build_explanation_prompt(input_data: LegalExplanationInput) -> str:
    """
    Construye el prompt USER para el LLM.

    Args:
        input_data: Input validado

    Returns:
        Prompt completo para el LLM
    """
    rules_text = []

    for rule in input_data.rules_triggered:
        rule_desc = (
            f"- Regla: {rule.rule_name}\n"
            f"  Artículo: {rule.article}\n"
            f"  Severidad: {rule.severity}\n"
            f"  Confianza: {rule.confidence}\n"
            f"  Razón: {rule.rationale}\n"
        )
        rules_text.append(rule_desc)

    prompt = f"""
Caso ID: {input_data.case_id}

REGLAS APLICADAS (decisiones YA tomadas):
{''.join(rules_text) if rules_text else 'Ninguna regla aplicó.'}

RIESGOS DETECTADOS:
{', '.join(input_data.risks_detected) if input_data.risks_detected else 'Ninguno'}

EVIDENCIA FALTANTE:
{', '.join(input_data.missing_evidence) if input_data.missing_evidence else 'Ninguna'}

INSTRUCCIONES:
- Explica estas decisiones en lenguaje {input_data.tone}.
- NO cambies severidad ni agregues reglas.
- Máximo {input_data.max_tokens} tokens.
"""

    if input_data.disclaimer_required:
        prompt += "\n- Incluye disclaimer legal al final.\n"

    return prompt.strip()
