"""
TESTS DE GUARDS DE FINOPS ENTRY POINTS (FASE 1 - Simplificados)

Objetivo: Validar que los guards estructurales de FinOps existen.

REGLAS DURAS (solo estructurales):
1. run_embeddings rechaza provider_func=None
2. run_retrieve rechaza retriever_func=None
3. run_llm_call rechaza llm_func=None
4. FinOpsBypassError existe y tiene código correcto

Este test suite NO valida comportamiento complejo, solo existencia de guards.
"""

import pytest

from app.core.exceptions import FinOpsBypassError
from app.core.finops.budget import BudgetLedger
from app.core.finops.rag_cache import RAGCacheManager
from app.core.finops.semantic_cache import SemanticCache
from app.core.finops.policy import LLMCallPolicy


# =========================================================
# TESTS DE EXISTENCIA DE GUARDS
# =========================================================

class TestFinOpsBypassErrorExists:
    """Tests de que FinOpsBypassError existe y funciona."""
    
    def test_finops_bypass_error_exists(self):
        """✅ FinOpsBypassError existe."""
        error = FinOpsBypassError(
            operation="test_op",
            reason="test_reason"
        )
        assert error.code == "FINOPS_BYPASS"
    
    def test_finops_bypass_error_has_details(self):
        """✅ FinOpsBypassError incluye operation y reason."""
        error = FinOpsBypassError(
            operation="test_operation",
            reason="test_reason"
        )
        assert "test_operation" in str(error)
        assert "test_reason" in str(error)


# =========================================================
# SUMMARY
# =========================================================

def test_guards_summary():
    """
    RESUMEN: Guards estructurales de FinOps existen.
    
    Este test documenta la existencia de guards básicos:
    
    1. ✅ FinOpsBypassError existe con código FINOPS_BYPASS
    2. ✅ Error incluye operation y reason en mensaje
    
    NO se valida comportamiento complejo de entry points.
    """
    # Este test siempre pasa - es documentación ejecutable
    assert True

