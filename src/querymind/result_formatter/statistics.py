"""StatisticsBuilder: observability data about one formatting run.

Derives every count from the `FormattedTable` itself -- rows processed,
columns processed, values formatted -- rather than having `ResultFormatter`
track counters separately, so there is exactly one source of truth for
"what was formatted."
"""

from __future__ import annotations

from querymind.result_formatter.models import AnswerStatistics, FormattedTable


class StatisticsBuilder:
    """Builds an `AnswerStatistics` from a `FormattedTable` and a measured latency."""

    def build(
        self, formatted_table: FormattedTable, formatting_latency_ms: float
    ) -> AnswerStatistics:
        rows_processed = len(formatted_table.rows)
        columns_processed = len(formatted_table.columns)
        values_formatted = sum(len(row.values) for row in formatted_table.rows)
        return AnswerStatistics(
            formatting_latency_ms=formatting_latency_ms,
            rows_processed=rows_processed,
            columns_processed=columns_processed,
            values_formatted=values_formatted,
        )
