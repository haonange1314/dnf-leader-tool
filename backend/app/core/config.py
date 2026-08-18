from functools import lru_cache

from pydantic import Field
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
    session_ttl_hours: int = Field(default=168, ge=1, le=24 * 90)
    cookie_secure: bool = False
    bootstrap_owner_username: str | None = None
    bootstrap_owner_password: str | None = None
    import_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    import_max_rows: int = Field(default=10_000, ge=1, le=100_000)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
