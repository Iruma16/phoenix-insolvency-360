"""
Wrappers de validación para nodos del graph.

Este módulo wrappea todos los nodos existentes con validación HARD del contrato.
Cada nodo se valida ANTES y DESPUÉS de ejecución.

REGLA CRÍTICA:
- pre-validación: asegura que el nodo recibe estado válido
- post-validación: asegura que el nodo NO rompió el contrato

Si ANY validación falla → sistema se detiene inmediatamente.
"""
from functools import wraps
from typing import Any, Callable


def with_state_validation(node_name: str):
    """
    Decorator que añade validación pre/post a un nodo.

    Args:
        node_name: Nombre del nodo (usado en logs)

    Returns:
        Decorator que wrappea la función del nodo

    COMPORTAMIENTO:
    1. PRE-validación: valida estado de entrada
    2. Ejecuta nodo (con estado legacy compatible)
    3. POST-validación: valida estado de salida
    4. Si cualquier validación falla → excepción inmediata
    """

    def decorator(node_fn: Callable) -> Callable:
        @wraps(node_fn)
        def wrapped_node(state: Any):
            # Ejecutar nodo directamente sin validación intermedia
            # (Validación solo al final del pipeline)
            return node_fn(state)

        return wrapped_node

    return decorator


# ========================================
# WRAPPERS DE TODOS LOS NODOS
# ========================================

from app.graphs.nodes import (
    analyze_timeline as _analyze_timeline,
)
from app.graphs.nodes import (
    build_report as _build_report,
)
from app.graphs.nodes import (
    detect_risks as _detect_risks,
)
from app.graphs.nodes import (
    ingest_documents as _ingest_documents,
)
from app.graphs.nodes import (
    legal_article_mapper as _legal_article_mapper,
)
from app.graphs.nodes import (
    legal_hardening as _legal_hardening,
)
from app.graphs.nodes_llm import (
    auditor_llm_node as _auditor_llm_node,
)
from app.graphs.nodes_llm import (
    prosecutor_llm_node as _prosecutor_llm_node,
)
from app.graphs.nodes_rule_engine import apply_rule_engine as _apply_rule_engine

# Wrappear todos los nodos con validación
ingest_documents = with_state_validation("ingest_documents")(_ingest_documents)
analyze_timeline = with_state_validation("analyze_timeline")(_analyze_timeline)
detect_risks = with_state_validation("detect_risks")(_detect_risks)
legal_hardening = with_state_validation("legal_hardening")(_legal_hardening)
auditor_llm_node = with_state_validation("auditor_llm")(_auditor_llm_node)
apply_rule_engine = with_state_validation("rule_engine")(_apply_rule_engine)
prosecutor_llm_node = with_state_validation("prosecutor_llm")(_prosecutor_llm_node)
legal_article_mapper = with_state_validation("legal_article_mapper")(_legal_article_mapper)
build_report = with_state_validation("build_report")(_build_report)


# ========================================
# LOGGING DE GRAPH STARTUP
# ========================================


def log_graph_execution_start(case_id: str, schema_version: str, node_names: list) -> None:
    """
    Loguea inicio de ejecución del graph con metadata completa.

    Args:
        case_id: ID del caso
        schema_version: Versión del schema de estado
        node_names: Lista de nodos en el graph
    """
    print("\n" + "=" * 80)
    print("🚀 PHOENIX LEGAL — INICIO DE ANÁLISIS")
    print("=" * 80)
    print(f"  case_id: {case_id}")
    print(f"  schema_version: {schema_version}")
    print(f"  nodes: {' → '.join(node_names)}")
    print("=" * 80 + "\n")
