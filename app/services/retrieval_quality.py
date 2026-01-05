"""
Medición objetiva de calidad del retrieval (recall@k).

REGLA 5: Medición REAL de recall@k con ground truth explícito.
"""

from typing import List, Dict, Any, Set
from dataclasses import dataclass
from pathlib import Path
import json

from sqlalchemy.orm import Session
from openai import OpenAI

from app.services.embeddings_pipeline import get_case_collection
from app.core.variables import EMBEDDING_MODEL, DATA
from app.core.logger import logger


@dataclass
class GroundTruthQuery:
    """
    Pregunta con ground truth explícito.
    
    REGLA 5: Chunks esperados por pregunta.
    """
    query: str
    expected_chunk_ids: Set[str]  # IDs de chunks que DEBERÍAN recuperarse
    description: str


# REGLA 5: Conjunto mínimo de preguntas típicas de concurso de acreedores
# NOTA: Este es el conjunto BASE. Para casos reales, se debe crear ground truth
# específico por case_id con chunk_ids reales.

GROUND_TRUTH_QUERIES_TEMPLATE = [
    GroundTruthQuery(
        query="¿Cuál es el importe total de la deuda reconocida en el concurso?",
        expected_chunk_ids=set(),  # Configurar por caso
        description="Deuda total concursal",
    ),
    GroundTruthQuery(
        query="¿Quiénes son los acreedores privilegiados y cuál es su crédito?",
        expected_chunk_ids=set(),
        description="Acreedores privilegiados",
    ),
    GroundTruthQuery(
        query="¿Cuál es la fecha de solicitud del concurso de acreedores?",
        expected_chunk_ids=set(),
        description="Fecha solicitud concurso",
    ),
    GroundTruthQuery(
        query="¿Qué bienes y derechos integran la masa activa del concurso?",
        expected_chunk_ids=set(),
        description="Masa activa",
    ),
    GroundTruthQuery(
        query="¿Se ha declarado la insolvencia como fortuita o culpable?",
        expected_chunk_ids=set(),
        description="Calificación concurso",
    ),
]


def create_ground_truth_for_case(
    case_id: str,
    ground_truth_mapping: dict[str, set[str]],
) -> List[GroundTruthQuery]:
    """
    Crea ground truth específico para un caso.
    
    CORRECCIÓN: Ground truth DEBE ser explícito por caso.
    
    Args:
        case_id: ID del caso
        ground_truth_mapping: Dict de {descripción: set de chunk_ids esperados}
        
    Ejemplo:
        ground_truth = create_ground_truth_for_case(
            "case_001",
            {
                "Deuda total concursal": {"chunk_abc123", "chunk_def456"},
                "Acreedores privilegiados": {"chunk_xyz789"},
            }
        )
    """
    queries = []
    for template in GROUND_TRUTH_QUERIES_TEMPLATE:
        expected_ids = ground_truth_mapping.get(template.description, set())
        queries.append(
            GroundTruthQuery(
                query=template.query,
                expected_chunk_ids=expected_ids,
                description=template.description,
            )
        )
    return queries


# =========================================================
# REGLA 1: SOPORTE OPERACIONAL DE GROUND TRUTH POR CASE_ID
# =========================================================

def get_ground_truth_path(case_id: str) -> Path:
    """Obtiene ruta del archivo de ground truth para un caso."""
    case_dir = DATA / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir / "ground_truth.json"


def save_ground_truth_for_case(
    case_id: str,
    ground_truth_mapping: Dict[str, Set[str]],
) -> None:
    """
    Guarda ground truth específico para un caso en disco.
    
    REGLA 1: Ground Truth REAL por case_id (operacional).
    
    Args:
        case_id: ID del caso
        ground_truth_mapping: Dict de {descripción: set de chunk_ids esperados}
        
    Ejemplo:
        save_ground_truth_for_case(
            "case_001",
            {
                "Deuda total concursal": {"chunk_abc123", "chunk_def456"},
                "Acreedores privilegiados": {"chunk_xyz789"},
            }
        )
    """
    gt_path = get_ground_truth_path(case_id)
    
    # Convertir sets a listas para JSON
    serializable_mapping = {
        desc: list(chunk_ids) 
        for desc, chunk_ids in ground_truth_mapping.items()
    }
    
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(serializable_mapping, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Ground truth guardado para case_id={case_id}: {gt_path}")
    print(f"[GT] ✅ Ground truth guardado: {gt_path}")


def load_ground_truth_for_case(case_id: str) -> List[GroundTruthQuery]:
    """
    Carga ground truth específico de un caso desde disco.
    
    REGLA 1: Ground Truth REAL por case_id (operacional).
    
    Args:
        case_id: ID del caso
        
    Returns:
        Lista de GroundTruthQuery con chunk_ids esperados por pregunta.
        Si no existe GT para el caso, retorna template vacío.
        
    Ejemplo:
        queries = load_ground_truth_for_case("case_001")
        metrics = calculate_recall_at_k(db, "case_001", queries, k=5)
    """
    gt_path = get_ground_truth_path(case_id)
    
    if not gt_path.exists():
        logger.warning(
            f"No existe ground truth para case_id={case_id}. "
            f"Usando template vacío. Crear GT con save_ground_truth_for_case()."
        )
        print(f"[GT] ⚠️ No existe ground truth para {case_id}")
        return create_ground_truth_for_case(case_id, {})
    
    try:
        with open(gt_path, "r", encoding="utf-8") as f:
            ground_truth_mapping = json.load(f)
        
        # Convertir listas a sets
        ground_truth_mapping = {
            desc: set(chunk_ids)
            for desc, chunk_ids in ground_truth_mapping.items()
        }
        
        logger.info(f"Ground truth cargado para case_id={case_id}: {gt_path}")
        print(f"[GT] ✅ Ground truth cargado: {gt_path}")
        
        return create_ground_truth_for_case(case_id, ground_truth_mapping)
    
    except Exception as e:
        logger.error(f"Error cargando ground truth para {case_id}: {e}")
        print(f"[GT] ❌ Error cargando ground truth: {e}")
        return create_ground_truth_for_case(case_id, {})


@dataclass
class RecallMetrics:
    """
    Métricas de recall@k para una pregunta.
    """
    query: str
    description: str
    k: int
    expected_count: int
    retrieved_count: int
    hits: int
    recall: float
    retrieved_chunk_ids: List[str]
    expected_chunk_ids: List[str]
    

def calculate_recall_at_k(
    db: Session,
    case_id: str,
    ground_truth_queries: List[GroundTruthQuery],
    k: int = 5,
) -> Dict[str, Any]:
    """
    Calcula recall@k para un conjunto de preguntas con ground truth.
    
    REGLA 5: Medición REAL de recall@k.
    
    recall@k = (chunks esperados recuperados en top-k) / (total chunks esperados)
    
    Args:
        db: Sesión de BD
        case_id: ID del caso
        ground_truth_queries: Lista de preguntas con chunks esperados
        k: Número de chunks a recuperar (default=5)
        
    Returns:
        Dict con métricas agregadas y por pregunta
    """
    logger.info(f"[RECALL@K] Iniciando medición para case_id={case_id}, k={k}")
    
    # Inicializar cliente OpenAI
    openai_client = OpenAI()
    
    # Obtener colección del vectorstore
    try:
        collection = get_case_collection(case_id, version=None)
    except Exception as e:
        logger.error(f"[RECALL@K] Error obteniendo colección: {e}")
        return {
            "error": str(e),
            "case_id": case_id,
            "k": k,
        }
    
    results: List[RecallMetrics] = []
    total_recall = 0.0
    queries_with_ground_truth = 0
    
    for gt_query in ground_truth_queries:
        # Saltar si no hay ground truth configurado
        if not gt_query.expected_chunk_ids:
            logger.warning(
                f"[RECALL@K] Saltando query sin ground truth: {gt_query.description}"
            )
            continue
        
        queries_with_ground_truth += 1
        
        # Generar embedding de la pregunta
        question_embedding = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[gt_query.query],
        ).data[0].embedding
        
        # Buscar top-k chunks
        search_results = collection.query(
            query_embeddings=[question_embedding],
            n_results=k,
            include=["metadatas"],
        )
        
        # Extraer IDs de chunks recuperados
        retrieved_ids = []
        if search_results and "ids" in search_results:
            retrieved_ids = search_results["ids"][0] if search_results["ids"] else []
        
        retrieved_set = set(retrieved_ids)
        expected_set = gt_query.expected_chunk_ids
        
        # Calcular hits (intersección)
        hits = len(retrieved_set & expected_set)
        
        # Calcular recall@k
        recall = hits / len(expected_set) if len(expected_set) > 0 else 0.0
        
        total_recall += recall
        
        result = RecallMetrics(
            query=gt_query.query,
            description=gt_query.description,
            k=k,
            expected_count=len(expected_set),
            retrieved_count=len(retrieved_set),
            hits=hits,
            recall=recall,
            retrieved_chunk_ids=list(retrieved_ids),
            expected_chunk_ids=list(expected_set),
        )
        
        results.append(result)
        
        logger.info(
            f"[RECALL@K] Query: {gt_query.description}, "
            f"Recall@{k}: {recall:.2%}, "
            f"Hits: {hits}/{len(expected_set)}"
        )
    
    # Calcular recall@k agregado
    avg_recall = total_recall / queries_with_ground_truth if queries_with_ground_truth > 0 else 0.0
    
    return {
        "case_id": case_id,
        "k": k,
        "queries_evaluated": queries_with_ground_truth,
        "avg_recall_at_k": avg_recall,
        "results_by_query": results,
    }


def print_recall_metrics(metrics: Dict[str, Any]) -> None:
    """
    Muestra métricas de recall@k por pantalla (stdout).
    
    REGLA 5: El resultado DEBE mostrarse por pantalla.
    """
    print("\n" + "=" * 80)
    print("MÉTRICAS DE CALIDAD DEL RETRIEVAL (RECALL@K)")
    print("=" * 80)
    
    if "error" in metrics:
        print(f"❌ ERROR: {metrics['error']}")
        return
    
    print(f"\nCase ID: {metrics['case_id']}")
    print(f"k (top chunks): {metrics['k']}")
    print(f"Queries evaluadas: {metrics['queries_evaluated']}")
    print(f"\n📊 RECALL@{metrics['k']} AGREGADO: {metrics['avg_recall_at_k']:.2%}")
    
    print("\n" + "-" * 80)
    print("RESULTADOS POR PREGUNTA:")
    print("-" * 80)
    
    for result in metrics['results_by_query']:
        print(f"\n📋 {result.description}")
        print(f"   Query: {result.query[:80]}...")
        print(f"   Recall@{result.k}: {result.recall:.2%}")
        print(f"   Hits: {result.hits}/{result.expected_count}")
        print(f"   Chunks recuperados: {result.retrieved_count}")
        
        if result.recall < 0.5:
            print(f"   ⚠️  BAJA CALIDAD: Recall < 50%")
        elif result.recall < 0.8:
            print(f"   ⚠️  CALIDAD MEDIA: Recall < 80%")
        else:
            print(f"   ✅ BUENA CALIDAD: Recall >= 80%")
    
    print("\n" + "=" * 80)
    
    # Resumen de calidad
    if metrics['avg_recall_at_k'] < 0.5:
        print("❌ CALIDAD GENERAL: BAJA - Sistema recupera < 50% de chunks esperados")
        print("   Acción requerida: Revisar estrategia de chunking y embeddings")
    elif metrics['avg_recall_at_k'] < 0.8:
        print("⚠️  CALIDAD GENERAL: MEDIA - Sistema recupera < 80% de chunks esperados")
        print("   Acción sugerida: Optimizar parámetros de chunking")
    else:
        print("✅ CALIDAD GENERAL: BUENA - Sistema recupera >= 80% de chunks esperados")
    
    print("=" * 80 + "\n")

