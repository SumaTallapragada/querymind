"""Application configuration.

All runtime configuration flows through this module. Nothing in the
application is permitted to read ``os.environ`` directly outside of this
file — every other module receives configuration via the :class:`Settings`
object (typically through the :func:`get_settings` dependency), which keeps
the source of truth for "what can be configured" in exactly one place.

Settings are validated eagerly at process startup: if a required variable is
missing or malformed, the application fails fast with a clear error instead
of surfacing a confusing failure later at request time.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, PostgresDsn, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from querymind.llm.config import (
    DEFAULT_CLAUDE_BASE_URL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_RETRY_COUNT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    LLMProviderConfig,
)
from querymind.llm.models import LLMProvider

Environment = Literal["development", "staging", "production", "test"]
LogFormat = Literal["json", "console"]


class Settings(BaseSettings):
    """Strongly-typed application settings, sourced from environment variables.

    Values are read from the process environment first and fall back to a
    local ``.env`` file (see ``.env.example``) when present — this mirrors
    how the app is configured in Docker Compose (via ``env_file:``) versus
    local development.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Application ---------------------------------------------------
    app_name: str = Field(default="Text-to-SQL Analytics Engine")
    app_env: Environment = Field(default="development")
    app_debug: bool = Field(default=False)
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000, ge=1, le=65535)
    api_v1_prefix: str = Field(default="/api/v1")

    # -- Logging ---------------------------------------------------------
    log_level: str = Field(default="INFO")
    log_format: LogFormat = Field(default="json")

    # -- PostgreSQL --------------------------------------------------------
    # Names intentionally match the variables the official `postgres` Docker
    # image reads for first-run initialization, so one .env file drives both
    # the application's connection string and the database container itself.
    postgres_user: str
    postgres_password: SecretStr
    postgres_db: str
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432, ge=1, le=65535)

    # -- SQLAlchemy engine tuning -----------------------------------------
    database_pool_size: int = Field(default=10, ge=1)
    database_max_overflow: int = Field(default=5, ge=0)
    database_pool_timeout: int = Field(default=30, ge=1)
    database_echo: bool = Field(default=False)

    # -- LLM provider (Phase 16) ---------------------------------------------
    # `llm_api_key` defaults to empty rather than being required: a missing key is a real,
    # legitimate deployment state (the pipeline simply isn't configured to call an LLM yet)
    # that `querymind.observability.DiagnosticsEngine`'s `llm_configuration` check already
    # reports correctly, not something that should prevent the application from starting at
    # all -- unlike `postgres_password`, an application with no database connection can't
    # serve *any* traffic, but one with no LLM key can still serve health/diagnostics traffic.
    llm_provider: LLMProvider = Field(default=LLMProvider.CLAUDE)
    llm_model: str = Field(default="claude-sonnet-5")
    llm_api_key: SecretStr = Field(default=SecretStr(""))
    llm_temperature: float = Field(default=DEFAULT_TEMPERATURE, ge=0.0, le=1.0)
    llm_max_tokens: int = Field(default=DEFAULT_MAX_TOKENS, gt=0)
    llm_timeout_seconds: float = Field(default=DEFAULT_TIMEOUT_SECONDS, gt=0.0)
    llm_retry_count: int = Field(default=DEFAULT_RETRY_COUNT, ge=0)
    llm_base_url: str = Field(default=DEFAULT_CLAUDE_BASE_URL)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Async SQLAlchemy connection string, built from discrete parts.

        Building this from its components (rather than accepting one
        ``DATABASE_URL`` env var) prevents the connection string and the
        Postgres container's own bootstrap credentials from drifting apart.
        """
        password = quote_plus(self.postgres_password.get_secret_value())
        dsn = PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.postgres_user,
            password=password,
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.postgres_db,
        )
        return str(dsn)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def llm_provider_config(self) -> LLMProviderConfig:
        """Build the `LLMProviderConfig` the LLM Adapter needs, from the discrete `llm_*` fields.

        Mirrors `database_url`: one place assembles the real, phase-owned
        config object from `Settings`' own fields, so every caller (the
        API container, a script) gets the exact same construction logic.
        """
        return LLMProviderConfig(
            provider=self.llm_provider,
            model=self.llm_model,
            api_key=self.llm_api_key,
            temperature=self.llm_temperature,
            max_tokens=self.llm_max_tokens,
            timeout=self.llm_timeout_seconds,
            retry_count=self.llm_retry_count,
            base_url=self.llm_base_url,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton.

    ``lru_cache`` gives us a single, memoized instance without reaching for
    a global variable or a DI container — the settings are read from the
    environment exactly once per process, and FastAPI's dependency
    injection (``Depends(get_settings)``) makes it trivial to override in
    tests via ``app.dependency_overrides``.
    """
    return Settings()
