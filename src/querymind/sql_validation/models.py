"""Immutable data models for the SQL Validation Engine.

`SQLValidationResult` is the single output type of
`querymind.sql_validation.engine.SQLValidationEngine.validate` — a
`querymind.sql_generation.GeneratedSQL`, checked by ten independent
validators against sqlglot's parsed AST plus the existing Metadata
Engine, Relationship Graph, and Business Knowledge Engine, reduced to one
immutable pass/fail verdict with full explainability. Nothing here
generates, modifies, repairs, optimizes, or executes SQL.

Every model is frozen (`model_config = ConfigDict(frozen=True)`) and uses
`tuple`, never `list`, for collections — matching every other Phase's
models package: a Pydantic `frozen=True` model still allows in-place
mutation of a `list` field, a `tuple` field does not.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from querymind.sql_generation.models import GeneratedSQL


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ValidationSeverity(str, Enum):
    """How serious a `ValidationIssue` is."""

    ERROR = "error"
    WARNING = "warning"


class ValidationIssue(_FrozenModel):
    """One problem a validator found — data, never raised as an exception.

    `code` is a short, stable, machine-readable identifier (e.g.
    `"unknown_table"`, `"unsupported_function"`) — what a caller should
    match on programmatically. `message` is the human-readable
    explanation. `location`/`related_object` are populated whenever a
    validator can point at *what* specifically triggered the issue —
    `location` for where in the SQL text, `related_object` for which
    table/column/alias/function the issue concerns.
    """

    code: str = Field(
        description="Short, stable, machine-readable identifier, e.g. 'unknown_table'."
    )
    severity: ValidationSeverity
    message: str = Field(description="Human-readable explanation of the problem.")
    location: str | None = Field(
        default=None, description="Where in the SQL this was found, if available."
    )
    related_object: str | None = Field(
        default=None,
        description="The table/column/alias/function name this issue concerns, if any.",
    )


class ValidationWarning(ValidationIssue):
    """A `ValidationIssue` whose severity is pinned to `WARNING` — never blocks `is_valid`."""

    severity: Literal[ValidationSeverity.WARNING] = ValidationSeverity.WARNING


class ValidatorExecutionTime(_FrozenModel):
    """How long one validator took to run, within one `SQLValidationEngine.validate` call."""

    validator: str = Field(description="The validator's name, e.g. 'schema', 'join'.")
    duration_ms: float = Field(ge=0.0)


class ValidationStatistics(_FrozenModel):
    """Observability data about one `SQLValidationEngine.validate` call."""

    validation_latency_ms: float = Field(
        ge=0.0, description="Wall-clock time the whole validate() call took."
    )
    validator_execution_times: tuple[ValidatorExecutionTime, ...] = Field(default=())
    table_count: int = Field(ge=0, description="Distinct base tables referenced in the SQL.")
    column_count: int = Field(ge=0, description="Distinct columns referenced in the SQL.")
    join_count: int = Field(ge=0, description="JOIN clauses in the SQL.")
    function_count: int = Field(ge=0, description="Distinct function calls referenced in the SQL.")
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)


class SQLValidationResult(_FrozenModel):
    """The complete output of one validation run: verdict, every issue found, plus statistics."""

    generated_sql: GeneratedSQL = Field(description="The input this validation was run against.")
    is_valid: bool = Field(description="Whether validation found zero ERROR-severity issues.")
    errors: tuple[ValidationIssue, ...] = Field(default=())
    warnings: tuple[ValidationIssue, ...] = Field(default=())
    validated_tables: tuple[str, ...] = Field(
        default=(), description="Every distinct base table name referenced in the SQL."
    )
    validated_columns: tuple[str, ...] = Field(
        default=(), description="Every distinct 'table.column' or bare column name referenced."
    )
    validated_functions: tuple[str, ...] = Field(
        default=(), description="Every distinct function name referenced, canonicalized uppercase."
    )
    validation_statistics: ValidationStatistics
