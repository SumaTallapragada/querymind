"""Tests for `querymind.result_formatter.statistics.StatisticsBuilder`."""

from __future__ import annotations

from querymind.result_formatter.formatter import ResultFormatter
from querymind.result_formatter.statistics import StatisticsBuilder

from .conftest import make_column, make_query_result


class TestBuild:
    def test_counts_match_the_formatted_table(self) -> None:
        table = ResultFormatter().format(
            make_query_result(
                (make_column("a"), make_column("b")),
                ((1, 2), (3, 4), (5, 6)),
            )
        )
        stats = StatisticsBuilder().build(table, 12.5)
        assert stats.rows_processed == 3
        assert stats.columns_processed == 2
        assert stats.values_formatted == 6
        assert stats.formatting_latency_ms == 12.5

    def test_zero_rows_still_reports_columns_processed(self) -> None:
        table = ResultFormatter().format(make_query_result((make_column("a"),), ()))
        stats = StatisticsBuilder().build(table, 1.0)
        assert stats.rows_processed == 0
        assert stats.columns_processed == 1
        assert stats.values_formatted == 0
