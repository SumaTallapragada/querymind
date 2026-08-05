"""Immutable data models for the Result Formatter / Answer Generator.

`BusinessAnswer` is the single output type of
`querymind.result_formatter.engine.ResultFormatterEngine.format` -- a
successful `querymind.sql_execution.SQLExecutionResult`, reduced to a
formatted table plus a deterministic, non-interpretive summary and
classification. Nothing here performs a business calculation or infers
meaning beyond what `SQLExecutionResult` itself already contains.

`FormattedTable.columns` reuses `querymind.sql_execution.QueryColumn`
directly (not a re-declared duplicate) -- per this phase's "do not
duplicate any existing models" rule, and because `QueryColumn` already
carries everything a formatted column needs (`name`, `database_type`,
`python_type`, `nullable`). `BusinessAnswer.execution_result` reuses
`querymind.sql_execution.SQLExecutionResult` the same way, for
traceability back to the exact query that produced this answer.

Every model is frozen (`model_config = ConfigDict(frozen=True,
extra="forbid")`) and uses `tuple`, never `list`, for collections --
matching every other phase's models package.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from querymind.sql_execution import QueryColumn, SQLExecutionResult


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class AnswerType(str, Enum):
    """What shape of answer a `BusinessAnswer` represents, determined by `AnswerGenerator`."""

    SCALAR = "scalar"
    TABLE = "table"
    EMPTY_RESULT = "empty_result"
    AGGREGATION = "aggregation"
    DETAIL = "detail"


class AnswerSummary(_FrozenModel):
    """A concise, deterministic summary derived only from the execution result itself."""

    title: str = Field(description="A short, one-line summary, e.g. 'Returned 154 rows.'.")
    description: str = Field(description="A slightly longer, still-deterministic description.")
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    contains_numeric: bool = Field(
        description="Whether any column's python_type is a numeric type (int/float/Decimal)."
    )
    contains_dates: bool = Field(
        description="Whether any column's python_type is a temporal type (date/datetime)."
    )


class FormattedValue(_FrozenModel):
    """One value, before and after deterministic formatting."""

    original_value: Any = Field(description="The raw value exactly as `QueryRow` carried it.")
    formatted_value: str = Field(description="The deterministic, locale-independent text form.")
    detected_type: str = Field(
        description="The Python type name `ValueFormatter` detected, e.g. 'int', 'datetime'."
    )


class FormattedRow(_FrozenModel):
    """One immutable row of `FormattedValue`s, in the same order as `FormattedTable.columns`."""

    values: tuple[FormattedValue, ...]


class FormattedTable(_FrozenModel):
    """The complete formatted result set: columns (reused from `sql_execution`) and rows."""

    columns: tuple[QueryColumn, ...]
    rows: tuple[FormattedRow, ...]


class AnswerStatistics(_FrozenModel):
    """Observability data about one `ResultFormatterEngine.format` call."""

    formatting_latency_ms: float = Field(ge=0.0, description="Wall-clock time the whole call took.")
    rows_processed: int = Field(ge=0)
    columns_processed: int = Field(ge=0)
    values_formatted: int = Field(ge=0)


class BusinessAnswer(_FrozenModel):
    """The complete output of one formatting attempt."""

    answer_type: AnswerType
    summary: AnswerSummary
    formatted_table: FormattedTable
    statistics: AnswerStatistics
    execution_result: SQLExecutionResult = Field(
        description="The SQLExecutionResult this answer was built from, unmodified."
    )
