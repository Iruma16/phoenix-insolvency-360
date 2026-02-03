"""
Esquemas de datos para el agente auditor.
"""

from pydantic import BaseModel


class AuditorResult(BaseModel):
    summary: str
    risks: list[str]
    next_actions: list[str]
