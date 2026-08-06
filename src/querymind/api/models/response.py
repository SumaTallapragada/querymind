"""HTTP response DTOs for the QueryMind API.

Every real endpoint response is one of the engine layer's own models,
used directly as a FastAPI `response_model` (`QueryMindResponse`,
`GeneratedSqlResult`, `SQLValidationResult`, `SQLRepairResult`,
`SQLExecutionResult`, `BusinessAnswer`, `HealthReport`,
`DiagnosticsReport`, `MetricsSnapshot`) -- none of them are re-declared
here. The one genuinely new shape is the error envelope every mapped
exception is rendered as (`querymind.api.exception_handlers`).
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
