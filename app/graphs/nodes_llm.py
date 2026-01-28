"""
Nodos del grafo para agentes LLM (Auditor y Prosecutor).

Estos nodos conectan los agentes LLM con RAG para análisis contextualizado.
"""
from typing import Dict, Any

from app.graphs.state import AuditState
from app.agents_llm.auditor_llm import AuditorLLMAgent
from app.agents_llm.prosecutor_llm import ProsecutorLLMAgent
from app.core.database import get_session_factory
from app.rag.case_rag.service import query_case_rag
from app.rag.legal_rag.service import query_legal_rag


def auditor_llm_node(state: AuditState) -> Dict[str, Any]:
    """
    Nodo que ejecuta el agente Auditor LLM.
    
    Analiza documentos, timeline y riesgos heurísticos,
    generando razonamiento complementario.
    
    Usa RAG de casos para obtener contexto relevante.
    """
    case_id = state["case_id"]
    documents = state.get("documents", [])
    timeline = state.get("timeline", [])
    risks = state.get("risks", [])
    
    # Consultar RAG de casos para contexto
    rag_context = None
    try:
        SessionLocal = get_session_factory()
        with SessionLocal() as db:
            rag_context = query_case_rag(
                db=db,
                case_id=case_id,
                query="Resumen general de la situación financiera y documental del caso"
            )
            if rag_context:
                rag_context = rag_context[:1000]  # Limitar tamaño
    except Exception as e:
        print(f"⚠️  No se pudo consultar RAG de casos: {e}")
    
    # Ejecutar agente
    agent = AuditorLLMAgent()
    result = agent.analyze(
        case_id=case_id,
        documents=documents,
        timeline=timeline,
        risks=risks,
        case_rag_context=rag_context
    )
    
    print(f"🤖 Ejecutando Auditor LLM para caso {case_id}...")
    if result.get("llm_enabled"):
        summary = result.get("llm_summary", "")[:100]
        print(f"   ✅ Auditor LLM: {summary}...")
    else:
        print(f"   ⚠️  Auditor LLM deshabilitado (sin API key)")
    
    # Actualizar estado
    return {
        "auditor_llm": result
    }


def prosecutor_llm_node(state: AuditState) -> Dict[str, Any]:
    """
    Nodo que ejecuta el agente Prosecutor LLM.
    
    Analiza los riesgos y hallazgos legales, generando
    razonamiento legal complementario.
    
    Usa RAG legal para obtener fundamento jurídico relevante.
    """
    case_id = state["case_id"]
    risks = state.get("risks", [])
    legal_findings = state.get("legal_findings", [])
    documents = state.get("documents", [])
    
    # Consultar RAG legal para contexto
    legal_context = None
    try:
        # Construir query basada en los tipos de riesgo detectados
        risk_types = [r.get("risk_type", "") for r in risks]
        queries = []
        
        if "delay_filing" in risk_types:
            queries.append("deber de solicitar concurso")
        if "accounting_red_flags" in risk_types:
            queries.append("obligaciones contables")
        if "document_inconsistency" in risk_types or "documentation_gap" in risk_types:
            queries.append("deber de colaboración")
        
        if queries:
            legal_results = query_legal_rag(
                query=" ".join(queries),
                top_k=5,
                include_ley=True,
                include_jurisprudencia=False
            )
            
            if legal_results:
                # Formatear contexto legal
                context_parts = []
                for result in legal_results[:3]:
                    citation = result.get("citation", "")
                    text = result.get("text", "")[:200]
                    context_parts.append(f"{citation}: {text}")
                
                legal_context = "\n\n".join(context_parts)
    
    except Exception as e:
        print(f"⚠️  No se pudo consultar RAG legal: {e}")
    
    # Ejecutar agente
    agent = ProsecutorLLMAgent()
    result = agent.analyze(
        case_id=case_id,
        risks=risks,
        legal_findings=legal_findings,
        legal_rag_context=legal_context
    )
    
    print(f"⚖️  Ejecutando Prosecutor LLM para caso {case_id}...")
    if result.get("llm_enabled"):
        summary = result.get("llm_summary", "")[:100]
        print(f"   ✅ Prosecutor LLM: {summary}...")
    else:
        print(f"   ⚠️  Prosecutor LLM deshabilitado (sin API key)")
    
    # Actualizar estado
    return {
        "prosecutor_llm": result
    }
