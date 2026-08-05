"""Tests for `querymind.sql_execution.executor.SQLExecutor`.

Runs real SQL against the real, already-running local Postgres instance
(via `connection_provider` from `conftest.py`) -- executing, timing out,
and failing are all genuinely database-level behaviors not worth faking.
"""

from __future__ import annotations

import pytest

from querymind.sql_execution.connection import DatabaseConnectionProvider
from querymind.sql_execution.exceptions import ExecutionFailureError, ExecutionTimeoutError
from querymind.sql_execution.executor import SQLExecutor


class TestExecute:
    async def test_a_real_select_returns_column_names_and_rows(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        executor = SQLExecutor()
        async with connection_provider.acquire() as connection:
            raw = await executor.execute(
                connection,
                "SELECT customer_id, first_name FROM customers ORDER BY customer_id LIMIT 3;",
                timeout_seconds=10.0,
            )
        assert raw.column_names == ("customer_id", "first_name")
        assert len(raw.rows) == 3
        assert raw.column_type_oids[0] is not None
        assert raw.execution_latency_ms >= 0.0

    async def test_a_query_with_no_rows_still_reports_columns(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        executor = SQLExecutor()
        async with connection_provider.acquire() as connection:
            raw = await executor.execute(
                connection,
                "SELECT customer_id FROM customers WHERE customer_id < 0;",
                timeout_seconds=10.0,
            )
        assert raw.column_names == ("customer_id",)
        assert raw.rows == ()

    async def test_exceeding_the_timeout_raises_execution_timeout_error(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        executor = SQLExecutor()
        async with connection_provider.acquire() as connection:
            with pytest.raises(ExecutionTimeoutError):
                await executor.execute(connection, "SELECT pg_sleep(2);", timeout_seconds=0.1)

    async def test_a_database_error_raises_execution_failure_error(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        executor = SQLExecutor()
        async with connection_provider.acquire() as connection:
            with pytest.raises(ExecutionFailureError):
                await executor.execute(
                    connection, "SELECT * FROM this_table_does_not_exist;", timeout_seconds=10.0
                )
