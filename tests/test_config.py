from pathlib import Path

import pytest

import app
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


def test_production_rejects_a_short_session_secret() -> None:
    with pytest.raises(ValueError, match="at least 32 characters"):
        Settings.from_env({"APP_ENV": "production", "SESSION_SECRET": "short"})


def test_production_enables_secure_cookies() -> None:
    settings = Settings.from_env({"APP_ENV": "production", "SESSION_SECRET": "a" * 32})

    assert settings.secure_cookies is True


def test_default_document_template_path_is_package_relative() -> None:
    settings = Settings.from_env({})

    assert (
        settings.document_template_path
        == (
            Path(app.__file__).parent
            / "document_templates/hsk_registration_template.docx"
        ).resolve()
    )


def test_document_template_path_can_be_overridden(tmp_path: Path) -> None:
    configured_path = tmp_path / "institute-template.docx"

    settings = Settings.from_env(
        {
            "DOCUMENT_TEMPLATE_PATH": str(
                configured_path.parent / ".." / configured_path.name
            )
        }
    )

    assert (
        settings.document_template_path
        == configured_path.parent.parent.resolve() / configured_path.name
    )
