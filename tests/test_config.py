import pytest

from app.config import Settings


def test_development_settings_have_safe_local_defaults() -> None:
    settings = Settings.from_env({})

    assert settings.environment == "development"
    assert settings.database_url == "sqlite:///./hsk_registration.db"
    assert settings.session_secret == "development-only-change-me"
    assert settings.secure_cookies is False


def test_production_requires_a_session_secret() -> None:
    with pytest.raises(ValueError, match="SESSION_SECRET is required"):
        Settings.from_env({"APP_ENV": "production"})


def test_production_enables_secure_cookies() -> None:
    settings = Settings.from_env(
        {"APP_ENV": "production", "SESSION_SECRET": "a" * 32}
    )

    assert settings.secure_cookies is True
