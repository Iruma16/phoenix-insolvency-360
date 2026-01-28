"""
LLM EXECUTOR CENTRALIZADO con gestión de errores, retry y degradación.

Este módulo es el ÚNICO punto de entrada para ejecutar LLMs.

REGLAS NO NEGOCIABLES:
- PROHIBIDO llamar directamente al cliente OpenAI desde otros módulos.
- TODAS las llamadas a LLM pasan por execute_llm().
- El sistema NUNCA falla por error de LLM.
- Degradación controlada siempre activa.

PRINCIPIOS:
- FAIL SAFE, NO FAIL FAST
- Rule Engine > LLM
- Trazabilidad total
"""
import time
from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

from app.core.llm_config import is_llm_enabled, PRIMARY_MODEL, FALLBACK_MODEL
from app.services.legal_disclaimer import process_llm_output_safe


# ========================================
# RESULTADO DE EJECUCIÓN
# ========================================

class LLMExecutionResult(BaseModel):
    """
    Resultado de una ejecución de LLM.
    
    Este modelo SIEMPRE se retorna, incluso si el LLM falla.
    """
    success: bool = Field(
        ...,
        description="¿La ejecución fue exitosa?"
    )
    
    output_text: Optional[str] = Field(
        default=None,
        description="Texto generado por el LLM (None si falló)"
    )
    
    error_type: Optional[Literal[
        "disabled",
        "no_api_key",
        "timeout",
        "api_error",
        "validation_error",
        "unknown"
    ]] = Field(
        default=None,
        description="Tipo de error (si success=False)"
    )
    
    error_message: Optional[str] = Field(
        default=None,
        description="Mensaje de error detallado"
    )
    
    retries_used: int = Field(
        default=0,
        description="Número de reintentos realizados"
    )
    
    model_used: Optional[str] = Field(
        default=None,
        description="Modelo usado (primary o fallback)"
    )
    
    degraded: bool = Field(
        default=False,
        description="¿Se activó modo degradado?"
    )
    
    latency_ms: Optional[float] = Field(
        default=None,
        description="Latencia total de ejecución"
    )
    
    task_name: str = Field(
        ...,
        description="Nombre de la tarea ejecutada"
    )
    
    executed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp de ejecución"
    )
    
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True
    )


# ========================================
# EXECUTOR PRINCIPAL
# ========================================

def execute_llm(
    *,
    task_name: str,
    prompt_system: str,
    prompt_user: str,
    primary_model: Optional[str] = None,
    fallback_model: Optional[str] = None,
    max_retries: int = 2,
    timeout_seconds: int = 15,
    max_tokens: int = 500
) -> LLMExecutionResult:
    """
    Ejecuta un LLM con gestión completa de errores.
    
    Args:
        task_name: Nombre de la tarea (para logging)
        prompt_system: System prompt
        prompt_user: User prompt
        primary_model: Modelo principal (default: config global)
        fallback_model: Modelo de fallback (default: config global)
        max_retries: Máximo de reintentos
        timeout_seconds: Timeout por intento
        max_tokens: Tokens máximos a generar
    
    Returns:
        LLMExecutionResult (SIEMPRE, nunca lanza excepción)
    
    COMPORTAMIENTO:
    1. Si LLM_ENABLED=false → degraded=True inmediatamente
    2. Intenta con primary_model
    3. Si falla, reintenta hasta max_retries
    4. Si sigue fallando, intenta con fallback_model
    5. Si todo falla → degraded=True
    """
    start_time = time.time()
    
    # Usar modelos de config si no se especifican
    if primary_model is None:
        primary_model = PRIMARY_MODEL
    if fallback_model is None:
        fallback_model = FALLBACK_MODEL
    
    # ════════════════════════════════════════════════════════════════
    # CASO 1: LLM deshabilitado
    # ════════════════════════════════════════════════════════════════
    if not is_llm_enabled():
        print(f"[LLM_EXECUTOR] task={task_name} result=DEGRADED reason=disabled")
        
        return LLMExecutionResult(
            success=False,
            output_text=None,
            error_type="disabled",
            error_message="LLM is disabled via feature flag or missing API key",
            retries_used=0,
            model_used=None,
            degraded=True,
            latency_ms=(time.time() - start_time) * 1000,
            task_name=task_name
        )
    
    # ════════════════════════════════════════════════════════════════
    # CASO 2: Intentar ejecución con primary
    # ════════════════════════════════════════════════════════════════
    result = _try_execute_with_model(
        task_name=task_name,
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        model=primary_model,
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
        is_fallback=False
    )
    
    if result.success:
        result.latency_ms = (time.time() - start_time) * 1000
        return result
    
    # ════════════════════════════════════════════════════════════════
    # CASO 3: Primary falló → intentar fallback
    # ════════════════════════════════════════════════════════════════
    print(f"[LLM_EXECUTOR] task={task_name} primary_failed={primary_model} "
          f"trying_fallback={fallback_model}")
    
    result_fallback = _try_execute_with_model(
        task_name=task_name,
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        model=fallback_model,
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
        is_fallback=True
    )
    
    if result_fallback.success:
        result_fallback.latency_ms = (time.time() - start_time) * 1000
        return result_fallback
    
    # ════════════════════════════════════════════════════════════════
    # CASO 4: TODO falló → degradación
    # ════════════════════════════════════════════════════════════════
    print(f"[LLM_EXECUTOR] task={task_name} result=DEGRADED "
          f"reason=all_models_failed")
    
    return LLMExecutionResult(
        success=False,
        output_text=None,
        error_type=result.error_type or "unknown",
        error_message=f"All models failed. Primary: {result.error_message}. "
                     f"Fallback: {result_fallback.error_message}",
        retries_used=result.retries_used + result_fallback.retries_used,
        model_used=None,
        degraded=True,
        latency_ms=(time.time() - start_time) * 1000,
        task_name=task_name
    )


# ========================================
# HELPER: Intentar con un modelo
# ========================================

def _try_execute_with_model(
    *,
    task_name: str,
    prompt_system: str,
    prompt_user: str,
    model: str,
    max_retries: int,
    timeout_seconds: int,
    max_tokens: int,
    is_fallback: bool
) -> LLMExecutionResult:
    """
    Intenta ejecutar con un modelo específico (con retries).
    
    Args:
        is_fallback: Si True, este es el modelo de fallback
    
    Returns:
        LLMExecutionResult
    """
    retries_used = 0
    last_error = None
    last_error_type = "unknown"
    
    for attempt in range(max_retries + 1):
        try:
            # Intentar llamada real al LLM
            output = _call_llm_api(
                prompt_system=prompt_system,
                prompt_user=prompt_user,
                model=model,
                timeout_seconds=timeout_seconds,
                max_tokens=max_tokens
            )
            
            # Post-procesar output para seguridad legal
            output_safe = process_llm_output_safe(
                output,
                add_disclaimer=True,
                apply_language_policy=True
            )
            
            # Éxito!
            print(f"[LLM_EXECUTOR] task={task_name} model={model} "
                  f"attempt={attempt+1} result=SUCCESS")
            
            return LLMExecutionResult(
                success=True,
                output_text=output_safe,
                error_type=None,
                error_message=None,
                retries_used=retries_used,
                model_used=model,
                degraded=False,
                task_name=task_name
            )
        
        except TimeoutError as e:
            last_error = str(e)
            last_error_type = "timeout"
            retries_used = attempt
            
            print(f"[LLM_EXECUTOR] task={task_name} model={model} "
                  f"attempt={attempt+1} error=timeout")
            
            # Retry para timeout
            if attempt < max_retries:
                time.sleep(1)  # Backoff simple
                continue
        
        except Exception as e:
            last_error = str(e)
            error_name = type(e).__name__
            
            # Clasificar error
            if "api" in error_name.lower() or "openai" in error_name.lower():
                last_error_type = "api_error"
            else:
                last_error_type = "unknown"
            
            print(f"[LLM_EXECUTOR] task={task_name} model={model} "
                  f"attempt={attempt+1} error={error_name}")
            
            # Retry solo para errores transitorios (5xx)
            if "5" in str(e) or "timeout" in str(e).lower():
                retries_used = attempt
                if attempt < max_retries:
                    time.sleep(1)
                    continue
            
            # Para otros errores, no reintentar
            break
    
    # Todos los intentos fallaron
    return LLMExecutionResult(
        success=False,
        output_text=None,
        error_type=last_error_type,
        error_message=last_error,
        retries_used=retries_used,
        model_used=None,
        degraded=False,
        task_name=task_name
    )


# ========================================
# HELPER: Llamada real a API
# ========================================

def _call_llm_api(
    *,
    prompt_system: str,
    prompt_user: str,
    model: str,
    timeout_seconds: int,
    max_tokens: int
) -> str:
    """
    Llamada real a la API de OpenAI.
    
    Esta es la ÚNICA función que hace la llamada real.
    
    Returns:
        str: Texto generado por el LLM
    
    Raises:
        TimeoutError: Si excede timeout
        Exception: Otros errores de API
    """
    try:
        from openai import OpenAI
        import os
        
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=timeout_seconds
        )
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            max_tokens=max_tokens,
            temperature=0.3  # Bajo para legal
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        # Re-raise para que _try_execute_with_model maneje
        raise


# ========================================
# HELPER: Degradación controlada
# ========================================

def generate_degraded_explanation(
    *,
    task_name: str,
    rule_engine_result,
    reason: str
) -> str:
    """
    Genera explicación automática sin LLM.
    
    Args:
        task_name: Nombre de la tarea
        rule_engine_result: RuleEngineResult con decisiones
        reason: Razón de la degradación
    
    Returns:
        str: Explicación generada sin LLM (CON disclaimer)
    """
    from app.legal.rule_engine_output import RuleEngineResult
    from app.services.legal_disclaimer import get_disclaimer
    
    # Header de degradación
    explanation = f"""
{get_disclaimer('degraded')}

Razón: {reason}

════════════════════════════════════════════════════════════════════════════════
REGLAS APLICADAS
════════════════════════════════════════════════════════════════════════════════
""".strip()
    
    # Si hay RuleEngineResult, extraer decisiones
    if isinstance(rule_engine_result, RuleEngineResult):
        if rule_engine_result.triggered_rules:
            explanation += "\n\n"
            for rule in rule_engine_result.triggered_rules:
                explanation += f"""
• {rule.rule_name}
  Artículo: {rule.article}
  Severidad: {rule.severity.upper()}
  Confianza: {rule.confidence}
  Razón: {rule.rationale}
""".strip()
                explanation += "\n\n"
        else:
            explanation += "\n\nNinguna regla aplicó al caso analizado.\n"
        
        # Summary flags
        if rule_engine_result.summary_flags:
            explanation += "\n" + "="*80 + "\n"
            explanation += "INDICADORES\n"
            explanation += "="*80 + "\n"
            for flag, value in rule_engine_result.summary_flags.items():
                status = "SÍ" if value else "NO"
                flag_readable = flag.replace("_", " ").title()
                explanation += f"• {flag_readable}: {status}\n"
    
    # Disclaimer técnico completo
    from app.services.legal_disclaimer import get_disclaimer
    explanation += "\n\n" + "="*80 + "\n"
    explanation += get_disclaimer('technical')
    
    return explanation

