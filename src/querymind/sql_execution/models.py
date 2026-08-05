"""Immutable data models for the SQL Execution Engine.

`SQLExecutionResult` is the single output type of
`querymind.sql_execution.engine.SQLExecutionEngine.execute` — a
`querymind.sql_generation.GeneratedSQL` (whose
`querymind.sql_validation.SQLValidationResult` reported it valid, or
whose `querymind.sql_repair.SQLRepairResult` reports it repaired), run
read-only against the real database via the existing SQLAlchemy engine,
reduced to one immutable status plus whatever rows came back — or, on
any rejection/failure, a structured `ExecutionError` instead. Rows are
returned exactly as the database produced them; nothing here performs a
business calculation, generates a chart, or explains a result.

Every model is frozen (`model_config = ConfigDict(frozen=True)`) and uses
`tuple`, never `list`, for collections — matching every other Phase's
models package: a Pydantic `frozen=True` model still allows in-place
mutation of a `list` field, a `tuple` field does not.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from querymind.query_library.models import SQLDialect


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ExecutionStatus(str, Enum):
    """The terminal outcome of one `SQLExecutionEngine.execute` call."""

    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class ExecutionError(_FrozenModel):
    """One structured error — never a raw database/driver exception reaching the caller."""

    code: str = Field(
        description="Short, stable, machine-readable identifier, e.g. 'execution_timeout'."
    )
    message: str = Field(description="Human-readable explanation of what went wrong.")
    details: str | None = Field(
        default=None, description="Additional context, e.g. the underlying driver error text."
    )


class QueryColumn(_FrozenModel):
    """One column's shape, as reported by the database driver for this specific result set."""

    name: str
    database_type: str = Field(
        description="The database's own type name for this column, e.g. 'bigint', 'varchar'."
    )
    python_type: str = Field(description="The Python type this column's values are represented as.")
    nullable: bool | None = Field(
        default=None,
        description="Whether this column may contain NULL, if the driver exposes that -- "
        "asyncpg's cursor metadata does not, so this is always None in practice.",
    )


class QueryRow(_FrozenModel):
    """One immutable row: values in the same order as `QueryResult.columns`."""

    values: tuple[Any, ...] = Field(
        description="This row's values. Typed `Any` deliberately -- a database row is "
        "genuinely heterogeneous (int/str/Decimal/datetime/bool/None/...), and its shape "
        "depends entirely on the query, not on anything knowable statically."
    )


class QueryResult(_FrozenModel):
    """The complete, unmodified result set of one successful query."""

    columns: tuple[QueryColumn, ...]
    rows: tuple[QueryRow, ...]
    row_count: int = Field(ge=0)


class ExecutionStatistics(_FrozenModel):
    """Observability data about one `SQLExecutionEngine.execute` call."""

    execution_latency_ms: float = Field(ge=0.0, description="Wall-clock time the whole call took.")
    rows_returned: int = Field(ge=0)
    columns_returned: int = Field(ge=0)
    database_name: str
    dialect: SQLDialect


class SQLExecutionResult(_FrozenModel):
    """The complete output of one execution attempt."""

    status: ExecutionStatus
    executed_sql: str = Field(
        description="The exact SQL text execution was attempted against -- kept for traceability, "
        "matching every other phase's result model."
    )
    query_result: QueryResult | None = Field(
        default=None, description="Populated only when status is SUCCESS."
    )
    statistics: ExecutionStatistics
    execution_error: ExecutionError | None = Field(
        default=None, description="Populated only when status is not SUCCESS."
    )
