"""Tests for `querymind.result_formatter.summarizer.SummaryGenerator`."""

from __future__ import annotations

from datetime import date

from querymind.result_formatter.formatter import ResultFormatter
from querymind.result_formatter.summarizer import SummaryGenerator

from .conftest import make_column, make_query_result


class TestGenerate:
    def test_zero_rows(self) -> None:
        table = ResultFormatter().format(make_query_result((make_column("customer_id"),), ()))
        summary = SummaryGenerator().generate(table)
        assert summary.title == "No records found."
        assert summary.row_count == 0
        assert summary.column_count == 1

    def test_one_row_one_column(self) -> None:
        table = ResultFormatter().format(make_query_result((make_column("total"),), ((42,),)))
        summary = SummaryGenerator().generate(table)
        assert summary.title == "Returned one record."
        assert "total" in summary.description
        assert summary.row_count == 1
        assert summary.column_count == 1

    def test_one_row_multiple_columns(self) -> None:
        table = ResultFormatter().format(
            make_query_result(
                (make_column("customer_id"), make_column("first_name", python_type="str")),
                ((1, "Alice"),),
            )
        )
        summary = SummaryGenerator().generate(table)
        assert summary.title == "Returned one record."
        assert "customer_id" in summary.description
        assert "first_name" in summary.description

    def test_many_rows(self) -> None:
        table = ResultFormatter().format(
            make_query_result((make_column("customer_id"),), tuple((i,) for i in range(154)))
        )
        summary = SummaryGenerator().generate(table)
        assert summary.title == "Returned 154 rows."
        assert summary.row_count == 154

    def test_contains_numeric_is_true_for_a_numeric_column(self) -> None:
        table = ResultFormatter().format(
            make_query_result((make_column("total", python_type="float"),), ((1.5,),))
        )
        summary = SummaryGenerator().generate(table)
        assert summary.contains_numeric is True
        assert summary.contains_dates is False

    def test_contains_dates_is_true_for_a_temporal_column(self) -> None:
        table = ResultFormatter().format(
            make_query_result(
                (make_column("created_at", database_type="date", python_type="date"),),
                ((date(2026, 1, 1),),),
            )
        )
        summary = SummaryGenerator().generate(table)
        assert summary.contains_dates is True
        assert summary.contains_numeric is False

    def test_neither_numeric_nor_dates_for_a_plain_string_column(self) -> None:
        table = ResultFormatter().format(
            make_query_result((make_column("name", python_type="str"),), (("Alice",),))
        )
        summary = SummaryGenerator().generate(table)
        assert summary.contains_numeric is False
        assert summary.contains_dates is False

    def test_never_infers_business_meaning_from_column_names(self) -> None:
        # A "region"/"revenue" pair must not produce a hallucinated "by region" phrase --
        # only the literal column names may appear.
        table = ResultFormatter().format(
            make_query_result(
                (
                    make_column("region", python_type="str"),
                    make_column("revenue", python_type="float"),
                ),
                (("West", 1000.0),),
            )
        )
        summary = SummaryGenerator().generate(table)
        assert "by region" not in summary.description.lower()
        assert "region" in summary.description
        assert "revenue" in summary.description
