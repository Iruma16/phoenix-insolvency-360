"""
Test para verificar que el Agente Legal no alucina artículos legales.
"""

import unittest
from unittest.mock import MagicMock, patch

from app.agents.agent_legal.logic import (
    _extract_allowed_articles,
    _filter_legal_articles,
    _normalize_article_reference,
    legal_agent_logic,
)


class TestAgentLegalHallucination(unittest.TestCase):
    """Test para verificar blindaje contra alucinaciones de artículos legales."""

    def test_extract_allowed_articles(self):
        """Verifica que se extraen correctamente los artículos del contexto legal."""
        legal_context = """
        Art. 165 LC: Texto del artículo 165
        Artículo 166 de la Ley Concursal
        Art 167 LC
        Art.168
        """
        allowed = _extract_allowed_articles(legal_context)
        self.assertIn("165", allowed)
        self.assertIn("166", allowed)
        self.assertIn("167", allowed)
        self.assertIn("168", allowed)

    def test_extract_allowed_articles_empty(self):
        """Verifica que retorna set vacío con contexto vacío."""
        allowed = _extract_allowed_articles("")
        self.assertEqual(allowed, set())
        allowed = _extract_allowed_articles(None)
        self.assertEqual(allowed, set())

    def test_normalize_article_reference(self):
        """Verifica normalización de referencias de artículos."""
        self.assertEqual(_normalize_article_reference("Art. 165 LC"), "165")
        self.assertEqual(_normalize_article_reference("Artículo 166"), "166")
        self.assertEqual(_normalize_article_reference("Art 167"), "167")
        self.assertEqual(_normalize_article_reference("165"), "165")
        self.assertIsNone(_normalize_article_reference(""))
        self.assertIsNone(_normalize_article_reference("Texto sin artículo"))

    def test_filter_legal_articles(self):
        """Verifica que se filtran correctamente los artículos."""
        allowed = {"165", "166"}
        legal_articles = ["Art. 165 LC", "Art. 167 LC", "Artículo 166"]

        valid, discarded = _filter_legal_articles(legal_articles, allowed, "")

        self.assertEqual(set(valid), {"Art. 165 LC", "Artículo 166"})
        self.assertEqual(set(discarded), {"Art. 167 LC"})

    @patch("app.agents.agent_legal.logic.OpenAI")
    def test_hallucination_filtering(self, mock_openai_class):
        """Test principal: verifica que se filtran artículos alucinados."""
        # Configurar mock del LLM
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Simular respuesta del LLM con artículo alucinado
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """{
            "legal_risks": [
                {
                    "risk_type": "calificacion_culpable",
                    "description": "Riesgo de calificación culpable",
                    "severity": "alta",
                    "legal_articles": ["Art. 165 LC", "Art. 999 LC"],
                    "jurisprudence": [],
                    "evidence_status": "suficiente",
                    "recommendation": "Revisar documentación"
                }
            ],
            "legal_conclusion": "Conclusión legal",
            "confidence_level": "alta",
            "missing_data": [],
            "legal_basis": ["Art. 165 LC", "Art. 999 LC"]
        }"""
        mock_client.chat.completions.create.return_value = mock_response

        # Contexto legal que solo contiene Art. 165
        legal_context = """
        Art. 165 LC: El deudor puede ser calificado como culpable si...
        """

        # Ejecutar lógica
        result = legal_agent_logic(
            question="¿Existen riesgos de calificación culpable?",
            legal_context=legal_context,
        )

        # Verificaciones
        self.assertIsNotNone(result)
        self.assertEqual(result["confidence_level"], "indeterminado")

        # Verificar que el artículo válido (165) está presente
        risk = result["legal_risks"][0]
        self.assertIn("Art. 165 LC", risk["legal_articles"])

        # Verificar que el artículo alucinado (999) fue eliminado
        self.assertNotIn("Art. 999 LC", risk["legal_articles"])
        self.assertNotIn("Art. 999 LC", result["legal_basis"])

        # Verificar que missing_data contiene aviso
        missing_data_str = " ".join(result["missing_data"])
        self.assertIn("Art. 999", missing_data_str)
        self.assertIn("no presentes en el contexto legal", missing_data_str.lower())

        # Verificar que evidence_status se ajustó
        self.assertIn(risk["evidence_status"], ["insuficiente", "falta"])

    @patch("app.agents.agent_legal.logic.OpenAI")
    def test_empty_legal_context_forces_indeterminado(self, mock_openai_class):
        """Verifica que contexto legal vacío fuerza confidence_level a indeterminado."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """{
            "legal_risks": [],
            "legal_conclusion": "Conclusión",
            "confidence_level": "alta",
            "missing_data": [],
            "legal_basis": []
        }"""
        mock_client.chat.completions.create.return_value = mock_response

        # Contexto legal vacío
        result = legal_agent_logic(
            question="Pregunta legal",
            legal_context="",
        )

        self.assertEqual(result["confidence_level"], "indeterminado")
        missing_data_str = " ".join(result["missing_data"]).lower()
        self.assertIn("base legal insuficiente", missing_data_str)

    @patch("app.agents.agent_legal.logic.OpenAI")
    def test_all_valid_articles_preserved(self, mock_openai_class):
        """Verifica que artículos válidos se preservan correctamente."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """{
            "legal_risks": [
                {
                    "risk_type": "omision",
                    "description": "Riesgo",
                    "severity": "media",
                    "legal_articles": ["Art. 165 LC", "Artículo 166"],
                    "jurisprudence": [],
                    "evidence_status": "suficiente",
                    "recommendation": "Revisar"
                }
            ],
            "legal_conclusion": "Conclusión",
            "confidence_level": "alta",
            "missing_data": [],
            "legal_basis": ["Art. 165 LC", "Artículo 166"]
        }"""
        mock_client.chat.completions.create.return_value = mock_response

        # Contexto legal con ambos artículos
        legal_context = """
        Art. 165 LC: Texto del artículo 165
        Artículo 166: Texto del artículo 166
        """

        result = legal_agent_logic(
            question="Pregunta legal",
            legal_context=legal_context,
        )

        # Si todos los artículos son válidos y hay contexto, no debe forzar indeterminado
        # (a menos que el LLM ya lo haya marcado)
        risk = result["legal_risks"][0]
        self.assertIn("Art. 165 LC", risk["legal_articles"])
        self.assertIn("Artículo 166", risk["legal_articles"])
        self.assertEqual(len(risk["legal_articles"]), 2)


if __name__ == "__main__":
    unittest.main()
