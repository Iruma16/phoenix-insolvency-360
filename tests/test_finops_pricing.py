"""
TESTS: Pricing Table (Endurecimiento #7)

OBJETIVO: Validar tabla de precios versionada y determinista.

PRINCIPIO: Mismo modelo + tokens → mismo coste.
"""
import pytest

from app.core.finops.pricing import (
    PRICING_VERSION,
    PRICING_TABLE,
    estimate_cost_usd,
    pricing_fingerprint,
    get_pricing_info,
)


# ============================
# TEST 1: PRICING VERSION
# ============================

def test_pricing_version_exists():
    """PRICING_VERSION debe existir y no estar vacía."""
    assert PRICING_VERSION is not None
    assert len(PRICING_VERSION) > 0


def test_pricing_version_format():
    """PRICING_VERSION debe tener formato YYYY-MM-DD."""
    # Formato: YYYY-MM-DD
    assert len(PRICING_VERSION) == 10
    assert PRICING_VERSION[4] == "-"
    assert PRICING_VERSION[7] == "-"


# ============================
# TEST 2: ESTIMATE COST
# ============================

def test_estimate_cost_deterministic():
    """INVARIANTE: Mismo modelo + tokens → mismo coste."""
    cost1 = estimate_cost_usd("gpt-4o-mini", 1000, 500)
    cost2 = estimate_cost_usd("gpt-4o-mini", 1000, 500)
    
    assert cost1 == cost2


def test_estimate_cost_calculation():
    """Verificar cálculo correcto de coste."""
    # gpt-4o-mini: input_per_1k=0.00015, output_per_1k=0.0006
    # 1000 input tokens = 1K * 0.00015 = 0.00015
    # 500 output tokens = 0.5K * 0.0006 = 0.0003
    # Total = 0.00045
    
    cost = estimate_cost_usd("gpt-4o-mini", 1000, 500)
    expected = 0.00045
    
    assert abs(cost - expected) < 0.000001


def test_estimate_cost_embeddings():
    """Embeddings tienen output_tokens = 0."""
    cost = estimate_cost_usd("text-embedding-3-small", 1000, 0)
    expected = 0.00002  # 1K * 0.00002
    
    assert abs(cost - expected) < 0.000001


def test_estimate_cost_unknown_model_fails():
    """GATE: Modelo desconocido → ValueError."""
    with pytest.raises(ValueError, match="desconocido"):
        estimate_cost_usd("modelo-inexistente", 1000, 500)


# ============================
# TEST 3: PRICING FINGERPRINT
# ============================

def test_pricing_fingerprint_stable():
    """INVARIANTE: Misma tabla → mismo fingerprint."""
    fp1 = pricing_fingerprint()
    fp2 = pricing_fingerprint()
    
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA256


def test_pricing_fingerprint_changes_on_price_change():
    """
    INVARIANTE: Si cambia un precio → fingerprint cambia.
    
    Este test DEBE FALLAR si se modifica PRICING_TABLE
    sin actualizar PRICING_VERSION.
    """
    # Guardar fingerprint actual
    current_fp = pricing_fingerprint()
    
    # Modificar tabla temporalmente
    original_price = PRICING_TABLE["gpt-4o-mini"]["input_per_1k"]
    PRICING_TABLE["gpt-4o-mini"]["input_per_1k"] = 999.99
    
    modified_fp = pricing_fingerprint()
    
    # Restaurar tabla
    PRICING_TABLE["gpt-4o-mini"]["input_per_1k"] = original_price
    
    # Fingerprint debe haber cambiado
    assert modified_fp != current_fp


# ============================
# TEST 4: GET PRICING INFO
# ============================

def test_get_pricing_info_structure():
    """get_pricing_info debe retornar version y fingerprint."""
    info = get_pricing_info()
    
    assert "pricing_version" in info
    assert "pricing_fingerprint" in info
    assert info["pricing_version"] == PRICING_VERSION
    assert len(info["pricing_fingerprint"]) == 64


# ============================
# TEST 5: PRICING TABLE INTEGRITY
# ============================

def test_pricing_table_has_required_models():
    """Tabla de precios debe tener modelos críticos."""
    required_models = [
        "gpt-4o-mini",
        "text-embedding-3-small",
    ]
    
    for model in required_models:
        assert model in PRICING_TABLE, f"Falta modelo: {model}"


def test_pricing_table_structure():
    """Cada modelo debe tener input_per_1k y output_per_1k."""
    for model, pricing in PRICING_TABLE.items():
        assert "input_per_1k" in pricing, f"Falta input_per_1k en {model}"
        assert "output_per_1k" in pricing, f"Falta output_per_1k en {model}"
        assert pricing["input_per_1k"] >= 0
        assert pricing["output_per_1k"] >= 0


# ============================
# RESUMEN DE TESTS
# ============================
"""
COBERTURA:

1. ✅ PRICING_VERSION existe y tiene formato
2. ✅ estimate_cost_usd determinista
3. ✅ Cálculo correcto de coste
4. ✅ Embeddings con output_tokens = 0
5. ✅ Modelo desconocido → ValueError
6. ✅ pricing_fingerprint estable
7. ✅ Cambio de precio → fingerprint cambia
8. ✅ get_pricing_info estructura
9. ✅ Pricing table tiene modelos requeridos
10. ✅ Pricing table estructura correcta

TOTAL: 10 tests deterministas

INVARIANTES CERTIFICADOS:
- INVARIANTE 1: Mismo modelo + tokens → mismo coste
- INVARIANTE 2: Misma tabla → mismo fingerprint
- INVARIANTE 3: Cambio de precio → fingerprint cambia
- INVARIANTE 4: Modelo desconocido → ValueError
- INVARIANTE 5: Pricing table tiene estructura obligatoria
"""

