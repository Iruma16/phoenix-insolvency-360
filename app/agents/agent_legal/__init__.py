"""
Agente Legal: Administrador Concursal / Abogado Concursalista.

Este agente analiza riesgos legales específicos basándose en:
- Ley Concursal española
- Jurisprudencia relevante
- Evidencias del caso
"""

from .models import Rule, Rulebook
from .rule_engine import RuleEngine
from .rule_loader import load_default_rulebook, load_rulebook
from .runner import run_legal_agent
from .schema import LegalAgentResult, LegalRisk

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
