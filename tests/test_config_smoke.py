import pytest


@pytest.mark.smoke
def test_settings_load_smoke():
    from app.core.config import settings

    # Debe poder importarse y tener los campos básicos.
    assert settings is not None
    assert hasattr(settings, "database_url")
