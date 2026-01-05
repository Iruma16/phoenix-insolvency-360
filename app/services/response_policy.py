"""
REGLA 2: Políticas finas de no respuesta.

Define políticas configurables de producto para decidir cuándo responder.
"""

from typing import Literal
from dataclasses import dataclass


PolicyMode = Literal["conservadora", "estandar", "exploratoria"]


@dataclass
class ResponsePolicy:
    """
    Política de no respuesta.
    
    REGLA 2: Combina umbrales de nº chunks y confidence_score.
    """
    name: PolicyMode
    min_chunks: int
    min_confidence_score: float
    description: str


# =========================================================
# POLÍTICAS PREDEFINIDAS
# =========================================================

POLICIES = {
    "conservadora": ResponsePolicy(
        name="conservadora",
        min_chunks=3,
        min_confidence_score=0.70,
        description="Política conservadora: solo responde con evidencia sólida y múltiples fuentes",
    ),
    "estandar": ResponsePolicy(
        name="estandar",
        min_chunks=2,
        min_confidence_score=0.60,
        description="Política estándar: equilibrio entre prudencia y utilidad",
    ),
    "exploratoria": ResponsePolicy(
        name="exploratoria",
        min_chunks=1,
        min_confidence_score=0.45,
        description="Política exploratoria: permite respuestas con evidencia limitada (advertencias obligatorias)",
    ),
}


def get_policy(mode: PolicyMode) -> ResponsePolicy:
    """Obtiene política por nombre."""
    return POLICIES[mode]


def evaluate_policy(
    *,
    policy: ResponsePolicy,
    num_chunks: int,
    confidence_score: float,
) -> tuple[bool, str]:
    """
    Evalúa si la respuesta cumple la política activa.
    
    REGLA 2: Decisión BLOQUEANTE si no cumple.
    
    Args:
        policy: Política activa
        num_chunks: Número de chunks recuperados
        confidence_score: Score de confianza (0-1)
        
    Returns:
        (cumple: bool, motivo: str)
    """
    if num_chunks < policy.min_chunks:
        return False, f"Insuficientes fuentes ({num_chunks} < {policy.min_chunks} requerido)"
    
    if confidence_score < policy.min_confidence_score:
        return False, f"Confianza insuficiente ({confidence_score:.2f} < {policy.min_confidence_score:.2f} requerido)"
    
    return True, "Política cumplida"


def print_policy_decision(
    *,
    policy: ResponsePolicy,
    num_chunks: int,
    confidence_score: float,
    cumple: bool,
    motivo: str,
) -> None:
    """
    REGLA 5: Decisión trazable por stdout.
    """
    print(f"\n{'='*80}")
    print(f"[POLÍTICA] Política activa: {policy.name.upper()}")
    print(f"[POLÍTICA] {policy.description}")
    print(f"[POLÍTICA] Umbrales:")
    print(f"  - Min chunks: {policy.min_chunks}")
    print(f"  - Min confidence: {policy.min_confidence_score:.2f}")
    print(f"[POLÍTICA] Valores actuales:")
    print(f"  - Chunks recuperados: {num_chunks}")
    print(f"  - Confidence score: {confidence_score:.3f}")
    print(f"[POLÍTICA] Evaluación: {'✅ CUMPLE' if cumple else '❌ NO CUMPLE'}")
    print(f"[POLÍTICA] Motivo: {motivo}")
    print(f"{'='*80}\n")

