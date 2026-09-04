import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_are_normalized() -> None:
    settings = Settings(_env_file=None, cors_origins="http://localhost:5173, https://example.test ")

    assert settings.cors_origin_list == ["http://localhost:5173", "https://example.test"]


def test_identity_security_defaults_are_safe_for_local_development() -> None:
    settings = Settings(_env_file=None)

    assert settings.csrf_cookie_name != settings.session_cookie_name
    assert settings.csrf_header_name == "X-CSRF-Token"
    assert settings.login_rate_limit_attempts == 5
    assert settings.login_rate_limit_source_attempts > settings.login_rate_limit_attempts
    assert settings.login_rate_limit_lock_seconds > settings.login_rate_limit_window_seconds
    assert settings.edit_lock_lease_seconds == 90
    assert settings.effective_edit_lock_heartbeat_seconds == 30


def test_character_import_blank_defaults_match_business_rules() -> None:
    settings = Settings(_env_file=None)

    assert settings.import_default_treasure_damage is False
    assert settings.import_default_fixed_lead_team_buffer is False
    assert settings.import_default_group_hunt is False
    assert settings.import_default_raid_participant is True


def test_edit_lock_heartbeat_is_capped_below_half_the_lease() -> None:
    settings = Settings(_env_file=None, edit_lock_lease_seconds=60, edit_lock_heartbeat_seconds=45)

    assert settings.effective_edit_lock_heartbeat_seconds == 30


def test_natural_language_rules_are_disabled_without_a_key_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.natural_language_rules_enabled is False
    assert settings.deepseek_model == "deepseek-v4-flash"
    assert settings.rule_prompt_version == "schedule-rules-v2"
    assert settings.natural_language_rule_rate_limit_requests == 10


def test_enabling_natural_language_rules_requires_secure_provider_config() -> None:
    with pytest.raises(ValidationError, match="DEEPSEEK_API_KEY"):
        Settings(_env_file=None, natural_language_rules_enabled=True)

    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            _env_file=None,
            natural_language_rules_enabled=True,
            deepseek_api_key="secret",
            deepseek_base_url="http://api.deepseek.com",
        )


def test_isolated_tests_can_use_the_internal_http_rule_provider() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        natural_language_rules_enabled=True,
        deepseek_api_key="fixture-only",
        deepseek_base_url="http://rule-provider:18080",
        deepseek_model="deepseek-v4-e2e-fixture",
    )

    assert settings.deepseek_base_url == "http://rule-provider:18080"

    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            _env_file=None,
            environment="test",
            natural_language_rules_enabled=True,
            deepseek_api_key="fixture-only",
            deepseek_base_url="http://external.example.com",
        )


def test_source_login_limit_cannot_be_lower_than_account_source_limit() -> None:
    with pytest.raises(ValidationError, match="LOGIN_RATE_LIMIT_SOURCE_ATTEMPTS"):
        Settings(
            _env_file=None,
            login_rate_limit_attempts=10,
            login_rate_limit_source_attempts=5,
        )


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
        Settings(_env_file=None, **values)


def test_production_accepts_explicit_https_and_replaced_secrets() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        cookie_secure=True,
        cors_origins="https://dnf.example.com",
        database_url="postgresql+psycopg://dnf:strong-password@db/dnf",
        bootstrap_owner_password="strong-owner-password",
    )

    assert settings.environment == "production"
