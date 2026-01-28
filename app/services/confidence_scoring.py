"""
REGLA 1: Scoring de confianza explícito.

Calcula confidence_score (0-1) de forma determinista.
NO influye en retrieval, SOLO en decisión de producto.
"""

from typing import List, Dict, Any, Optional, Set
import statistics


def calculate_confidence_score(
    *,
    sources: List[Dict[str, Any]],
    ground_truth_chunk_ids: Optional[Set[str]] = None,
) -> float:
    """
    Calcula confidence_score (0-1) de forma DETERMINISTA.
    
    REGLA 1: Score basado en:
    - Número de chunks recuperados
    - Scores de similitud (distances)
    - Consistencia entre chunks (varianza de scores)
    - Intersección con Ground Truth (si existe)
    
    Args:
        sources: Lista de chunks con metadata y similarity_score
        ground_truth_chunk_ids: Set de chunk_ids esperados (opcional)
        
    Returns:
        float entre 0.0 y 1.0 (mayor = más confianza)
    """
    if not sources:
        return 0.0
    
    # --------------------------------------------------
    # Factor 1: Cantidad de chunks (más chunks = más contexto)
    # --------------------------------------------------
    num_chunks = len(sources)
    quantity_score = min(num_chunks / 5.0, 1.0)  # Normalizar a 5 chunks = 1.0
    
    # --------------------------------------------------
    # Factor 2: Calidad de similitud (menor distance = mejor)
    # --------------------------------------------------
    distances = [s["similarity_score"] for s in sources if "similarity_score" in s]
    
    if not distances:
        similarity_score = 0.5  # Neutro si no hay scores
    else:
        avg_distance = statistics.mean(distances)
        # Mapear distance a score (distance < 0.5 = excelente, > 1.5 = pobre)
        # Score = 1.0 - (distance / 2.0), capeado en [0, 1]
        similarity_score = max(0.0, min(1.0, 1.0 - (avg_distance / 2.0)))
    
    # --------------------------------------------------
    # Factor 3: Consistencia (baja varianza = más consistente)
    # --------------------------------------------------
    if len(distances) > 1:
        variance = statistics.variance(distances)
        # Varianza alta (>0.5) = inconsistente, varianza baja (<0.1) = consistente
        consistency_score = max(0.0, min(1.0, 1.0 - (variance / 0.5)))
    else:
        consistency_score = 1.0  # Un solo chunk = perfectamente consistente
    
    # --------------------------------------------------
    # Factor 4: Intersección con Ground Truth (si existe)
    # --------------------------------------------------
    if ground_truth_chunk_ids:
        retrieved_ids = {s.get("chunk_id") for s in sources if s.get("chunk_id")}
        hits = retrieved_ids & ground_truth_chunk_ids
        
        if ground_truth_chunk_ids:
            gt_recall = len(hits) / len(ground_truth_chunk_ids)
        else:
            gt_recall = 1.0
    else:
        gt_recall = None  # No disponible, no penalizar
    
    # --------------------------------------------------
    # Combinación ponderada de factores
    # --------------------------------------------------
    if gt_recall is not None:
        # Si hay GT, darle más peso
        confidence = (
            0.20 * quantity_score +
            0.30 * similarity_score +
            0.20 * consistency_score +
            0.30 * gt_recall
        )
    else:
        # Sin GT, depender más de similitud y consistencia
        confidence = (
            0.25 * quantity_score +
            0.50 * similarity_score +
            0.25 * consistency_score
        )
    
    return round(confidence, 3)


def explain_confidence_score(
    *,
    sources: List[Dict[str, Any]],
    confidence_score: float,
    ground_truth_chunk_ids: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Explica cómo se calculó el confidence_score.
    
    REGLA 5: Decisión trazable.
    CORRECCIÓN A: NO incluir narrativa en dict, solo factores numéricos/flags.
    
    Returns:
        Dict con desglose de factores (SOLO datos, NO narrativa)
    """
    if not sources:
        return {
            "confidence_score": 0.0,
            "factors": {},
        }
    
    num_chunks = len(sources)
    distances = [s["similarity_score"] for s in sources if "similarity_score" in s]
    
    factors = {
        "num_chunks": num_chunks,
        "avg_distance": round(statistics.mean(distances), 3) if distances else None,
        "consistency": "alta" if len(distances) <= 1 or statistics.variance(distances) < 0.1 else "media" if statistics.variance(distances) < 0.3 else "baja",
    }
    
    if ground_truth_chunk_ids:
        retrieved_ids = {s.get("chunk_id") for s in sources if s.get("chunk_id")}
        hits = retrieved_ids & ground_truth_chunk_ids
        factors["gt_recall"] = f"{len(hits)}/{len(ground_truth_chunk_ids)}"
    
    return {
        "confidence_score": confidence_score,
        "factors": factors,
    }


def interpret_score_for_stdout(score: float) -> str:
    """
    Interpreta el score en términos legales.
    CORRECCIÓN A: Función separada SOLO para stdout, NO para dict.
    """
    if score >= 0.8:
        return "ALTA: Evidencia sólida y consistente"
    elif score >= 0.6:
        return "MEDIA: Evidencia suficiente pero con limitaciones"
    elif score >= 0.4:
        return "BAJA: Evidencia débil o inconsistente"
    else:
        return "MUY BAJA: Evidencia insuficiente para conclusión fiable"

