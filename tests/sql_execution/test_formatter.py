"""Tests for `querymind.sql_execution.formatter.ResultFormatter`."""

from __future__ import annotations

import pytest

from querymind.sql_execution.exceptions import ResultFormattingError
from querymind.sql_execution.executor import RawQueryResult
from querymind.sql_execution.formatter import ResultFormatter


def _raw(**overrides: object) -> RawQueryResult:
    defaults: dict[str, object] = {
        "column_names": ("customer_id", "first_name"),
        "column_type_oids": (20, 1043),
        "rows": ((1, "Alice"), (2, "Bob")),
        "execution_latency_ms": 3.5,
    }
    defaults.update(overrides)
    return RawQueryResult(**defaults)  # type: ignore[arg-type]


class TestFormat:
    def test_known_oids_are_mapped_to_readable_types(self) -> None:
        query_result = ResultFormatter().format(_raw())
        assert query_result.columns[0].name == "customer_id"
        assert query_result.columns[0].database_type == "bigint"
        assert query_result.columns[0].python_type == "int"
        assert query_result.columns[1].database_type == "varchar"
        assert query_result.columns[1].python_type == "str"

    def test_an_unknown_oid_falls_back_to_its_numeric_string(self) -> None:
        query_result = ResultFormatter().format(
            _raw(column_names=("weird",), column_type_oids=(999999,), rows=((None,),))
        )
        assert query_result.columns[0].database_type == "oid:999999"
        assert query_result.columns[0].python_type == "object"

    def test_a_none_oid_falls_back_to_its_numeric_string(self) -> None:
        query_result = ResultFormatter().format(
            _raw(column_names=("weird",), column_type_oids=(None,), rows=((None,),))
        )
        assert query_result.columns[0].database_type == "oid:None"
        assert query_result.columns[0].python_type == "object"

    def test_rows_are_carried_through_unmodified(self) -> None:
        query_result = ResultFormatter().format(_raw())
        assert [row.values for row in query_result.rows] == [(1, "Alice"), (2, "Bob")]
        assert query_result.row_count == 2

    def test_zero_rows_still_reports_columns(self) -> None:
        query_result = ResultFormatter().format(_raw(rows=()))
        assert query_result.row_count == 0
        assert len(query_result.columns) == 2

    def test_nullable_is_always_none(self) -> None:
        query_result = ResultFormatter().format(_raw())
        assert all(column.nullable is None for column in query_result.columns)

    def test_mismatched_column_names_and_oids_raises_result_formatting_error(self) -> None:
        with pytest.raises(ResultFormattingError):
            ResultFormatter().format(_raw(column_names=("a", "b"), column_type_oids=(20,), rows=()))
