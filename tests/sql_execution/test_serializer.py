"""Tests for `querymind.sql_execution.serializer.SQLExecutionSerializer`."""

from __future__ import annotations

import json

import yaml

from querymind.query_library.models import SQLDialect
from querymind.sql_execution.models import (
    ExecutionStatistics,
    ExecutionStatus,
    QueryColumn,
    QueryResult,
    QueryRow,
    SQLExecutionResult,
)
from querymind.sql_execution.serializer import SQLExecutionSerializer


def _result() -> SQLExecutionResult:
    column = QueryColumn(name="customer_id", database_type="bigint", python_type="int")
    row = QueryRow(values=(1,))
    return SQLExecutionResult(
        status=ExecutionStatus.SUCCESS,
        executed_sql="SELECT customer_id FROM customers;",
        query_result=QueryResult(columns=(column,), rows=(row,), row_count=1),
        statistics=ExecutionStatistics(
            execution_latency_ms=2.5,
            rows_returned=1,
            columns_returned=1,
            database_name="querymind",
            dialect=SQLDialect.POSTGRESQL,
        ),
        execution_error=None,
    )


class TestToDict:
    def test_returns_json_safe_primitives(self) -> None:
        data = SQLExecutionSerializer.to_dict(_result())
        assert data["status"] == "success"
        assert data["query_result"]["rows"] == [{"values": [1]}]
        assert isinstance(data["query_result"]["columns"], list)


class TestToJson:
    def test_round_trips_through_json(self) -> None:
        text = SQLExecutionSerializer.to_json(_result())
        parsed = json.loads(text)
        assert parsed["status"] == "success"
        assert parsed["statistics"]["dialect"] == "postgresql"

    def test_indent_is_honored(self) -> None:
        text = SQLExecutionSerializer.to_json(_result(), indent=None)
        assert "\n" not in text


class TestToYaml:
    def test_round_trips_through_yaml(self) -> None:
        text = SQLExecutionSerializer.to_yaml(_result())
        parsed = yaml.safe_load(text)
        assert parsed["status"] == "success"
        assert parsed["executed_sql"] == "SELECT customer_id FROM customers;"
