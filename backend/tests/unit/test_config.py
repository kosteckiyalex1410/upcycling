from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from app.config import DEV_DATABASE_URL, REQUIRED_IN_PRODUCTION, Settings

SAFE_PRODUCTION: dict[str, Any] = {
    "environment": "production",
    "database_url": "postgresql+psycopg://app:pw@db.internal:5432/upcycling",
    "secret_key": SecretStr("p" * 48),
    "session_cookie_secure": True,
    "public_origin": "https://upcycling.example",
    "smtp_host": "smtp.example",
    "smtp_from": "Upcycling <no-reply@upcycling.example>",
    "smtp_starttls": True,
}


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)


def test_safe_production_settings_are_accepted() -> None:
    assert _settings(**SAFE_PRODUCTION).is_production


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"secret_key": SecretStr("dev-only-insecure-secret-key-change-me-0000")}, "SECRET_KEY"),
        ({"secret_key": SecretStr("short")}, "SECRET_KEY"),
        ({"session_cookie_secure": False}, "COOKIE_SECURE"),
        ({"public_origin": "http://upcycling.example"}, "PUBLIC_ORIGIN"),
        ({"extra_allowed_origins": ["http://localhost:5173"]}, "allowed origins"),
        ({"database_url": DEV_DATABASE_URL}, "development database"),
        ({"smtp_starttls": False}, "SMTP must use TLS"),
    ],
)
def test_unsafe_production_settings_are_rejected(override: dict[str, Any], fragment: str) -> None:
    with pytest.raises(ValidationError, match=fragment):
        _settings(**{**SAFE_PRODUCTION, **override})


def test_development_defaults_are_allowed() -> None:
    settings = _settings(environment="development", session_cookie_secure=False)
    assert settings.public_origin in settings.allowed_origins


@pytest.mark.parametrize("field", REQUIRED_IN_PRODUCTION)
def test_production_rejects_defaults_for_required_settings(field: str) -> None:
    """Secrets and endpoints must come from the environment, never from code defaults."""
    values = {k: v for k, v in SAFE_PRODUCTION.items() if k != field}
    with pytest.raises(ValidationError, match=f"UPCYCLING_{field.upper()} must be set explicitly"):
        _settings(**values)


def test_secure_cookie_uses_host_prefix() -> None:
    assert _settings(**SAFE_PRODUCTION).session_cookie_key == "__Host-upcycling_session"
    insecure_dev = _settings(environment="development", session_cookie_secure=False)
    assert insecure_dev.session_cookie_key == "upcycling_session"
