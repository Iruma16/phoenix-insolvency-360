"""
Generación de respuestas con LLM a partir de contexto recuperado.
"""

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
    openai_client = OpenAI()

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

    completion = openai_client.chat.completions.create(
        model=RAG_LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=RAG_TEMPERATURE,
    )

    answer = completion.choices[0].message.content.strip()
    return answer
