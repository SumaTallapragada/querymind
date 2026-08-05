"""Tests for `querymind.sql_execution.validator.ExecutionGuard` — the final safety gate.

Includes the two gaps `ExecutionGuard` was specifically written to close
(see `validator.py`'s module docstring): multi-statement smuggling via
`sqlglot.parse_one`'s silent truncation, and a write hidden inside a
PostgreSQL writable CTE.
"""

from __future__ import annotations

import pytest

from querymind.sql_execution.exceptions import (
    ExecutionRejectedError,
    SQLExecutionConfigurationError,
)
from querymind.sql_execution.validator import DEFAULT_EXECUTION_TIMEOUT_SECONDS, ExecutionGuard

from .conftest import make_generated_sql, make_issue, make_validation_result


class TestConstruction:
    def test_default_timeout_is_used_when_not_given(self) -> None:
        guard = ExecutionGuard()
        assert guard.timeout_seconds == DEFAULT_EXECUTION_TIMEOUT_SECONDS

    def test_custom_timeout_is_honored(self) -> None:
        guard = ExecutionGuard(timeout_seconds=5.0)
        assert guard.timeout_seconds == 5.0

    @pytest.mark.parametrize("bad_timeout", [0.0, -1.0])
    def test_non_positive_timeout_is_rejected(self, bad_timeout: float) -> None:
        with pytest.raises(SQLExecutionConfigurationError):
            ExecutionGuard(timeout_seconds=bad_timeout)


class TestPermittedStatements:
    def test_a_plain_select_is_permitted(self) -> None:
        guard = ExecutionGuard(timeout_seconds=12.0)
        generated = make_generated_sql("SELECT customer_id FROM customers;")
        permit = guard.check(generated, make_validation_result(generated))
        assert permit.sql == "SELECT customer_id FROM customers;"
        assert permit.timeout_seconds == 12.0

    def test_a_with_select_cte_is_permitted(self) -> None:
        guard = ExecutionGuard()
        sql = "WITH recent AS (SELECT customer_id FROM customers) " "SELECT * FROM recent;"
        generated = make_generated_sql(sql)
        permit = guard.check(generated, make_validation_result(generated))
        assert permit.sql == sql


class TestRejectedByValidation:
    def test_a_failed_validation_result_is_rejected(self) -> None:
        guard = ExecutionGuard()
        generated = make_generated_sql("SELECT customer_id FROM customers;")
        validation = make_validation_result(
            generated, is_valid=False, errors=(make_issue("unknown_table"),)
        )
        with pytest.raises(ExecutionRejectedError):
            guard.check(generated, validation)


class TestRejectedByEmptiness:
    @pytest.mark.parametrize("sql", ["   ", "\n\t"])
    def test_blank_sql_is_rejected(self, sql: str) -> None:
        # `GeneratedSQL.sql` itself enforces `min_length=1`, so only whitespace-only
        # (non-empty but blank after `.strip()`) values reach ExecutionGuard's own check.
        guard = ExecutionGuard()
        generated = make_generated_sql(sql)
        with pytest.raises(ExecutionRejectedError):
            guard.check(generated, make_validation_result(generated))


class TestRejectedByStatementType:
    @pytest.mark.parametrize(
        "sql",
        [
            "DELETE FROM customers;",
            "UPDATE customers SET is_active = false;",
            "INSERT INTO customers (customer_id) VALUES (1);",
            "DROP TABLE customers;",
            "TRUNCATE TABLE customers;",
        ],
    )
    def test_non_select_statements_are_rejected(self, sql: str) -> None:
        guard = ExecutionGuard()
        generated = make_generated_sql(sql)
        with pytest.raises(ExecutionRejectedError):
            guard.check(generated, make_validation_result(generated))


class TestRejectedByMultiStatementSmuggling:
    def test_a_second_statement_smuggled_after_a_select_is_rejected(self) -> None:
        """`sqlglot.parse_one` would silently drop the second statement -- this must not."""
        guard = ExecutionGuard()
        sql = "SELECT 1; DROP TABLE customers;"
        generated = make_generated_sql(sql)
        with pytest.raises(ExecutionRejectedError):
            guard.check(generated, make_validation_result(generated))


class TestRejectedByWritableCTE:
    def test_a_delete_hidden_inside_a_with_clause_is_rejected(self) -> None:
        """Root node is `exp.Select`; a naive root-type check alone would pass this."""
        guard = ExecutionGuard()
        sql = (
            "WITH deleted AS (DELETE FROM customers RETURNING customer_id) "
            "SELECT * FROM deleted;"
        )
        generated = make_generated_sql(sql)
        with pytest.raises(ExecutionRejectedError):
            guard.check(generated, make_validation_result(generated))

    def test_an_insert_hidden_inside_a_with_clause_is_rejected(self) -> None:
        guard = ExecutionGuard()
        sql = (
            "WITH inserted AS (INSERT INTO customers (customer_id) VALUES (999) "
            "RETURNING customer_id) SELECT * FROM inserted;"
        )
        generated = make_generated_sql(sql)
        with pytest.raises(ExecutionRejectedError):
            guard.check(generated, make_validation_result(generated))
