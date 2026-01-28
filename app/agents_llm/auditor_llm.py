"""
Agente Auditor con LLM.

Genera razonamiento contextualizado sobre el estado financiero y documental
del caso, complementando las heurísticas con análisis LLM.
"""
import os
from typing import Any, Optional

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI


class AuditorLLMAgent:
    """
    Agente Auditor híbrido que complementa heurísticas con razonamiento LLM.

    NO sobrescribe resultados heurísticos.
    Genera: resumen, razonamiento, confianza.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Inicializa el agente Auditor LLM.

        Args:
            api_key: OpenAI API key (opcional, toma de env si no se provee)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.enabled = bool(self.api_key)

        if self.enabled:
            self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3, api_key=self.api_key)
        else:
            self.llm = None

    def analyze(
        self,
        case_id: str,
        documents: list[dict[str, Any]],
        timeline: list[dict[str, Any]],
        risks: list[dict[str, Any]],
        case_rag_context: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Genera análisis LLM complementario sobre documentación y timeline.

        Args:
            case_id: ID del caso
            documents: Lista de documentos del caso
            timeline: Timeline de eventos
            risks: Riesgos detectados por heurísticas
            case_rag_context: Contexto recuperado del RAG de casos

        Returns:
            Dict con llm_summary, llm_reasoning, llm_confidence
        """
        if not self.enabled:
            return self._disabled_response()

        try:
            # Construir contexto
            context = self._build_context(documents, timeline, risks, case_rag_context)

            # Prompt
            prompt = ChatPromptTemplate.from_messages(
                [("system", self._get_system_prompt()), ("user", self._get_user_prompt())]
            )

            # Ejecutar
            chain = prompt | self.llm
            response = chain.invoke(
                {
                    "case_id": case_id,
                    "context": context,
                    "documents_count": len(documents),
                    "timeline_events": len(timeline),
                    "risks_detected": len(risks),
                }
            )

            # Parsear respuesta
            return self._parse_response(response.content)

        except Exception as e:
            print(f"⚠️  Auditor LLM error: {e}")
            return self._error_response(str(e))

    def _build_context(
        self,
        documents: list[dict],
        timeline: list[dict],
        risks: list[dict],
        rag_context: Optional[str],
    ) -> str:
        """Construye contexto estructurado para el LLM."""

        context_parts = []

        # Documentos
        if documents:
            context_parts.append("DOCUMENTOS DISPONIBLES:")
            for doc in documents[:10]:  # Limitar a 10
                doc_type = doc.get("doc_type", "desconocido")
                filename = doc.get("filename", doc.get("doc_id", "sin nombre"))
                context_parts.append(f"  - {doc_type}: {filename}")

        # Timeline
        if timeline:
            context_parts.append("\nEVENTOS TEMPORALES:")
            for event in timeline[:8]:  # Limitar a 8
                date = event.get("date", "N/A")
                desc = event.get("description", "Sin descripción")
                context_parts.append(f"  - {date}: {desc}")

        # Riesgos detectados (heurísticas)
        if risks:
            context_parts.append("\nRIESGOS DETECTADOS (HEURÍSTICAS):")
            for risk in risks:
                risk_type = risk.get("risk_type", "desconocido")
                severity = risk.get("severity", "indeterminate")
                context_parts.append(f"  - {risk_type}: {severity}")

        # Contexto RAG (si existe)
        if rag_context:
            context_parts.append(f"\nCONTEXTO RELEVANTE DEL CASO:\n{rag_context[:500]}")

        return "\n".join(context_parts)

    def _get_system_prompt(self) -> str:
        """Prompt de sistema para el Auditor."""
        return """Eres un auditor experto en análisis de insolvencias empresariales.

Tu tarea es COMPLEMENTAR (no reemplazar) el análisis heurístico con tu razonamiento profesional.

Analiza:
1. La completitud de la documentación
2. La coherencia temporal de los eventos
3. Señales de alerta o aspectos positivos
4. Tu nivel de confianza en el análisis

NO inventes hechos. Base tu análisis SOLO en la información proporcionada.
Sé conciso y profesional."""

    def _get_user_prompt(self) -> str:
        """Prompt de usuario para el Auditor."""
        return """Caso: {case_id}

{context}

Genera un análisis complementario que incluya:

1. RESUMEN (2-3 líneas): Estado general de la documentación y timeline
2. RAZONAMIENTO (4-5 líneas): Aspectos clave observados, coherencia, señales de alerta
3. CONFIANZA (1 línea): Tu nivel de confianza en el análisis (alta/media/baja) y por qué

Formato de respuesta:
RESUMEN:
[tu resumen]

RAZONAMIENTO:
[tu razonamiento]

CONFIANZA:
[tu nivel de confianza]"""

    def _parse_response(self, content: str) -> dict[str, Any]:
        """Parsea la respuesta del LLM."""

        lines = content.strip().split("\n")

        summary = []
        reasoning = []
        confidence = []

        current_section = None

        for line in lines:
            line = line.strip()

            if line.startswith("RESUMEN:"):
                current_section = "summary"
                continue
            elif line.startswith("RAZONAMIENTO:"):
                current_section = "reasoning"
                continue
            elif line.startswith("CONFIANZA:"):
                current_section = "confidence"
                continue

            if line and current_section:
                if current_section == "summary":
                    summary.append(line)
                elif current_section == "reasoning":
                    reasoning.append(line)
                elif current_section == "confidence":
                    confidence.append(line)

        return {
            "llm_summary": " ".join(summary) if summary else "No disponible",
            "llm_reasoning": " ".join(reasoning) if reasoning else "No disponible",
            "llm_confidence": " ".join(confidence) if confidence else "No disponible",
            "llm_agent": "auditor",
            "llm_enabled": True,
        }

    def _disabled_response(self) -> dict[str, Any]:
        """Respuesta cuando el agente está deshabilitado."""
        return {
            "llm_summary": None,
            "llm_reasoning": None,
            "llm_confidence": None,
            "llm_agent": "auditor",
            "llm_enabled": False,
        }

    def _error_response(self, error: str) -> dict[str, Any]:
        """Respuesta cuando hay un error."""
        return {
            "llm_summary": f"Error: {error}",
            "llm_reasoning": None,
            "llm_confidence": None,
            "llm_agent": "auditor",
            "llm_enabled": True,
            "llm_error": error,
        }
