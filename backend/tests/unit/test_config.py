import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_are_normalized() -> None:
    settings = Settings(cors_origins="http://localhost:5173, https://example.test ")

    assert settings.cors_origin_list == ["http://localhost:5173", "https://example.test"]


def test_identity_security_defaults_are_safe_for_local_development() -> None:
    settings = Settings()

    assert settings.csrf_cookie_name != settings.session_cookie_name
    assert settings.csrf_header_name == "X-CSRF-Token"
    assert settings.login_rate_limit_attempts == 5
    assert settings.login_rate_limit_source_attempts > settings.login_rate_limit_attempts
    assert settings.login_rate_limit_lock_seconds > settings.login_rate_limit_window_seconds
    assert settings.edit_lock_lease_seconds == 90
    assert settings.effective_edit_lock_heartbeat_seconds == 30


def test_edit_lock_heartbeat_is_capped_below_half_the_lease() -> None:
    settings = Settings(edit_lock_lease_seconds=60, edit_lock_heartbeat_seconds=45)

    assert settings.effective_edit_lock_heartbeat_seconds == 30


def test_source_login_limit_cannot_be_lower_than_account_source_limit() -> None:
    with pytest.raises(ValidationError, match="LOGIN_RATE_LIMIT_SOURCE_ATTEMPTS"):
        Settings(login_rate_limit_attempts=10, login_rate_limit_source_attempts=5)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"cookie_secure": False}, "COOKIE_SECURE"),
        ({"cors_origins": "http://dnf.example.com"}, "CORS_ORIGINS"),
        ({"database_url": "postgresql+psycopg://dnf:dnf-local-only@db/dnf"}, "database"),
        ({"bootstrap_owner_password": "change-me-now"}, "owner password"),
    ],
)
def test_production_rejects_insecure_configuration(
    overrides: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "environment": "production",
        "cookie_secure": True,
        "cors_origins": "https://dnf.example.com",
        "database_url": "postgresql+psycopg://dnf:strong-password@db/dnf",
        "bootstrap_owner_password": "strong-owner-password",
        **overrides,
    }

    with pytest.raises(ValidationError, match=message):
        Settings(**values)


def test_production_accepts_explicit_https_and_replaced_secrets() -> None:
    settings = Settings(
        environment="production",
        cookie_secure=True,
        cors_origins="https://dnf.example.com",
        database_url="postgresql+psycopg://dnf:strong-password@db/dnf",
        bootstrap_owner_password="strong-owner-password",
    )

    assert settings.environment == "production"
