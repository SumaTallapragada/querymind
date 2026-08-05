"""Tests for `querymind.result_formatter.models` — immutability and validation constraints."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from querymind.result_formatter.models import (
    AnswerStatistics,
    AnswerSummary,
    AnswerType,
    BusinessAnswer,
    FormattedRow,
    FormattedTable,
    FormattedValue,
)

from .conftest import make_column, make_execution_result, make_query_result


def _summary(**overrides: object) -> AnswerSummary:
    defaults: dict[str, object] = {
        "title": "Returned 1 rows.",
        "description": "Returned 1 rows across 1 columns: customer_id.",
        "row_count": 1,
        "column_count": 1,
        "contains_numeric": True,
        "contains_dates": False,
    }
    defaults.update(overrides)
    return AnswerSummary(**defaults)  # type: ignore[arg-type]


def _statistics(**overrides: object) -> AnswerStatistics:
    defaults: dict[str, object] = {
        "formatting_latency_ms": 1.0,
        "rows_processed": 1,
        "columns_processed": 1,
        "values_formatted": 1,
    }
    defaults.update(overrides)
    return AnswerStatistics(**defaults)  # type: ignore[arg-type]


class TestFormattedValue:
    def test_is_frozen(self) -> None:
        value = FormattedValue(original_value=1, formatted_value="1", detected_type="int")
        with pytest.raises(ValidationError):
            value.formatted_value = "2"  # type: ignore[misc]

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            FormattedValue(  # type: ignore[call-arg]
                original_value=1, formatted_value="1", detected_type="int", extra="x"
            )


class TestFormattedRowAndTable:
    def test_row_values_is_a_tuple(self) -> None:
        row = FormattedRow(
            values=(FormattedValue(original_value=1, formatted_value="1", detected_type="int"),)
        )
        assert isinstance(row.values, tuple)

    def test_table_holds_columns_and_rows(self) -> None:
        column = make_column("customer_id")
        row = FormattedRow(
            values=(FormattedValue(original_value=1, formatted_value="1", detected_type="int"),)
        )
        table = FormattedTable(columns=(column,), rows=(row,))
        assert table.columns == (column,)
        assert table.rows == (row,)


class TestAnswerSummary:
    def test_row_count_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            _summary(row_count=-1)

    def test_column_count_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            _summary(column_count=-1)


class TestAnswerStatistics:
    def test_negative_latency_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _statistics(formatting_latency_ms=-1.0)

    def test_negative_values_formatted_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _statistics(values_formatted=-1)


class TestBusinessAnswer:
    def test_is_frozen(self) -> None:
        column = make_column("customer_id")
        table = FormattedTable(
            columns=(column,),
            rows=(
                FormattedRow(
                    values=(
                        FormattedValue(original_value=1, formatted_value="1", detected_type="int"),
                    )
                ),
            ),
        )
        query_result = make_query_result((column,), ((1,),))
        execution_result = make_execution_result("SELECT customer_id FROM customers;", query_result)
        answer = BusinessAnswer(
            answer_type=AnswerType.SCALAR,
            summary=_summary(),
            formatted_table=table,
            statistics=_statistics(),
            execution_result=execution_result,
        )
        with pytest.raises(ValidationError):
            answer.answer_type = AnswerType.TABLE  # type: ignore[misc]

    def test_rejects_unknown_fields(self) -> None:
        column = make_column("customer_id")
        table = FormattedTable(columns=(column,), rows=())
        query_result = make_query_result((column,), ())
        execution_result = make_execution_result("SELECT customer_id FROM customers;", query_result)
        with pytest.raises(ValidationError):
            BusinessAnswer(  # type: ignore[call-arg]
                answer_type=AnswerType.EMPTY_RESULT,
                summary=_summary(row_count=0),
                formatted_table=table,
                statistics=_statistics(rows_processed=0, values_formatted=0),
                execution_result=execution_result,
                unexpected="value",
            )


class TestAnswerType:
    def test_has_the_five_required_members(self) -> None:
        assert {member.value for member in AnswerType} == {
            "scalar",
            "table",
            "empty_result",
            "aggregation",
            "detail",
        }
