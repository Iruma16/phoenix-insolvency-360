from langgraph.graph import END, StateGraph

from app.graphs.state import AuditState

# ⚠️ IMPORTANTE: Usar nodos validados con contrato de estado HARD
from app.graphs.validated_nodes import (
    analyze_timeline,
    apply_rule_engine,
    auditor_llm_node,
    build_report,
    detect_risks,
    ingest_documents,
    legal_article_mapper,
    legal_hardening,
    prosecutor_llm_node,
)


def build_audit_graph():
    # ⚠️ NOTA: Aún usa AuditState para compatibilidad con LangGraph
    # Los nodos validados manejan la conversión interna
    graph = StateGraph(AuditState)

    # Nodos heurísticos (existentes)
    graph.add_node("ingest_documents", ingest_documents)
    graph.add_node("analyze_timeline", analyze_timeline)
    graph.add_node("detect_risks", detect_risks)
    graph.add_node("legal_hardening", legal_hardening)

    # Nodos nuevos (LLM + Rule Engine)
    graph.add_node("auditor_llm", auditor_llm_node)
    graph.add_node("rule_engine", apply_rule_engine)
    graph.add_node("prosecutor_llm", prosecutor_llm_node)

    # Nodos finales
    graph.add_node("legal_article_mapper", legal_article_mapper)
    graph.add_node("build_report", build_report)

    # Flujo mejorado:
    # ingest → timeline → risks
    # → hardening → auditor_llm (enriquecimiento doc)
    # → rule_engine (reglas deterministas)
    # → prosecutor_llm (enriquecimiento legal)
    # → mapper → report

    graph.set_entry_point("ingest_documents")
    graph.add_edge("ingest_documents", "analyze_timeline")
    graph.add_edge("analyze_timeline", "detect_risks")
    graph.add_edge("detect_risks", "legal_hardening")
    graph.add_edge("legal_hardening", "auditor_llm")
    graph.add_edge("auditor_llm", "rule_engine")
    graph.add_edge("rule_engine", "prosecutor_llm")
    graph.add_edge("prosecutor_llm", "legal_article_mapper")
    graph.add_edge("legal_article_mapper", "build_report")
    graph.add_edge("build_report", END)

    return graph.compile()
