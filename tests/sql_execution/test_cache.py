"""Tests for `querymind.sql_execution.cache` — `NoOpSQLExecutionCache` is always a miss."""

from __future__ import annotations

from querymind.query_library.models import SQLDialect
from querymind.sql_execution.cache import NoOpSQLExecutionCache
from querymind.sql_execution.models import ExecutionStatistics, ExecutionStatus, SQLExecutionResult


def _result() -> SQLExecutionResult:
    return SQLExecutionResult(
        status=ExecutionStatus.SUCCESS,
        executed_sql="SELECT 1;",
        query_result=None,
        statistics=ExecutionStatistics(
            execution_latency_ms=1.0,
            rows_returned=0,
            columns_returned=0,
            database_name="querymind",
            dialect=SQLDialect.POSTGRESQL,
        ),
        execution_error=None,
    )


class TestNoOpSQLExecutionCache:
    def test_get_is_always_a_miss(self) -> None:
        cache = NoOpSQLExecutionCache()
        assert cache.get("any-key") is None

    def test_set_does_not_make_a_subsequent_get_a_hit(self) -> None:
        cache = NoOpSQLExecutionCache()
        cache.set("key", _result())
        assert cache.get("key") is None

    def test_clear_does_not_raise(self) -> None:
        NoOpSQLExecutionCache().clear()
