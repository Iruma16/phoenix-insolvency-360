"""
Generación de respuestas con LLM a partir de contexto recuperado.
"""
import os

from openai import OpenAI

from app.core.variables import RAG_LLM_MODEL, RAG_TEMPERATURE


def build_llm_answer(
    *,
    question: str,
    context_text: str,
) -> str:
    """
    Genera una respuesta usando LLM a partir de una pregunta y contexto recuperado.

    REGLA 5: Prohibición explícita de relleno, inferencia o completado sin evidencia.

    Args:
        question: Pregunta a responder
        context_text: Contexto documental recuperado (texto concatenado)

    Returns:
        Respuesta generada por el LLM
    """
    # region agent log (debug-mode)
    def _dbg_log_llm(hypothesis_id: str, message: str, data: dict) -> None:
        try:
            _path = "/Users/irumabragado/Documents/procesos/202512_phoenix-legal/.cursor/debug.log"
            payload = {
                "sessionId": "debug-session",
                "runId": "rag-env-debug-v1",
                "hypothesisId": hypothesis_id,
                "location": "app/agents/base/response_builder.py:build_llm_answer",
                "message": message,
                "data": data,
                "timestamp": int(__import__("time").time() * 1000),
            }
            with open(_path, "a", encoding="utf-8") as f:
                f.write(__import__("json").dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # endregion agent log (debug-mode)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        _dbg_log_llm("H1", "llm_missing_openai_env", {"has_key": False})
        raise RuntimeError("LLM_DISABLED: OPENAI_API_KEY no configurada")

    openai_client = OpenAI(api_key=api_key)

    # REGLA 5: Prompt ENDURECIDO - Prohibición explícita de relleno
    system_prompt = (
        "Eres un asistente legal especializado en análisis documental.\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "1. Responde EXCLUSIVAMENTE basándote en el contexto documental proporcionado.\n"
        "2. PROHIBIDO inferir, deducir, completar o inventar información que NO esté explícitamente en los documentos.\n"
        "3. PROHIBIDO usar conocimiento general o razonamiento externo al contexto.\n"
        "4. Si la información NO está explícitamente en los fragmentos proporcionados, "
        "responde EXACTAMENTE: 'No hay evidencia suficiente en los documentos aportados.'\n"
        "5. Toda afirmación DEBE ser verificable en el contexto proporcionado.\n"
        "6. En un contexto legal, responder sin evidencia es INACEPTABLE.\n\n"
        "Prefiere siempre reconocer la ausencia de información antes que completar o inferir."
    )

    user_prompt = (
        f"CONTEXTO DOCUMENTAL (ÚNICA FUENTE VÁLIDA):\n"
        f"{context_text}\n\n"
        f"---\n\n"
        f"PREGUNTA:\n{question}\n\n"
        f"---\n\n"
        f"INSTRUCCIONES:\n"
        f"- Analiza el contexto proporcionado.\n"
        f"- Si encuentras la información explícitamente, responde de forma precisa y fundamentada.\n"
        f"- Si la información NO está en el contexto, responde: 'No hay evidencia suficiente en los documentos aportados.'\n"
        f"- NO completes, NO inferas, NO razones más allá del texto proporcionado."
    )

    try:
        completion = openai_client.chat.completions.create(
            model=RAG_LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=RAG_TEMPERATURE,
        )
    except Exception as e:
        _dbg_log_llm("H2", "llm_provider_error", {"error_type": type(e).__name__})
        raise RuntimeError(f"LLM_ERROR: {type(e).__name__}") from e

    answer = completion.choices[0].message.content.strip()
    return answer
