from datetime import datetime, timezone
from typing import Optional


async def generate_executive_summary_with_gpt(
    findings: list[dict],
    risks: list[dict],
    case_name: str,
    case_id: str,
    budget_ledger=None,
    trace_id: Optional[str] = None,
) -> str:
    """
    Genera resumen ejecutivo profesional usando GPT-4.

    CRÍTICO: Integración obligatoria con FinOps de Phoenix:
    - Budget check ANTES de llamar API
    - Registro de coste DESPUÉS de llamada
    - Trace ID para auditoría
    - Pricing version tracking

    Args:
        findings: Lista de hallazgos legales
        risks: Lista de riesgos identificados
        case_name: Nombre del caso
        case_id: ID del caso (para budget tracking)
        budget_ledger: BudgetLedger de Phoenix (opcional)
        trace_id: ID de trace para auditoría (opcional)

    Returns:
        str: Resumen ejecutivo generado o mensaje de error
    """
    try:
        from openai import AsyncOpenAI

        from app.core.finops.budget import BudgetEntry
        from app.core.finops.pricing import PRICING_VERSION, get_pricing, pricing_fingerprint
        from app.core.llm_config import get_llm_config
        from app.core.telemetry import get_tracer

        config = get_llm_config()
        client = AsyncOpenAI(api_key=config.openai_api_key)

        # CRÍTICO: Setup de FinOps
        if budget_ledger is None:
            from app.core.finops.gates import get_global_ledger

            budget_ledger = get_global_ledger()

        if not budget_ledger.has_budget(case_id):
            budget_ledger.initialize_budget(case_id)

        # CRÍTICO: Estimación de coste y budget check
        estimated_tokens = 500  # Prompt + respuesta estimados
        pricing = get_pricing("openai", "gpt-4")
        estimated_cost = (estimated_tokens / 1000) * pricing["per_1k_tokens"]

        budget = budget_ledger.get_budget(case_id)
        if not budget.can_spend(estimated_cost):
            print(
                f"[BUDGET] GPT-4 summary denied: presupuesto insuficiente (quedan ${budget.remaining_usd:.4f})"
            )
            return "[Resumen GPT-4 no disponible: presupuesto excedido]"

        # Telemetría
        tracer = get_tracer()
        with tracer.start_as_current_span("gpt4_executive_summary") as span:
            span.set_attribute("case_id", case_id)
            span.set_attribute("estimated_tokens", estimated_tokens)
            span.set_attribute("estimated_cost_usd", estimated_cost)

            # Preparar contexto
            high_risks = [r for r in risks if r.get("severity") == "high"]
            medium_risks = [r for r in risks if r.get("severity") == "medium"]

            context = f"""
Caso: {case_name}

Hallazgos totales: {len(findings)}
Riesgos identificados:
- Alto: {len(high_risks)}
- Medio: {len(medium_risks)}
- Bajo: {len(risks) - len(high_risks) - len(medium_risks)}

Principales riesgos de alta severidad:
{chr(10).join([f"- {r.get('type', 'N/A')}: {r.get('description', 'Sin descripción')[:100]}" for r in high_risks[:3]])}

Principales hallazgos legales:
{chr(10).join([f"- {f.get('type', 'N/A')}: {f.get('description', 'Sin descripción')[:100]}" for f in findings[:3]])}
"""

            prompt = f"""Eres un abogado experto en derecho concursal español. Genera un resumen ejecutivo profesional para el siguiente caso.

{context}

REQUISITOS:
- Máximo 300 palabras
- Tono formal y objetivo
- Enfócate en los riesgos más críticos
- Indica claramente la gravedad de la situación
- Menciona las implicaciones legales principales
- NO uses bullets, escribe en párrafos corridos
- NO incluyas recomendaciones de acción (solo análisis)

Redacta el resumen ejecutivo:"""

            # Llamada a OpenAI
            try:
                response = await client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {
                            "role": "system",
                            "content": "Eres un abogado experto en derecho concursal español.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=500,
                )

                # CRÍTICO: Registrar coste real
                usage = response.usage
                actual_cost = (usage.prompt_tokens / 1000) * pricing["per_1k_tokens"] + (
                    usage.completion_tokens / 1000
                ) * pricing.get("per_1k_tokens_output", pricing["per_1k_tokens"])

                entry = BudgetEntry(
                    case_id=case_id,
                    phase="report_generation",
                    provider="openai",
                    model="gpt-4",
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                    cost_usd=actual_cost,
                    trace_id=trace_id,
                    pricing_version=PRICING_VERSION,
                    pricing_fingerprint=pricing_fingerprint(),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )

                budget_ledger.record(entry)

                # Telemetría
                span.set_attribute("actual_tokens_input", usage.prompt_tokens)
                span.set_attribute("actual_tokens_output", usage.completion_tokens)
                span.set_attribute("actual_cost_usd", actual_cost)
                span.set_attribute("budget_remaining_usd", budget.remaining_usd)

                summary = response.choices[0].message.content.strip()
                return summary

            except Exception as e:
                span.record_exception(e)
                span.set_attribute("error", str(e))
                raise

    except ImportError as e:
        print(f"[ERROR] Dependencia no disponible: {e}")
        return "[Resumen GPT-4 no disponible: dependencia no instalada]"
    except Exception as e:
        print(f"[ERROR] Error generando resumen con GPT-4: {e}")
        return f"[Error generando resumen automático: {str(e)}]"
