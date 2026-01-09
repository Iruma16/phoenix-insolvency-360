"""
Wrappers de validación para nodos del graph.

Este módulo wrappea todos los nodos existentes con validación HARD del contrato.
Cada nodo se valida ANTES y DESPUÉS de ejecución.

REGLA CRÍTICA:
- pre-validación: asegura que el nodo recibe estado válido
- post-validación: asegura que el nodo NO rompió el contrato

Si ANY validación falla → sistema se detiene inmediatamente.
"""
from typing import Callable, Any, Dict
from functools import wraps

from app.graphs.state_schema import PhoenixState
from app.graphs.state_validation import (
    validate_state,
    migrate_legacy_state_to_schema,
    extract_legacy_state_from_schema,
    log_state_snapshot
)


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
        def wrapped_node(state: Any) -> PhoenixState:
            # ════════════════════════════════════════════════════════
            # PRE-VALIDACIÓN
            # ════════════════════════════════════════════════════════
            stage_pre = f"pre:{node_name}"
            
            try:
                # Detectar tipo de estado
                if isinstance(state, PhoenixState):
                    # Ya es PhoenixState → validar directamente
                    validated_input = validate_state(state, stage=stage_pre)
                
                elif isinstance(state, dict):
                    # Es dict → detectar si es legacy o ya migrado
                    # Legacy tiene campos planos: documents, timeline (lista), risks (lista)
                    # Migrado tiene estructura anidada: inputs.documents, timeline.events
                    
                    is_legacy = (
                        "documents" in state and "inputs" not in state
                    ) or (
                        "timeline" in state and isinstance(state.get("timeline"), list)
                    )
                    
                    if is_legacy:
                        # Migrar estructura legacy a PhoenixState
                        state = migrate_legacy_state_to_schema(state)
                    
                    # Validar estado (migrado o ya estructurado)
                    validated_input = validate_state(state, stage=stage_pre)
                
                else:
                    raise ValueError(
                        f"Estado debe ser PhoenixState o dict, recibido {type(state).__name__}"
                    )
                
                # Log snapshot
                log_state_snapshot(validated_input, stage_pre)
                
            except ValueError as e:
                # Validación pre falló → HARD FAIL
                print(f"\n❌ PRE-VALIDACIÓN FALLÓ: {node_name}")
                print(f"   {str(e)}\n")
                raise
            
            # ════════════════════════════════════════════════════════
            # EJECUCIÓN DEL NODO (con compatibilidad legacy)
            # ════════════════════════════════════════════════════════
            try:
                # Extraer formato legacy para nodos que aún no migró
                legacy_state = extract_legacy_state_from_schema(validated_input)
                
                # Ejecutar nodo original
                result = node_fn(legacy_state)
                
                # Si el nodo retorna dict → mergear con estado actual
                if isinstance(result, dict):
                    # Mergear resultado parcial
                    legacy_state.update(result)
                    output_state = legacy_state
                else:
                    # El nodo retornó estado completo
                    output_state = result
                
            except Exception as e:
                # Error en ejecución del nodo
                print(f"\n❌ ERROR EN NODO: {node_name}")
                print(f"   {str(e)}\n")
                raise
            
            # ════════════════════════════════════════════════════════
            # POST-VALIDACIÓN
            # ════════════════════════════════════════════════════════
            stage_post = f"post:{node_name}"
            
            try:
                # Migrar output a schema
                if isinstance(output_state, dict):
                    # Preservar case_id y metadatos
                    output_state["case_id"] = validated_input.case_id
                    output_state["schema_version"] = validated_input.schema_version
                    output_state["created_at"] = validated_input.created_at
                    
                    validated_output = migrate_legacy_state_to_schema(output_state)
                else:
                    validated_output = output_state
                
                # Validar estado de salida
                validated_output = validate_state(validated_output, stage=stage_post)
                
                # Log snapshot
                log_state_snapshot(validated_output, stage_post)
                
                return validated_output
                
            except ValueError as e:
                # Validación post falló → HARD FAIL
                print(f"\n❌ POST-VALIDACIÓN FALLÓ: {node_name}")
                print(f"   El nodo '{node_name}' rompió el contrato de estado")
                print(f"   {str(e)}\n")
                raise
        
        return wrapped_node
    return decorator


# ========================================
# WRAPPERS DE TODOS LOS NODOS
# ========================================

from app.graphs.nodes import (
    ingest_documents as _ingest_documents,
    analyze_timeline as _analyze_timeline,
    detect_risks as _detect_risks,
    legal_hardening as _legal_hardening,
    legal_article_mapper as _legal_article_mapper,
    build_report as _build_report
)

from app.graphs.nodes_llm import (
    auditor_llm_node as _auditor_llm_node,
    prosecutor_llm_node as _prosecutor_llm_node
)

from app.graphs.nodes_rule_engine import (
    apply_rule_engine as _apply_rule_engine
)


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
    print("\n" + "="*80)
    print("🚀 PHOENIX LEGAL — INICIO DE ANÁLISIS")
    print("="*80)
    print(f"  case_id: {case_id}")
    print(f"  schema_version: {schema_version}")
    print(f"  nodes: {' → '.join(node_names)}")
    print("="*80 + "\n")

