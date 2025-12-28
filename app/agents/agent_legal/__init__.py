"""
Agente Legal: Administrador Concursal / Abogado Concursalista.

Este agente analiza riesgos legales específicos basándose en:
- Ley Concursal española
- Jurisprudencia relevante
- Evidencias del caso
"""

from .runner import run_legal_agent
from .schema import LegalAgentResult, LegalRisk
from .rule_engine import RuleEngine
from .rule_loader import load_rulebook, load_default_rulebook
from .models import Rulebook, Rule

__all__ = [
    "run_legal_agent",
    "LegalAgentResult",
    "LegalRisk",
    "RuleEngine",
    "load_rulebook",
    "load_default_rulebook",
    "Rulebook",
    "Rule",
]

