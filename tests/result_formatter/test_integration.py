"""End-to-end tests against a real `SQLExecutionResult`.

Wires the real, already-verified `querymind.sql_execution.SQLExecutionEngine`
against the real, already-running local Postgres instance (same
`Settings`/`create_engine` precedent as `tests/sql_execution/
test_integration.py`) to produce a genuine `SQLExecutionResult`, then
feeds it through the real `ResultFormatterEngine` -- no fakes anywhere
in this file.
"""

from __future__ import annotations

from querymind.result_formatter.engine import ResultFormatterEngine
from querymind.result_formatter.models import AnswerType
from querymind.sql_execution import DatabaseConnectionProvider, ExecutionStatus, SQLExecutionEngine

from .conftest import make_generated_sql, make_validation_result


class TestRealScalarQuery:
    async def test_a_count_query_produces_a_scalar_answer(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        generated = make_generated_sql("SELECT COUNT(*) AS total FROM customers;")
        execution_result = await SQLExecutionEngine(connection_provider).execute(
            generated, make_validation_result(generated)
        )
        assert execution_result.status is ExecutionStatus.SUCCESS

        answer = ResultFormatterEngine().format(execution_result)

        assert answer.answer_type is AnswerType.SCALAR
        assert answer.formatted_table.rows[0].values[0].detected_type == "int"
        assert answer.execution_result is execution_result


class TestRealTableQuery:
    async def test_a_multi_row_select_produces_a_table_answer(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        generated = make_generated_sql(
            "SELECT customer_id, first_name FROM customers ORDER BY customer_id LIMIT 5;"
        )
        execution_result = await SQLExecutionEngine(connection_provider).execute(
            generated, make_validation_result(generated)
        )

        answer = ResultFormatterEngine().format(execution_result)

        assert answer.answer_type is AnswerType.TABLE
        assert answer.summary.row_count == 5
        assert answer.statistics.rows_processed == 5
        assert answer.statistics.columns_processed == 2


class TestRealEmptyQuery:
    async def test_a_query_matching_nothing_produces_an_empty_result_answer(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        generated = make_generated_sql("SELECT customer_id FROM customers WHERE customer_id < 0;")
        execution_result = await SQLExecutionEngine(connection_provider).execute(
            generated, make_validation_result(generated)
        )

        answer = ResultFormatterEngine().format(execution_result)

        assert answer.answer_type is AnswerType.EMPTY_RESULT
        assert answer.summary.title == "No records found."


class TestRealAggregationQuery:
    async def test_a_group_by_query_produces_an_aggregation_answer(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        generated = make_generated_sql(
            "SELECT customer_segment, COUNT(*) AS segment_count FROM customers "
            "GROUP BY customer_segment;"
        )
        execution_result = await SQLExecutionEngine(connection_provider).execute(
            generated, make_validation_result(generated)
        )

        answer = ResultFormatterEngine().format(execution_result)

        assert answer.answer_type is AnswerType.AGGREGATION
        assert answer.summary.contains_numeric is True


class TestRealDetailQuery:
    async def test_a_single_row_multi_column_select_produces_a_detail_answer(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        generated = make_generated_sql(
            "SELECT customer_id, first_name, customer_segment FROM customers "
            "ORDER BY customer_id LIMIT 1;"
        )
        execution_result = await SQLExecutionEngine(connection_provider).execute(
            generated, make_validation_result(generated)
        )

        answer = ResultFormatterEngine().format(execution_result)

        assert answer.answer_type is AnswerType.DETAIL
        assert answer.summary.row_count == 1
        assert answer.summary.column_count == 3
