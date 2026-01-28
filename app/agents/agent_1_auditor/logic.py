"""
Lógica del agente auditor.
"""
import json

from openai import OpenAI

from app.core.variables import RAG_LLM_MODEL, RAG_TEMPERATURE

from .prompt import AUDITOR_PROMPT


def audit_logic(question: str, context: str) -> dict:
    """
    Lógica del auditor que procesa pregunta y contexto del RAG usando LLM.

    Args:
        question: Pregunta o consulta del usuario
        context: Contexto recuperado del RAG

    Returns:
        Dict con summary, risks y next_actions
    """
    # Si no hay contexto, indicar problema
    if not context or not context.strip():
        return {
            "summary": "No se pudo recuperar contexto suficiente para realizar la auditoría.",
            "risks": [
                "Falta de documentación disponible",
                "Información insuficiente para una auditoría concluyente",
            ],
            "next_actions": [
                "Verificar que los documentos estén correctamente ingeridos",
                "Asegurar que los embeddings estén generados",
                "Revisar la calidad de la documentación",
            ],
        }

    # Usar LLM para análisis real
    try:
        openai_client = OpenAI()

        # Construir prompt con contexto y pregunta
        user_prompt = AUDITOR_PROMPT.format(context=context, question=question)

        completion = openai_client.chat.completions.create(
            model=RAG_LLM_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            temperature=RAG_TEMPERATURE,
            response_format={"type": "json_object"},  # Forzar JSON
        )

        answer = completion.choices[0].message.content.strip()

        # Parsear respuesta JSON
        result = json.loads(answer)

        # Validar estructura esperada
        if not isinstance(result, dict):
            raise ValueError("La respuesta no es un objeto JSON")

        # Asegurar que tiene las claves requeridas
        parsed_result = {
            "summary": result.get("summary", "Análisis realizado."),
            "risks": result.get("risks", []),
            "next_actions": result.get("next_actions", []),
        }

        # Validar tipos
        if not isinstance(parsed_result["summary"], str):
            parsed_result["summary"] = str(parsed_result["summary"])
        if not isinstance(parsed_result["risks"], list):
            parsed_result["risks"] = []
        if not isinstance(parsed_result["next_actions"], list):
            parsed_result["next_actions"] = []

        # Convertir elementos de listas a strings
        parsed_result["risks"] = [str(r) for r in parsed_result["risks"]]
        parsed_result["next_actions"] = [str(a) for a in parsed_result["next_actions"]]

        return parsed_result

    except json.JSONDecodeError:
        # Si falla el parseo JSON, devolver respuesta segura
        return {
            "summary": f"Error al parsear respuesta del LLM. Contexto recuperado: {len(context)} caracteres.",
            "risks": ["Error técnico en el análisis automatizado", "Se recomienda revisión manual"],
            "next_actions": [
                "Revisar manualmente el contexto recuperado",
                "Reintentar el análisis",
            ],
        }
    except Exception as e:
        # Fallback genérico para cualquier otro error
        return {
            "summary": f"Error durante el análisis: {str(e)}. Contexto disponible: {len(context)} caracteres.",
            "risks": [
                "Error técnico en el análisis",
                "Información disponible pero no procesada correctamente",
            ],
            "next_actions": [
                "Revisar manualmente la documentación",
                "Contactar soporte técnico si el problema persiste",
            ],
        }
