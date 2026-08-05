"""Tests for `querymind.result_formatter.cache` — `NoOpResultFormatterCache` is always a miss."""

from __future__ import annotations

from querymind.result_formatter.answer_generator import AnswerGenerator
from querymind.result_formatter.cache import NoOpResultFormatterCache
from querymind.result_formatter.formatter import ResultFormatter
from querymind.result_formatter.models import BusinessAnswer
from querymind.result_formatter.statistics import StatisticsBuilder
from querymind.result_formatter.summarizer import SummaryGenerator

from .conftest import make_column, make_execution_result, make_query_result


def _answer() -> BusinessAnswer:
    query_result = make_query_result((make_column("customer_id"),), ((1,),))
    execution_result = make_execution_result("SELECT customer_id FROM customers;", query_result)
    table = ResultFormatter().format(query_result)
    return BusinessAnswer(
        answer_type=AnswerGenerator().determine(execution_result, table),
        summary=SummaryGenerator().generate(table),
        formatted_table=table,
        statistics=StatisticsBuilder().build(table, 1.0),
        execution_result=execution_result,
    )


class TestNoOpResultFormatterCache:
    def test_get_is_always_a_miss(self) -> None:
        cache = NoOpResultFormatterCache()
        assert cache.get("any-key") is None

    def test_set_does_not_make_a_subsequent_get_a_hit(self) -> None:
        cache = NoOpResultFormatterCache()
        cache.set("key", _answer())
        assert cache.get("key") is None

    def test_clear_does_not_raise(self) -> None:
        NoOpResultFormatterCache().clear()
