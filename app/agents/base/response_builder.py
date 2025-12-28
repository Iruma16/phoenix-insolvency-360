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
    
    Args:
        question: Pregunta a responder
        context_text: Contexto documental recuperado (texto concatenado)
        
    Returns:
        Respuesta generada por el LLM
    """
    openai_client = OpenAI()

    system_prompt = (
        "Eres un asistente legal. Responde únicamente utilizando el contexto "
        "proporcionado. No inventes hechos. "
        "Si la información es insuficiente, indícalo claramente."
    )

    completion = openai_client.chat.completions.create(
        model=RAG_LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"CONTEXTO DOCUMENTAL:\n{context_text}\n\n"
                    f"PREGUNTA:\n{question}\n\n"
                    "RESPONDE DE FORMA PRUDENTE Y FUNDAMENTADA."
                ),
            },
        ],
        temperature=RAG_TEMPERATURE,
    )

    answer = completion.choices[0].message.content.strip()
    return answer

