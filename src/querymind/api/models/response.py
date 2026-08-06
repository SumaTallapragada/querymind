"""HTTP response DTOs for the QueryMind API.

Every real endpoint response is one of the engine layer's own models,
used directly as a FastAPI `response_model` (`QueryMindResponse`,
`GeneratedSqlResult`, `SQLValidationResult`, `SQLRepairResult`,
`SQLExecutionResult`, `BusinessAnswer`, `HealthReport`,
`DiagnosticsReport`, `MetricsSnapshot`) -- none of them are re-declared
here. `ErrorResponse` is the error envelope every mapped exception is
rendered as (`querymind.api.exception_handlers`). `SettingsResponse`
(Phase 18) is the one other genuinely new shape: nothing in the engine
layer already models "read-only application configuration for display,"
since no prior phase needed to expose it -- see
`querymind.api.routers.settings`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    """The JSON body of every error response this API returns. Never a raw traceback."""

    model_config = ConfigDict(extra="forbid")

    detail: str = Field(description="A human-readable description of what went wrong.")
    error_type: str = Field(
        description="The mapped exception's class name, e.g. 'EmptyQuestionError'."
    )


class SettingsResponse(BaseModel):
    """Read-only application configuration, safe to show a human. Never a secret -- no password,
    no API key, no connection string. Backs the Phase 18 frontend's Settings page.
    """

    model_config = ConfigDict(extra="forbid")

    app_name: str
    version: str = Field(description="The installed `querymind` package version.")
    environment: str = Field(description="`Settings.app_env` -- e.g. 'development', 'production'.")
    api_v1_prefix: str
    database_engine: str = Field(description="Always 'PostgreSQL' today -- see ARCHITECTURE.md.")
    database_name: str = Field(description="`Settings.postgres_db` -- a name, never a credential.")
    llm_provider: str
    llm_model: str
    streaming_transports: tuple[str, ...] = Field(
        description="Every streaming transport this backend serves, e.g. ('sse', 'websocket')."
    )
