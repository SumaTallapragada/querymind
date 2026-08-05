"""End-to-end tests against the real, fully wired execution stack.

Wires `SQLExecutionEngine` on top of a real `DatabaseConnectionProvider`
(the same `Settings`/`create_engine` the application itself uses) and its
own real `ExecutionGuard`/`SQLExecutor`/`ResultFormatter` -- no mocks,
no fakes -- run against the real, already-running local Postgres
instance with its real seeded `customers`/`orders`/`suppliers` data,
mirroring `tests/sql_repair/test_integration.py`'s "real components,
real data" precedent.
"""

from __future__ import annotations

from querymind.query_library.models import SQLDialect
from querymind.sql_execution.connection import DatabaseConnectionProvider
from querymind.sql_execution.engine import SQLExecutionEngine
from querymind.sql_execution.models import ExecutionStatus

from .conftest import make_generated_sql, make_validation_result


class TestSuccessfulExecution:
    async def test_a_real_select_against_the_real_seeded_database_succeeds(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        engine = SQLExecutionEngine(connection_provider)
        generated = make_generated_sql(
            "SELECT customer_id, first_name FROM customers ORDER BY customer_id LIMIT 5;"
        )
        result = await engine.execute(generated, make_validation_result(generated))

        assert result.status is ExecutionStatus.SUCCESS
        assert result.execution_error is None
        assert result.query_result is not None
        assert result.query_result.row_count == 5
        assert [c.name for c in result.query_result.columns] == ["customer_id", "first_name"]
        assert result.statistics.database_name == "querymind"
        assert result.statistics.dialect is SQLDialect.POSTGRESQL

    async def test_a_with_select_cte_succeeds(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        engine = SQLExecutionEngine(connection_provider)
        generated = make_generated_sql(
            "WITH active AS (SELECT customer_id FROM customers WHERE is_active = true) "
            "SELECT COUNT(*) AS active_count FROM active;"
        )
        result = await engine.execute(generated, make_validation_result(generated))

        assert result.status is ExecutionStatus.SUCCESS
        assert result.query_result is not None
        assert result.query_result.row_count == 1


class TestRejectedExecution:
    async def test_a_failed_validation_result_never_reaches_the_database(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        engine = SQLExecutionEngine(connection_provider)
        generated = make_generated_sql("SELECT customer_id FROM customers;")
        validation = make_validation_result(generated, is_valid=False)
        result = await engine.execute(generated, validation)

        assert result.status is ExecutionStatus.REJECTED
        assert result.query_result is None

    async def test_a_write_hidden_in_a_writable_cte_is_rejected_before_touching_the_database(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        engine = SQLExecutionEngine(connection_provider)
        generated = make_generated_sql(
            "WITH deactivated AS (UPDATE customers SET is_active = false "
            "WHERE customer_id = -1 RETURNING customer_id) SELECT * FROM deactivated;"
        )
        result = await engine.execute(generated, make_validation_result(generated))

        assert result.status is ExecutionStatus.REJECTED
        assert result.query_result is None


class TestFailedExecution:
    async def test_a_query_against_a_nonexistent_table_produces_a_failed_result(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        engine = SQLExecutionEngine(connection_provider)
        generated = make_generated_sql("SELECT * FROM this_table_does_not_exist;")
        result = await engine.execute(generated, make_validation_result(generated))

        assert result.status is ExecutionStatus.FAILED
        assert result.execution_error is not None
        assert result.execution_error.code == "execution_failed"
