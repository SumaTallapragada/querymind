"""Tests for `querymind.result_formatter.formatter.ResultFormatter`."""

from __future__ import annotations

import pytest

from querymind.result_formatter.exceptions import FormattingError
from querymind.result_formatter.formatter import ResultFormatter
from querymind.result_formatter.models import FormattedValue
from querymind.sql_execution import QueryColumn, QueryResult, QueryRow

from .conftest import make_column, make_query_result


class TestFormat:
    def test_produces_a_row_per_input_row(self) -> None:
        query_result = make_query_result(
            (make_column("customer_id"), make_column("first_name", python_type="str")),
            ((1, "Alice"), (2, "Bob")),
        )
        table = ResultFormatter().format(query_result)
        assert len(table.rows) == 2
        assert [v.formatted_value for v in table.rows[0].values] == ["1", "Alice"]
        assert [v.formatted_value for v in table.rows[1].values] == ["2", "Bob"]

    def test_columns_are_carried_through_unmodified(self) -> None:
        column = make_column("customer_id")
        query_result = make_query_result((column,), ((1,),))
        table = ResultFormatter().format(query_result)
        assert table.columns == (column,)

    def test_zero_rows_produces_an_empty_rows_tuple(self) -> None:
        query_result = make_query_result((make_column("customer_id"),), ())
        table = ResultFormatter().format(query_result)
        assert table.rows == ()
        assert len(table.columns) == 1

    def test_uses_the_injected_value_formatter(self) -> None:
        class _UppercaseFormatter:
            def format(self, value: object) -> FormattedValue:
                return FormattedValue(
                    original_value=value, formatted_value=str(value).upper(), detected_type="str"
                )

        query_result = make_query_result((make_column("name", python_type="str"),), (("alice",),))
        table = ResultFormatter(value_formatter=_UppercaseFormatter()).format(query_result)  # type: ignore[arg-type]
        assert table.rows[0].values[0].formatted_value == "ALICE"

    def test_mismatched_row_length_raises_formatting_error(self) -> None:
        columns = (make_column("a"), make_column("b"))
        # Bypass make_query_result's own row/column pairing to construct an intentionally
        # inconsistent QueryResult, matching the shape ResultFormatter must guard against.
        query_result = QueryResult(columns=columns, rows=(QueryRow(values=(1,)),), row_count=1)
        with pytest.raises(FormattingError):
            ResultFormatter().format(query_result)

    def test_a_column_with_no_rows_is_still_a_valid_empty_table(self) -> None:
        query_result = QueryResult(columns=(), rows=(), row_count=0)
        table = ResultFormatter().format(query_result)
        assert table.columns == ()
        assert table.rows == ()


def test_query_column_reuse_sanity() -> None:
    # Documents the "reuse, don't duplicate" decision: FormattedTable.columns really is
    # querymind.sql_execution.QueryColumn, not a re-declared lookalike.
    column = make_column("customer_id")
    assert isinstance(column, QueryColumn)
