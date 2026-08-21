from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DNF 团长排表工具 API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+psycopg://dnf:dnf-local-only@localhost:5432/dnf_leader",
        validation_alias="DATABASE_URL",
    )
    cors_origins: str = "http://localhost:5173"
    solver_time_limit_seconds: int = Field(default=10, ge=1, le=60)
    solver_random_seed: int = 42
    session_cookie_name: str = "dnf_session"
    csrf_cookie_name: str = "dnf_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    session_ttl_hours: int = Field(default=168, ge=1, le=24 * 90)
    cookie_secure: bool = False
    login_rate_limit_attempts: int = Field(default=5, ge=1, le=100)
    login_rate_limit_source_attempts: int = Field(default=20, ge=2, le=1000)
    login_rate_limit_window_seconds: int = Field(default=300, ge=10, le=86_400)
    login_rate_limit_lock_seconds: int = Field(default=900, ge=10, le=86_400)
    edit_lock_header_name: str = "X-Edit-Lock-Token"
    edit_lock_lease_seconds: int = Field(default=90, ge=30, le=3600)
    edit_lock_heartbeat_seconds: int = Field(default=30, ge=10, le=1200)
    bootstrap_owner_username: str | None = None
    bootstrap_owner_password: str | None = None
    import_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    import_max_rows: int = Field(default=10_000, ge=1, le=100_000)

    @property
    def effective_edit_lock_heartbeat_seconds(self) -> int:
        return min(self.edit_lock_heartbeat_seconds, self.edit_lock_lease_seconds // 2)

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.login_rate_limit_source_attempts < self.login_rate_limit_attempts:
            raise ValueError(
                "LOGIN_RATE_LIMIT_SOURCE_ATTEMPTS must be at least LOGIN_RATE_LIMIT_ATTEMPTS"
            )
        if self.environment.casefold() != "production":
            return self
        if not self.cookie_secure:
            raise ValueError("production requires COOKIE_SECURE=true")
        origins = self.cors_origin_list
        if not origins or any(
            not origin.startswith("https://")
            or "localhost" in origin
            or "127.0.0.1" in origin
            or "*" in origin
            for origin in origins
        ):
            raise ValueError("production CORS_ORIGINS must contain only explicit HTTPS origins")
        if "dnf-local-only" in self.database_url or "replace-with" in self.database_url:
            raise ValueError("production database credentials must replace local examples")
        if not self.bootstrap_owner_password or any(
            marker in self.bootstrap_owner_password
            for marker in ("change-me-now", "dnf-local-only", "replace-with")
        ):
            raise ValueError("production owner password must replace local examples")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
