"""Shared fixtures and builders for Result Formatter / Answer Generator tests.

`engine`/`connection_provider` mirror `tests/sql_execution/conftest.py`
exactly (real, already-running local Postgres, function-scoped to avoid
the cross-event-loop pitfall documented there) -- only
`test_integration.py` uses them, to produce a genuine
`SQLExecutionResult` via the real, already-verified `sql_execution`
package rather than a hand-built one. Every other test file uses the
synthetic `make_execution_result`/`make_query_result` builders below,
which mirror `tests/sql_execution/conftest.py`'s `make_generated_sql`
pattern.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from querymind.core.config import Settings
from querymind.db.engine import create_engine
from querymind.llm.models import FinishReason, GenerationMetrics, LLMProvider, TokenUsage
from querymind.query_library.models import SQLDialect
from querymind.sql_execution import (
    DatabaseConnectionProvider,
    ExecutionStatistics,
    ExecutionStatus,
    QueryColumn,
    QueryResult,
    QueryRow,
    SQLExecutionResult,
)
from querymind.sql_generation.models import (
    ExtractionMethod,
    GeneratedSQL,
    SQLGenerationStatistics,
    SQLStatementType,
)
from querymind.sql_validation.models import SQLValidationResult, ValidationStatistics

# --- real database engine / connection provider (test_integration.py only) ---------------


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Function-scoped -- see `tests/sql_execution/conftest.py`'s `engine` fixture docstring
    for why a session-scoped `AsyncEngine` breaks across this project's per-test event loops."""
    db_engine = create_engine(settings)
    yield db_engine
    await db_engine.dispose()


@pytest.fixture
def connection_provider(engine: AsyncEngine) -> DatabaseConnectionProvider:
    return DatabaseConnectionProvider(engine)


# --- synthetic QueryResult / SQLExecutionResult builders ----------------------------------


def make_column(
    name: str, *, database_type: str = "bigint", python_type: str = "int"
) -> QueryColumn:
    return QueryColumn(
        name=name, database_type=database_type, python_type=python_type, nullable=None
    )


def make_query_result(
    columns: tuple[QueryColumn, ...], rows: tuple[tuple[Any, ...], ...]
) -> QueryResult:
    return QueryResult(
        columns=columns,
        rows=tuple(QueryRow(values=row) for row in rows),
        row_count=len(rows),
    )


def make_execution_result(
    sql: str,
    query_result: QueryResult | None,
    *,
    status: ExecutionStatus = ExecutionStatus.SUCCESS,
    dialect: SQLDialect = SQLDialect.POSTGRESQL,
) -> SQLExecutionResult:
    return SQLExecutionResult(
        status=status,
        executed_sql=sql,
        query_result=query_result,
        statistics=ExecutionStatistics(
            execution_latency_ms=1.0,
            rows_returned=query_result.row_count if query_result is not None else 0,
            columns_returned=len(query_result.columns) if query_result is not None else 0,
            database_name="querymind",
            dialect=dialect,
        ),
        execution_error=None,
    )


def make_generated_sql(
    sql: str,
    *,
    dialect: SQLDialect = SQLDialect.POSTGRESQL,
    statement_type: SQLStatementType = SQLStatementType.SELECT,
) -> GeneratedSQL:
    return GeneratedSQL(
        sql=sql,
        statement_type=statement_type,
        raw_llm_content=sql,
        dialect=dialect,
        llm_metrics=GenerationMetrics(
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-5",
            latency_ms=1.0,
            token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
            retry_count=0,
            finish_reason=FinishReason.COMPLETE,
        ),
        statistics=SQLGenerationStatistics(
            extraction_method=ExtractionMethod.RAW_TEXT,
            raw_sql_length=len(sql),
            normalized_sql_length=len(sql),
            normalization_changed_sql=False,
            generation_latency_ms=1.0,
        ),
    )


def make_validation_result(generated_sql: GeneratedSQL) -> SQLValidationResult:
    return SQLValidationResult(
        generated_sql=generated_sql,
        is_valid=True,
        errors=(),
        warnings=(),
        validated_tables=(),
        validated_columns=(),
        validated_functions=(),
        validation_statistics=ValidationStatistics(
            validation_latency_ms=1.0,
            validator_execution_times=(),
            table_count=0,
            column_count=0,
            join_count=0,
            function_count=0,
            error_count=0,
            warning_count=0,
        ),
    )
