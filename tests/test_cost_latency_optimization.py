"""
Tests de certificación para PUNTO 7: COSTE Y LATENCIA.

ESTRATEGIA: Pre-mock de sys.modules para evitar imports problemáticos.

Verifica:
- Consolidación de llamadas RAG (3 → 1)
- NO llamadas intermedias al LLM
- Certificaciones [CERT] emitidas
- Métricas de reducción de coste/latencia
"""
import sys
from unittest.mock import MagicMock

# ============================================================================
# PRE-MOCK: ANTES de cualquier import de app
# ============================================================================

# Mock SQLAlchemy (evita evaluación de int | None)
mock_sa = MagicMock()
mock_sa.orm.Session = MagicMock
sys.modules['sqlalchemy'] = mock_sa
sys.modules['sqlalchemy.orm'] = mock_sa.orm
sys.modules['sqlalchemy.ext.declarative'] = MagicMock()

# Mock modelos
sys.modules['app.models'] = MagicMock()
sys.modules['app.models.document'] = MagicMock()
sys.modules['app.models.document_chunk'] = MagicMock()

# Mock embeddings/chromadb
sys.modules['chromadb'] = MagicMock()
sys.modules['app.services.embeddings_pipeline'] = MagicMock()

# Verificar versión Python
python_version = sys.version_info
print(f"[CERT] PYTHON_VERSION = {python_version.major}.{python_version.minor}")

# ============================================================================
# Imports después de pre-mock
# ============================================================================

import pytest
from unittest.mock import patch
from io import StringIO


def capture_stdout(func):
    """Captura stdout."""
    def wrapper(*args, **kwargs):
        old_stdout = sys.stdout
        sys.stdout = new_stdout = StringIO()
        try:
            result = func(*args, **kwargs)
            output = new_stdout.getvalue()
            return result, output
        finally:
            sys.stdout = old_stdout
    return wrapper


@pytest.fixture
def mock_deps():
    """Mock de dependencias del prosecutor."""
    
    mock_rag_result = MagicMock()
    mock_rag_result.sources = [
        {
            "chunk_id": "chunk_001",
            "document_id": "doc.pdf",
            "page": 1,
            "start_char": 0,
            "end_char": 100,
            "content": "Test"
        }
    ]
    mock_rag_result.context_text = "Context"
    mock_rag_result.confidence = "alta"
    mock_rag_result.hallucination_risk = False
    
    mock_legal = [{"citation": "TRLC Art. 5", "text": "Legal", "authority_level": "norma"}]
    
    mock_db = MagicMock()
    mock_db.close = MagicMock()
    
    # get_session_factory() retorna una función que cuando se llama retorna la sesión
    mock_session_maker = lambda: mock_db
    
    with patch("app.agents.agent_2_prosecutor.logic.rag_answer_internal", return_value=mock_rag_result) as m_rag, \
         patch("app.agents.agent_2_prosecutor.logic.query_legal_rag", return_value=mock_legal) as m_legal, \
         patch("app.agents.agent_2_prosecutor.logic.get_session_factory", return_value=mock_session_maker):
        
        yield {"rag": m_rag, "legal": m_legal}


def test_single_rag_legal_call_only(mock_deps):
    """Test 1: query_legal_rag se llama SOLO 1 vez."""
    from app.agents.agent_2_prosecutor.logic import ejecutar_analisis_prosecutor
    
    @capture_stdout
    def run():
        return ejecutar_analisis_prosecutor(case_id="test_001")
    
    result, output = run()
    
    assert mock_deps["legal"].call_count == 1
    print("✅ PASSED: test_single_rag_legal_call_only")


def test_no_intermediate_llm_calls_cert(mock_deps):
    """Test 2: Verifica [CERT] NO_INTERMEDIATE_LLM_CALLS."""
    from app.agents.agent_2_prosecutor.logic import ejecutar_analisis_prosecutor
    
    @capture_stdout
    def run():
        return ejecutar_analisis_prosecutor(case_id="test_002")
    
    result, output = run()
    
    assert "[CERT] NO_INTERMEDIATE_LLM_CALLS = OK" in output
    print("✅ PASSED: test_no_intermediate_llm_calls_cert")


def test_all_certifications_emitted(mock_deps):
    """Test 3: Verifica TODAS las certificaciones."""
    from app.agents.agent_2_prosecutor.logic import ejecutar_analisis_prosecutor
    
    @capture_stdout
    def run():
        return ejecutar_analisis_prosecutor(case_id="test_003")
    
    result, output = run()
    
    required = [
        "TOOL_CHAIN_DETECTED",
        "CONTEXT_REDUCTION",
        "TOOL_CHAIN_SCOPE",
        "NO_INTERMEDIATE_LLM_CALLS",
        "COST_LATENCY_COMPARISON"
    ]
    
    for cert in required:
        assert f"[CERT] {cert}" in output or f"[CERT] {cert.lower()}" in output
    
    print("✅ PASSED: test_all_certifications_emitted")


def test_cost_latency_metrics_present(mock_deps):
    """Test 4: Verifica métricas en COST_LATENCY_COMPARISON."""
    from app.agents.agent_2_prosecutor.logic import ejecutar_analisis_prosecutor
    
    @capture_stdout
    def run():
        return ejecutar_analisis_prosecutor(case_id="test_004")
    
    result, output = run()
    
    assert "[CERT] COST_LATENCY_COMPARISON" in output
    
    cost_line = [l for l in output.split("\n") if "COST_LATENCY_COMPARISON" in l][0]
    
    metrics = [
        "before_latency_ms=",
        "after_latency_ms=",
        "before_tokens=",
        "after_tokens=",
        "reduction_latency_pct=",
        "reduction_tokens_pct="
    ]
    
    for metric in metrics:
        assert metric in cost_line
    
    import re
    lat_pct = int(re.search(r"reduction_latency_pct=(\d+)", cost_line).group(1))
    tok_pct = int(re.search(r"reduction_tokens_pct=(\d+)", cost_line).group(1))
    
    assert lat_pct >= 50
    assert tok_pct >= 30
    
    print(f"✅ PASSED: test_cost_latency_metrics_present (lat={lat_pct}%, tok={tok_pct}%)")


def test_context_reduction_verified(mock_deps):
    """Test 5: Verifica reducción 3→1."""
    from app.agents.agent_2_prosecutor.logic import ejecutar_analisis_prosecutor
    
    @capture_stdout
    def run():
        return ejecutar_analisis_prosecutor(case_id="test_005")
    
    result, output = run()
    
    assert "[CERT] CONTEXT_REDUCTION before_legal_rag_calls=3 after_legal_rag_calls=1" in output
    
    print("✅ PASSED: test_context_reduction_verified")


def test_tool_chain_scope_present(mock_deps):
    """Test 6: Verifica TOOL_CHAIN_SCOPE."""
    from app.agents.agent_2_prosecutor.logic import ejecutar_analisis_prosecutor
    
    @capture_stdout
    def run():
        return ejecutar_analisis_prosecutor(case_id="test_006")
    
    result, output = run()
    
    assert "[CERT] TOOL_CHAIN_SCOPE" in output
    
    scope_line = [l for l in output.split("\n") if "TOOL_CHAIN_SCOPE" in l][0]
    
    assert "flows_optimized=" in scope_line
    assert "flows_not_applicable=" in scope_line
    assert "prosecutor_analysis" in scope_line
    
    print("✅ PASSED: test_tool_chain_scope_present")


def test_no_redundant_legal_queries(mock_deps):
    """Test 7: Verifica ausencia de llamadas redundantes."""
    from app.agents.agent_2_prosecutor.logic import ejecutar_analisis_prosecutor
    
    mock_deps["legal"].reset_mock()
    
    @capture_stdout
    def run():
        return ejecutar_analisis_prosecutor(case_id="test_007")
    
    result, output = run()
    
    assert mock_deps["legal"].call_count == 1
    
    print("✅ PASSED: test_no_redundant_legal_queries")
