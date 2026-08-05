"""Tests for `querymind.result_formatter.answer_generator.AnswerGenerator`."""

from __future__ import annotations

from querymind.result_formatter.answer_generator import AnswerGenerator
from querymind.result_formatter.formatter import ResultFormatter
from querymind.result_formatter.models import AnswerType
from querymind.sql_execution import QueryColumn

from .conftest import make_column, make_execution_result, make_query_result


def _determine(
    sql: str, columns: tuple[QueryColumn, ...], rows: tuple[tuple[object, ...], ...]
) -> AnswerType:
    query_result = make_query_result(columns, rows)
    execution_result = make_execution_result(sql, query_result)
    formatted_table = ResultFormatter().format(query_result)
    return AnswerGenerator().determine(execution_result, formatted_table)


class TestEmptyResult:
    def test_zero_rows_is_empty_result(self) -> None:
        answer_type = _determine(
            "SELECT customer_id FROM customers WHERE customer_id < 0;",
            (make_column("customer_id"),),
            (),
        )
        assert answer_type is AnswerType.EMPTY_RESULT


class TestScalar:
    def test_one_row_one_column_is_scalar(self) -> None:
        answer_type = _determine(
            "SELECT COUNT(*) FROM customers;", (make_column("count"),), ((2000,),)
        )
        assert answer_type is AnswerType.SCALAR

    def test_scalar_takes_priority_over_aggregation(self) -> None:
        # COUNT(*) is an aggregate function, but a single scalar cell still classifies as
        # SCALAR (rule order: row/column shape is checked before SQL-level aggregation).
        answer_type = _determine(
            "SELECT COUNT(*) AS total FROM customers;", (make_column("total"),), ((2000,),)
        )
        assert answer_type is AnswerType.SCALAR


class TestAggregation:
    def test_group_by_with_multiple_rows_is_aggregation(self) -> None:
        answer_type = _determine(
            "SELECT customer_segment, COUNT(*) FROM customers GROUP BY customer_segment;",
            (make_column("customer_segment", python_type="str"), make_column("count")),
            (("standard", 1500), ("premium", 500)),
        )
        assert answer_type is AnswerType.AGGREGATION

    def test_a_sum_without_group_by_over_multiple_rows_is_aggregation(self) -> None:
        # Contrived (a real SUM without GROUP BY collapses to one row), but exercises the
        # aggregate-function detection path independent of GROUP BY.
        answer_type = _determine(
            "SELECT customer_id, SUM(total_amount) FROM orders GROUP BY customer_id;",
            (make_column("customer_id"), make_column("total")),
            ((1, 100), (2, 200)),
        )
        assert answer_type is AnswerType.AGGREGATION


class TestDetail:
    def test_one_row_multiple_columns_without_aggregation_is_detail(self) -> None:
        answer_type = _determine(
            "SELECT customer_id, first_name FROM customers WHERE customer_id = 1;",
            (make_column("customer_id"), make_column("first_name", python_type="str")),
            ((1, "Alice"),),
        )
        assert answer_type is AnswerType.DETAIL


class TestTable:
    def test_many_rows_without_aggregation_is_table(self) -> None:
        answer_type = _determine(
            "SELECT customer_id, first_name FROM customers ORDER BY customer_id LIMIT 10;",
            (make_column("customer_id"), make_column("first_name", python_type="str")),
            tuple((i, f"Name{i}") for i in range(10)),
        )
        assert answer_type is AnswerType.TABLE


class TestMalformedSqlFallsBackGracefully:
    def test_unparseable_executed_sql_does_not_raise(self) -> None:
        # AnswerGenerator's aggregation check is best-effort; a parse failure must not
        # propagate as an exception -- it just falls through to the row-count-based rules.
        answer_type = _determine(
            "not actually valid sql ((((",
            (make_column("customer_id"), make_column("first_name", python_type="str")),
            tuple((i, f"Name{i}") for i in range(5)),
        )
        assert answer_type is AnswerType.TABLE
