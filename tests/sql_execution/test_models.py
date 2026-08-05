"""Tests for `querymind.sql_execution.models` — immutability and validation constraints."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from querymind.query_library.models import SQLDialect
from querymind.sql_execution.models import (
    ExecutionError,
    ExecutionStatistics,
    ExecutionStatus,
    QueryColumn,
    QueryResult,
    QueryRow,
    SQLExecutionResult,
)


def _statistics(**overrides: object) -> ExecutionStatistics:
    defaults: dict[str, object] = {
        "execution_latency_ms": 1.5,
        "rows_returned": 0,
        "columns_returned": 0,
        "database_name": "querymind",
        "dialect": SQLDialect.POSTGRESQL,
    }
    defaults.update(overrides)
    return ExecutionStatistics(**defaults)  # type: ignore[arg-type]


class TestQueryModels:
    def test_query_column_is_frozen(self) -> None:
        column = QueryColumn(name="customer_id", database_type="bigint", python_type="int")
        with pytest.raises(ValidationError):
            column.name = "other"  # type: ignore[misc]

    def test_query_column_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            QueryColumn(  # type: ignore[call-arg]
                name="customer_id", database_type="bigint", python_type="int", extra_field=1
            )

    def test_query_row_values_is_a_tuple(self) -> None:
        row = QueryRow(values=(1, "Alice", None))
        assert row.values == (1, "Alice", None)
        with pytest.raises(ValidationError):
            row.values = (2,)  # type: ignore[misc]

    def test_query_result_row_count_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            QueryResult(columns=(), rows=(), row_count=-1)

    def test_query_result_holds_columns_and_rows(self) -> None:
        column = QueryColumn(name="customer_id", database_type="bigint", python_type="int")
        row = QueryRow(values=(1,))
        result = QueryResult(columns=(column,), rows=(row,), row_count=1)
        assert result.columns == (column,)
        assert result.rows == (row,)
        assert result.row_count == 1


class TestExecutionStatistics:
    def test_negative_latency_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _statistics(execution_latency_ms=-1.0)

    def test_negative_rows_returned_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _statistics(rows_returned=-1)


class TestSQLExecutionResult:
    def test_success_result_carries_a_query_result_and_no_error(self) -> None:
        column = QueryColumn(name="customer_id", database_type="bigint", python_type="int")
        row = QueryRow(values=(1,))
        query_result = QueryResult(columns=(column,), rows=(row,), row_count=1)
        result = SQLExecutionResult(
            status=ExecutionStatus.SUCCESS,
            executed_sql="SELECT customer_id FROM customers;",
            query_result=query_result,
            statistics=_statistics(rows_returned=1, columns_returned=1),
            execution_error=None,
        )
        assert result.status is ExecutionStatus.SUCCESS
        assert result.query_result is query_result
        assert result.execution_error is None

    def test_failure_result_carries_an_error_and_no_query_result(self) -> None:
        result = SQLExecutionResult(
            status=ExecutionStatus.REJECTED,
            executed_sql="DROP TABLE customers;",
            query_result=None,
            statistics=_statistics(),
            execution_error=ExecutionError(code="execution_rejected", message="Not read-only."),
        )
        assert result.status is ExecutionStatus.REJECTED
        assert result.query_result is None
        assert result.execution_error is not None
        assert result.execution_error.code == "execution_rejected"

    def test_is_frozen(self) -> None:
        result = SQLExecutionResult(
            status=ExecutionStatus.FAILED,
            executed_sql="SELECT 1;",
            query_result=None,
            statistics=_statistics(),
            execution_error=ExecutionError(code="execution_failed", message="boom"),
        )
        with pytest.raises(ValidationError):
            result.status = ExecutionStatus.SUCCESS  # type: ignore[misc]

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            SQLExecutionResult(  # type: ignore[call-arg]
                status=ExecutionStatus.SUCCESS,
                executed_sql="SELECT 1;",
                query_result=None,
                statistics=_statistics(),
                execution_error=None,
                unexpected="value",
            )
