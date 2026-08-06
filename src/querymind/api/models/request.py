"""HTTP request DTOs for the QueryMind API.

Created only where the engine layer's own models don't already fit an
HTTP request body directly. Two of these (`RepairRequest.validation_result`,
`ExecuteRequest.validation_result`) embed a real, reused
`querymind.sql_validation.SQLValidationResult` rather than re-declaring
its fields -- per this phase's "reuse immutable models wherever
possible" rule. `/query/format` needs no wrapper at all: it accepts a
`querymind.sql_execution.SQLExecutionResult` directly as the whole
request body.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from querymind.query_library.models import SQLDialect
from querymind.sql_validation.models import SQLValidationResult


class QuestionRequest(BaseModel):
    """The input to `/query` and `/query/sql` -- a single natural language question."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        min_length=1,
        description="A natural language business question.",
        examples=["Who are our top 5 customers by revenue?"],
    )


class SqlInputRequest(BaseModel):
    """The input to `/query/validate` -- raw SQL text, not produced by this pipeline's own LLM.

    Wrapped internally into a placeholder `GeneratedSQL` before being
    handed to `SQLValidationEngine.validate`, since that is the only
    input type the engine's public API accepts -- see
    `querymind.api.routers.validation` for exactly how.
    """

    model_config = ConfigDict(extra="forbid")

    sql: str = Field(
        min_length=1,
        description="The SQL text to validate.",
        examples=["SELECT customer_id FROM customers;"],
    )
    dialect: SQLDialect = Field(default=SQLDialect.POSTGRESQL)


class RepairRequest(BaseModel):
    """The input to `/query/repair` -- the SQL to repair (embedded in `validation_result`) plus
    the original question, needed to rebuild the retrieval context `SQLRepairEngine.repair`
    requires (a fresh HTTP request carries no prior pipeline state to reuse).
    """

    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        min_length=1, description="The same question that originally produced `validation_result`."
    )
    validation_result: SQLValidationResult = Field(
        description="The failed validation result for the SQL to repair."
    )


class ExecuteRequest(BaseModel):
    """The input to `/query/execute` -- a validated `SQLValidationResult` (which itself embeds
    the `GeneratedSQL` to execute; no separate `sql` field is needed).
    """

    model_config = ConfigDict(extra="forbid")

    validation_result: SQLValidationResult = Field(
        description="A validation result whose generated_sql should be executed."
    )
