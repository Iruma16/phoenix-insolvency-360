"""
Tests de helpers comunes de UI.

Tests puros sin Streamlit.
100% testeables y rápidos.
"""
from app.ui.components_modules.common import get_confidence_emoji, get_field_value


class TestGetFieldValue:
    """Tests de extracción de valores de campos."""

    def test_dict_with_value_key(self):
        """Extrae valor de dict con key 'value'."""
        field = {"value": 100, "confidence": "HIGH"}
        assert get_field_value(field) == 100

    def test_dict_with_value_key_float(self):
        """Extrae valor float de dict."""
        field = {"value": 123.45}
        assert get_field_value(field) == 123.45

    def test_direct_number_int(self):
        """Extrae número directo (int)."""
        assert get_field_value(100) == 100

    def test_direct_number_float(self):
        """Extrae número directo (float)."""
        assert get_field_value(123.45) == 123.45

    def test_none_input(self):
        """Retorna None para input None."""
        assert get_field_value(None) is None

    def test_dict_without_value_key(self):
        """Retorna None para dict sin key 'value'."""
        field = {"foo": "bar", "confidence": "HIGH"}
        assert get_field_value(field) is None

    def test_empty_dict(self):
        """Retorna None para dict vacío."""
        assert get_field_value({}) is None

    def test_zero_value(self):
        """Maneja correctamente valor 0."""
        assert get_field_value(0) == 0
        assert get_field_value({"value": 0}) == 0

    def test_negative_value(self):
        """Maneja correctamente valores negativos."""
        assert get_field_value(-100) == -100
        assert get_field_value({"value": -100}) == -100


class TestGetConfidenceEmoji:
    """Tests de emojis de confianza."""

    def test_high_confidence(self):
        """Retorna ✅ para HIGH confidence."""
        field = {"confidence": "HIGH", "value": 100}
        assert get_confidence_emoji(field) == "✅"

    def test_medium_confidence(self):
        """Retorna 🟡 para MEDIUM confidence."""
        field = {"confidence": "MEDIUM"}
        assert get_confidence_emoji(field) == "🟡"

    def test_low_confidence(self):
        """Retorna ❓ para LOW confidence."""
        field = {"confidence": "LOW"}
        assert get_confidence_emoji(field) == "❓"

    def test_none_input(self):
        """Retorna ❓ para input None."""
        assert get_confidence_emoji(None) == "❓"

    def test_dict_without_confidence_key(self):
        """Retorna ❓ para dict sin key 'confidence'."""
        field = {"value": 100}
        assert get_confidence_emoji(field) == "❓"

    def test_empty_dict(self):
        """Retorna ❓ para dict vacío."""
        assert get_confidence_emoji({}) == "❓"

    def test_non_dict_input(self):
        """Retorna ❓ para input no-dict."""
        assert get_confidence_emoji(100) == "❓"
        assert get_confidence_emoji("HIGH") == "❓"
        assert get_confidence_emoji([1, 2, 3]) == "❓"

    def test_unknown_confidence_level(self):
        """Retorna ❓ para nivel de confianza desconocido."""
        field = {"confidence": "UNKNOWN"}
        assert get_confidence_emoji(field) == "❓"

    def test_case_sensitivity(self):
        """Verifica que es case-sensitive."""
        field_lower = {"confidence": "high"}
        assert get_confidence_emoji(field_lower) == "❓"  # No matchea "HIGH"
