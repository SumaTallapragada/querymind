"""Tests for `querymind.result_formatter.engine.ResultFormatterEngine` — orchestration only."""

from __future__ import annotations

import pytest

from querymind.result_formatter.engine import ResultFormatterEngine
from querymind.result_formatter.exceptions import FormattingError
from querymind.result_formatter.models import AnswerType
from querymind.sql_execution import ExecutionError, ExecutionStatus

from .conftest import make_column, make_execution_result, make_query_result


class TestFormatSuccess:
    def test_a_scalar_query_produces_a_scalar_answer(self) -> None:
        query_result = make_query_result((make_column("total"),), ((2000,),))
        execution_result = make_execution_result(
            "SELECT COUNT(*) AS total FROM customers;", query_result
        )

        answer = ResultFormatterEngine().format(execution_result)

        assert answer.answer_type is AnswerType.SCALAR
        assert answer.execution_result is execution_result
        assert answer.formatted_table.rows[0].values[0].formatted_value == "2000"
        assert answer.summary.row_count == 1
        assert answer.statistics.rows_processed == 1
        assert answer.statistics.values_formatted == 1

    def test_an_empty_result_produces_an_empty_result_answer(self) -> None:
        query_result = make_query_result((make_column("customer_id"),), ())
        execution_result = make_execution_result(
            "SELECT customer_id FROM customers WHERE customer_id < 0;", query_result
        )

        answer = ResultFormatterEngine().format(execution_result)

        assert answer.answer_type is AnswerType.EMPTY_RESULT
        assert answer.summary.title == "No records found."
        assert answer.formatted_table.rows == ()

    def test_a_table_query_produces_a_table_answer(self) -> None:
        query_result = make_query_result(
            (make_column("customer_id"), make_column("first_name", python_type="str")),
            tuple((i, f"Name{i}") for i in range(10)),
        )
        execution_result = make_execution_result(
            "SELECT customer_id, first_name FROM customers ORDER BY customer_id LIMIT 10;",
            query_result,
        )

        answer = ResultFormatterEngine().format(execution_result)

        assert answer.answer_type is AnswerType.TABLE
        assert answer.statistics.rows_processed == 10
        assert answer.statistics.values_formatted == 20

    def test_execution_result_is_never_mutated(self) -> None:
        query_result = make_query_result((make_column("customer_id"),), ((1,),))
        execution_result = make_execution_result("SELECT customer_id FROM customers;", query_result)

        answer = ResultFormatterEngine().format(execution_result)

        assert answer.execution_result == execution_result
        assert answer.execution_result.query_result == execution_result.query_result


class TestFormatRejectsUnsuccessfulExecution:
    def test_a_failed_execution_result_raises_formatting_error(self) -> None:
        execution_result = make_execution_result("SELECT 1;", None, status=ExecutionStatus.FAILED)
        execution_result = execution_result.model_copy(
            update={"execution_error": ExecutionError(code="execution_failed", message="boom")}
        )
        with pytest.raises(FormattingError):
            ResultFormatterEngine().format(execution_result)

    def test_a_rejected_execution_result_raises_formatting_error(self) -> None:
        execution_result = make_execution_result(
            "DROP TABLE customers;", None, status=ExecutionStatus.REJECTED
        )
        with pytest.raises(FormattingError):
            ResultFormatterEngine().format(execution_result)

    def test_a_success_status_with_no_query_result_raises_formatting_error(self) -> None:
        # Should not be reachable through SQLExecutionEngine in practice, but the engine
        # must not silently proceed with a None query_result regardless.
        execution_result = make_execution_result("SELECT 1;", None, status=ExecutionStatus.SUCCESS)
        with pytest.raises(FormattingError):
            ResultFormatterEngine().format(execution_result)
