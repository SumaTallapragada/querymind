"""Immutable data models for the SQL Repair Engine.

`SQLRepairResult` is the single output type of
`querymind.sql_repair.engine.SQLRepairEngine.repair` — a
`querymind.sql_generation.GeneratedSQL` and the
`querymind.sql_validation.SQLValidationResult` that reported it invalid,
repaired via the existing Prompt Compiler / LLM Adapter / SQL Validation
Engine over a bounded, deterministic loop. The original `GeneratedSQL` is
never mutated — every attempt produces a new artifact, and the complete,
immutable history of every attempt is always preserved. Nothing here
executes, optimizes, or explains SQL.

Every model is frozen (`model_config = ConfigDict(frozen=True)`) and uses
`tuple`, never `list`, for collections — matching every other Phase's
models package: a Pydantic `frozen=True` model still allows in-place
mutation of a `list` field, a `tuple` field does not.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from querymind.llm.models import GenerationMetrics
from querymind.sql_generation.models import GeneratedSQL
from querymind.sql_validation.models import SQLValidationResult


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class RepairReason(str, Enum):
    """The repair category `RepairPlanner` assigns to one attempt's dominant validation issue."""

    UNKNOWN_TABLE = "unknown_table"
    UNKNOWN_COLUMN = "unknown_column"
    SCHEMA_ISSUE = "schema_issue"
    INVALID_JOIN = "invalid_join"
    MISSING_GROUP_BY = "missing_group_by"
    AGGREGATE_ERROR = "aggregate_error"
    ALIAS_ISSUE = "alias_issue"
    UNSUPPORTED_FUNCTION = "unsupported_function"
    DIALECT_ISSUE = "dialect_issue"
    BUSINESS_RULE_MISMATCH = "business_rule_mismatch"
    UNSUPPORTED_STATEMENT = "unsupported_statement"
    SYNTAX_ERROR = "syntax_error"
    OTHER = "other"


class RepairStatus(str, Enum):
    """The terminal outcome of one `SQLRepairEngine.repair` call."""

    REPAIRED = "repaired"
    MAX_ATTEMPTS_REACHED = "max_attempts_reached"
    NO_PROGRESS = "no_progress"
    UNREPAIRABLE = "unrepairable"


class RepairAttempt(_FrozenModel):
    """One repair attempt: what was tried, what came back, and whether it worked."""

    attempt_number: int = Field(ge=1)
    repair_reason: RepairReason = Field(
        description="The dominant repair category this attempt targeted, per RepairPlanner."
    )
    input_sql: str = Field(description="The SQL text repair was attempted against.")
    repaired_sql: str = Field(description="The SQL text the repair LLM call produced.")
    validation_result: SQLValidationResult = Field(
        description="The result of re-validating `repaired_sql`."
    )
    prompt_version: str = Field(description="The repair CompiledPrompt's template_version.")
    llm_metrics: GenerationMetrics = Field(
        description="The repair LLM call's own metrics, unmodified."
    )
    success: bool = Field(description="Whether `repaired_sql` validated as fully valid.")


class RepairHistory(_FrozenModel):
    """Every attempt made during one repair run, in order. Nothing is ever overwritten."""

    attempts: tuple[RepairAttempt, ...] = Field(default=())

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def last_attempt(self) -> RepairAttempt | None:
        return self.attempts[-1] if self.attempts else None


class RepairStatistics(_FrozenModel):
    """Observability data about one `SQLRepairEngine.repair` call."""

    attempt_count: int = Field(ge=0)
    successful_repairs: int = Field(ge=0, description="How many attempts validated as fully valid.")
    failed_repairs: int = Field(ge=0, description="How many attempts still had at least one error.")
    repair_latency_ms: float = Field(
        ge=0.0, description="Wall-clock time the whole repair() call took, across every attempt."
    )
    average_validation_latency_ms: float = Field(
        ge=0.0, description="Mean validation_statistics.validation_latency_ms across every attempt."
    )


class SQLRepairResult(_FrozenModel):
    """The complete output of one repair run: original SQL, final SQL, and the full history."""

    original_sql: GeneratedSQL = Field(
        description="The GeneratedSQL passed into repair(), unmodified."
    )
    final_sql: GeneratedSQL = Field(
        description="The last SQL artifact produced -- repaired if any attempt ran, else identical "
        "to original_sql."
    )
    final_validation_result: SQLValidationResult = Field(
        description="The validation result for final_sql."
    )
    history: RepairHistory
    statistics: RepairStatistics
    status: RepairStatus
