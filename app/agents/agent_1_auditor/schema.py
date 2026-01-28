"""
Esquemas de datos para el agente auditor.
"""
from pydantic import BaseModel
from typing import List


class AuditorResult(BaseModel):
    summary: str
    risks: List[str]
    next_actions: List[str]

