"""
Agentes LLM para Phoenix Legal.

Agentes híbridos que complementan (no reemplazan) la lógica heurística
con razonamiento LLM contextualizado mediante RAG.
"""
from app.agents_llm.auditor_llm import AuditorLLMAgent
from app.agents_llm.prosecutor_llm import ProsecutorLLMAgent

__all__ = ["AuditorLLMAgent", "ProsecutorLLMAgent"]
