"""
Agente Prosecutor con LLM.

Genera razonamiento legal contextualizado con el TRLC, complementando
las heurísticas con análisis LLM fundamentado en el RAG legal.
"""
import os
from typing import Any, Optional

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI


class ProsecutorLLMAgent:
    """
    Agente Prosecutor híbrido que complementa heurísticas con razonamiento LLM legal.

    NO sobrescribe resultados heurísticos.
    Genera: resumen legal, razonamiento, recomendaciones.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Inicializa el agente Prosecutor LLM.

        Args:
            api_key: OpenAI API key (opcional, toma de env si no se provee)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.enabled = bool(self.api_key)

        if self.enabled:
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.2,  # Más conservador para análisis legal
                api_key=self.api_key,
            )
        else:
            self.llm = None

    def analyze(
        self,
        case_id: str,
        risks: list[dict[str, Any]],
        legal_findings: list[dict[str, Any]],
        legal_rag_context: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Genera análisis legal LLM complementario sobre riesgos y findings.

        Args:
            case_id: ID del caso
            risks: Riesgos detectados por heurísticas
            legal_findings: Findings legales mapeados
            legal_rag_context: Contexto recuperado del RAG legal (TRLC)

        Returns:
            Dict con llm_legal_summary, llm_legal_reasoning, llm_recommendations
        """
        if not self.enabled:
            return self._disabled_response()

        try:
            # Construir contexto
            context = self._build_context(risks, legal_findings, legal_rag_context)

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
                    "risks_count": len(risks),
                    "findings_count": len(legal_findings),
                }
            )

            # Parsear respuesta
            return self._parse_response(response.content)

        except Exception as e:
            print(f"⚠️  Prosecutor LLM error: {e}")
            return self._error_response(str(e))

    def _build_context(
        self, risks: list[dict], legal_findings: list[dict], rag_context: Optional[str]
    ) -> str:
        """Construye contexto estructurado para el LLM."""

        context_parts = []

        # Riesgos detectados
        if risks:
            context_parts.append("RIESGOS IDENTIFICADOS:")
            for risk in risks:
                risk_type = risk.get("risk_type", "desconocido")
                severity = risk.get("severity", "indeterminate")
                explanation = risk.get("explanation", "Sin explicación")
                context_parts.append(f"  - {risk_type} ({severity}): {explanation[:100]}")

        # Legal findings
        if legal_findings:
            context_parts.append("\nHALLAZGOS LEGALES:")
            for finding in legal_findings:
                finding_type = finding.get("finding_type", "desconocido")
                severity = finding.get("severity", "indeterminate")
                legal_basis = finding.get("legal_basis", [])

                articles = ", ".join(
                    [
                        f"{art.get('law', 'TRLC')} Art. {art.get('article', 'N/A')}"
                        for art in legal_basis[:3]
                    ]
                )

                context_parts.append(
                    f"  - {finding_type} ({severity}): {articles if articles else 'Sin base legal'}"
                )

        # Contexto RAG legal (si existe)
        if rag_context:
            context_parts.append(f"\nCONTEXTO LEGAL RELEVANTE (TRLC):\n{rag_context[:800]}")

        return "\n".join(context_parts)

    def _get_system_prompt(self) -> str:
        """Prompt de sistema para el Prosecutor."""
        return """Eres un fiscal especializado en derecho concursal español (TRLC).

Tu tarea es COMPLEMENTAR (no reemplazar) el análisis legal heurístico con tu razonamiento profesional fundamentado en el TRLC.

Analiza:
1. La gravedad legal de los riesgos identificados
2. La fundamentación legal de los hallazgos
3. Posibles implicaciones legales (calificación, responsabilidad, etc.)
4. Recomendaciones procesales específicas

Base tu análisis SOLO en el TRLC y la información proporcionada.
NO inventes artículos ni hechos.
Sé conciso, preciso y profesional."""

    def _get_user_prompt(self) -> str:
        """Prompt de usuario para el Prosecutor."""
        return """Caso: {case_id}

{context}

Genera un análisis legal complementario que incluya:

1. RESUMEN LEGAL (2-3 líneas): Valoración general de la situación legal del caso
2. RAZONAMIENTO LEGAL (5-6 líneas): Análisis de los riesgos desde perspectiva legal, fundamentación TRLC, posibles implicaciones
3. RECOMENDACIONES (3-4 líneas): Acciones legales recomendadas, próximos pasos procesales

Formato de respuesta:
RESUMEN LEGAL:
[tu resumen]

RAZONAMIENTO LEGAL:
[tu razonamiento]

RECOMENDACIONES:
[tus recomendaciones]"""

    def _parse_response(self, content: str) -> dict[str, Any]:
        """Parsea la respuesta del LLM."""

        lines = content.strip().split("\n")

        summary = []
        reasoning = []
        recommendations = []

        current_section = None

        for line in lines:
            line = line.strip()

            if line.startswith("RESUMEN LEGAL:"):
                current_section = "summary"
                continue
            elif line.startswith("RAZONAMIENTO LEGAL:"):
                current_section = "reasoning"
                continue
            elif line.startswith("RECOMENDACIONES:"):
                current_section = "recommendations"
                continue

            if line and current_section:
                if current_section == "summary":
                    summary.append(line)
                elif current_section == "reasoning":
                    reasoning.append(line)
                elif current_section == "recommendations":
                    recommendations.append(line)

        return {
            "llm_legal_summary": " ".join(summary) if summary else "No disponible",
            "llm_legal_reasoning": " ".join(reasoning) if reasoning else "No disponible",
            "llm_recommendations": " ".join(recommendations)
            if recommendations
            else "No disponible",
            "llm_agent": "prosecutor",
            "llm_enabled": True,
        }

    def _disabled_response(self) -> dict[str, Any]:
        """Respuesta cuando el agente está deshabilitado."""
        return {
            "llm_legal_summary": None,
            "llm_legal_reasoning": None,
            "llm_recommendations": None,
            "llm_agent": "prosecutor",
            "llm_enabled": False,
        }

    def _error_response(self, error: str) -> dict[str, Any]:
        """Respuesta cuando hay un error."""
        return {
            "llm_legal_summary": f"Error: {error}",
            "llm_legal_reasoning": None,
            "llm_recommendations": None,
            "llm_agent": "prosecutor",
            "llm_enabled": True,
            "llm_error": error,
        }
