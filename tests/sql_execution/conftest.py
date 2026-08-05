"""Shared fixtures and builders for SQL Execution Engine tests.

`engine`/`connection_provider` are built from the real, already-running
local Postgres instance (via the same `Settings`/`create_engine` the
application itself uses — see `querymind.db.engine`), mirroring
`tests/sql_repair/conftest.py`'s "real infrastructure, no mocks"
precedent for anything this phase is not itself responsible for
isolating. `GeneratedSQL`/`SQLValidationResult` builders mirror
`tests/sql_repair/conftest.py`'s `make_generated_sql`/
`make_validation_result` exactly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from querymind.core.config import Settings
from querymind.db.engine import create_engine
from querymind.llm.models import FinishReason, GenerationMetrics, LLMProvider, TokenUsage
from querymind.query_library.models import SQLDialect
from querymind.sql_execution.connection import DatabaseConnectionProvider
from querymind.sql_generation.models import (
    ExtractionMethod,
    GeneratedSQL,
    SQLGenerationStatistics,
    SQLStatementType,
)
from querymind.sql_validation.models import (
    SQLValidationResult,
    ValidationIssue,
    ValidationSeverity,
    ValidationStatistics,
)

# --- real database engine / connection provider ------------------------------------------


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Function-scoped (not session-scoped): each async test runs in its own event loop
    (this project sets no session-scoped asyncio loop), and an `AsyncEngine`'s connection
    pool holds loop-bound asyncio primitives -- reusing one across event loops breaks it
    (verified empirically: "RuntimeError: Event loop is closed" from a later test trying
    to use a pool created in an earlier, now-closed, test's loop)."""
    db_engine = create_engine(settings)
    yield db_engine
    await db_engine.dispose()


@pytest.fixture
def connection_provider(engine: AsyncEngine) -> DatabaseConnectionProvider:
    return DatabaseConnectionProvider(engine)


# --- GeneratedSQL / SQLValidationResult builders (mirrors tests/sql_repair/conftest.py) --


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


def make_validation_result(
    generated_sql: GeneratedSQL,
    *,
    is_valid: bool = True,
    errors: tuple[ValidationIssue, ...] = (),
    warnings: tuple[ValidationIssue, ...] = (),
) -> SQLValidationResult:
    return SQLValidationResult(
        generated_sql=generated_sql,
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
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
            error_count=len(errors),
            warning_count=len(warnings),
        ),
    )


def make_issue(
    code: str,
    *,
    message: str | None = None,
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> ValidationIssue:
    return ValidationIssue(code=code, severity=severity, message=message or f"{code} occurred.")
