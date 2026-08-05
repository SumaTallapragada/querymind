"""Tests for `querymind.sql_execution.engine.SQLExecutionEngine` — orchestration only.

Every collaborator (`ExecutionGuard`, `DatabaseConnectionProvider`,
`SQLExecutor`, `ResultFormatter`) is replaced with a small scripted fake
here, so each branch of `execute` (rejected/timeout/failed/formatting-
failed/success) can be exercised in isolation, deterministically, and
without touching a real database -- that end-to-end wiring is instead
covered by `test_integration.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from querymind.sql_execution.engine import SQLExecutionEngine
from querymind.sql_execution.exceptions import (
    DatabaseConnectionError,
    ExecutionFailureError,
    ExecutionRejectedError,
    ExecutionTimeoutError,
    ResultFormattingError,
)
from querymind.sql_execution.executor import RawQueryResult
from querymind.sql_execution.models import ExecutionStatus, QueryColumn, QueryResult, QueryRow
from querymind.sql_execution.validator import ExecutionPermit
from querymind.sql_repair.models import (
    RepairHistory,
    RepairStatistics,
    RepairStatus,
    SQLRepairResult,
)

from .conftest import make_generated_sql, make_validation_result

_SQL = "SELECT customer_id FROM customers;"


class _FakeGuard:
    def __init__(self, outcome: ExecutionPermit | ExecutionRejectedError) -> None:
        self._outcome = outcome

    def check(self, generated_sql: object, validation_result: object) -> ExecutionPermit:
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _FakeConnectionProvider:
    database_name = "querymind"

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[object]:
        yield object()


class _RaisingConnectionProvider:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.database_name = "querymind"

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[object]:
        raise self._error
        yield object()  # pragma: no cover -- unreachable, satisfies the generator protocol


class _FakeExecutor:
    def __init__(self, outcome: RawQueryResult | Exception) -> None:
        self._outcome = outcome

    async def execute(
        self, connection: object, sql: str, *, timeout_seconds: float, parameters: object = None
    ) -> RawQueryResult:
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _FakeFormatter:
    def __init__(self, outcome: QueryResult | Exception) -> None:
        self._outcome = outcome

    def format(self, raw: RawQueryResult) -> QueryResult:
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _raw_result() -> RawQueryResult:
    return RawQueryResult(
        column_names=("customer_id",),
        column_type_oids=(20,),
        rows=((1,),),
        execution_latency_ms=1.0,
    )


def _query_result() -> QueryResult:
    column = QueryColumn(name="customer_id", database_type="bigint", python_type="int")
    return QueryResult(columns=(column,), rows=(QueryRow(values=(1,)),), row_count=1)


def _build_engine(
    *,
    guard: _FakeGuard,
    connection_provider: _FakeConnectionProvider | _RaisingConnectionProvider | None = None,
    executor: _FakeExecutor | None = None,
    formatter: _FakeFormatter | None = None,
) -> SQLExecutionEngine:
    return SQLExecutionEngine(
        connection_provider=connection_provider or _FakeConnectionProvider(),  # type: ignore[arg-type]
        guard=guard,  # type: ignore[arg-type]
        executor=executor or _FakeExecutor(_raw_result()),  # type: ignore[arg-type]
        formatter=formatter or _FakeFormatter(_query_result()),  # type: ignore[arg-type]
    )


class TestExecuteRejected:
    async def test_a_guard_rejection_produces_a_rejected_result_with_no_query(self) -> None:
        engine = _build_engine(guard=_FakeGuard(ExecutionRejectedError("not read-only")))
        generated = make_generated_sql(_SQL)
        result = await engine.execute(generated, make_validation_result(generated))

        assert result.status is ExecutionStatus.REJECTED
        assert result.query_result is None
        assert result.execution_error is not None
        assert result.execution_error.message == "not read-only"
        assert result.executed_sql == _SQL


class TestExecuteTimeout:
    async def test_an_executor_timeout_produces_a_timeout_result(self) -> None:
        engine = _build_engine(
            guard=_FakeGuard(ExecutionPermit(sql=_SQL, timeout_seconds=1.0)),
            executor=_FakeExecutor(ExecutionTimeoutError("too slow")),
        )
        generated = make_generated_sql(_SQL)
        result = await engine.execute(generated, make_validation_result(generated))

        assert result.status is ExecutionStatus.TIMEOUT
        assert result.query_result is None
        assert result.execution_error is not None
        assert result.execution_error.code == "execution_timeout"


class TestExecuteFailed:
    async def test_a_connection_failure_produces_a_failed_result(self) -> None:
        engine = _build_engine(
            guard=_FakeGuard(ExecutionPermit(sql=_SQL, timeout_seconds=1.0)),
            connection_provider=_RaisingConnectionProvider(
                DatabaseConnectionError("cannot connect")
            ),
        )
        generated = make_generated_sql(_SQL)
        result = await engine.execute(generated, make_validation_result(generated))

        assert result.status is ExecutionStatus.FAILED
        assert result.execution_error is not None
        assert result.execution_error.code == "database_connection_error"

    async def test_an_execution_failure_produces_a_failed_result(self) -> None:
        engine = _build_engine(
            guard=_FakeGuard(ExecutionPermit(sql=_SQL, timeout_seconds=1.0)),
            executor=_FakeExecutor(ExecutionFailureError("syntax error")),
        )
        generated = make_generated_sql(_SQL)
        result = await engine.execute(generated, make_validation_result(generated))

        assert result.status is ExecutionStatus.FAILED
        assert result.execution_error is not None
        assert result.execution_error.code == "execution_failed"

    async def test_a_formatting_failure_produces_a_failed_result(self) -> None:
        engine = _build_engine(
            guard=_FakeGuard(ExecutionPermit(sql=_SQL, timeout_seconds=1.0)),
            formatter=_FakeFormatter(ResultFormattingError("mismatched columns")),
        )
        generated = make_generated_sql(_SQL)
        result = await engine.execute(generated, make_validation_result(generated))

        assert result.status is ExecutionStatus.FAILED
        assert result.execution_error is not None
        assert result.execution_error.code == "result_formatting_failed"


class TestExecuteSuccess:
    async def test_a_clean_run_produces_a_success_result_with_query_data(self) -> None:
        engine = _build_engine(guard=_FakeGuard(ExecutionPermit(sql=_SQL, timeout_seconds=1.0)))
        generated = make_generated_sql(_SQL)
        result = await engine.execute(generated, make_validation_result(generated))

        assert result.status is ExecutionStatus.SUCCESS
        assert result.execution_error is None
        assert result.query_result is not None
        assert result.query_result.row_count == 1
        assert result.statistics.rows_returned == 1
        assert result.statistics.columns_returned == 1
        assert result.statistics.database_name == "querymind"
        assert result.executed_sql == _SQL

    async def test_execution_latency_is_measured(self) -> None:
        engine = _build_engine(guard=_FakeGuard(ExecutionPermit(sql=_SQL, timeout_seconds=1.0)))
        generated = make_generated_sql(_SQL)
        result = await engine.execute(generated, make_validation_result(generated))
        assert result.statistics.execution_latency_ms >= 0.0


class TestExecuteRepairResult:
    async def test_delegates_to_execute_with_the_final_sql_and_validation_result(self) -> None:
        engine = _build_engine(guard=_FakeGuard(ExecutionPermit(sql=_SQL, timeout_seconds=1.0)))
        original = make_generated_sql("SELECT bad_column FROM customers;")
        final = make_generated_sql(_SQL)
        repair_result = SQLRepairResult(
            original_sql=original,
            final_sql=final,
            final_validation_result=make_validation_result(final),
            history=RepairHistory(attempts=()),
            statistics=RepairStatistics(
                attempt_count=0,
                successful_repairs=0,
                failed_repairs=0,
                repair_latency_ms=1.0,
                average_validation_latency_ms=1.0,
            ),
            status=RepairStatus.REPAIRED,
        )

        result = await engine.execute_repair_result(repair_result)

        assert result.status is ExecutionStatus.SUCCESS
        assert result.executed_sql == _SQL
