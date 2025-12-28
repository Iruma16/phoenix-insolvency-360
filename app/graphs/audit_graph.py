from langgraph.graph import StateGraph, END

from app.graphs.state import AuditState
from app.graphs.nodes import (
    ingest_documents,
    analyze_timeline,
    detect_risks,
    build_report,
)


def build_audit_graph():
    graph = StateGraph(AuditState)

    # Nodos
    graph.add_node("ingest_documents", ingest_documents)
    graph.add_node("analyze_timeline", analyze_timeline)
    graph.add_node("detect_risks", detect_risks)
    graph.add_node("build_report", build_report)

    # Flujo
    graph.set_entry_point("ingest_documents")
    graph.add_edge("ingest_documents", "analyze_timeline")
    graph.add_edge("analyze_timeline", "detect_risks")
    graph.add_edge("detect_risks", "build_report")
    graph.add_edge("build_report", END)

    return graph.compile()
