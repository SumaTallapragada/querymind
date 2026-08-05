"""ResultFormatter: transforms a `QueryResult` into an immutable `FormattedTable`.

Responsibilities only: turn every raw row value into a `FormattedValue`
(delegating the actual per-value rendering to the constructor-injected
`ValueFormatter`) and carry columns through unmodified. No summaries, no
business explanations, no statistics -- those are `SummaryGenerator`'s
and `StatisticsBuilder`'s jobs respectively.
"""

from __future__ import annotations

from querymind.result_formatter.exceptions import FormattingError
from querymind.result_formatter.models import FormattedRow, FormattedTable
from querymind.result_formatter.value_formatter import ValueFormatter
from querymind.sql_execution import QueryResult


class ResultFormatter:
    """Formats a `QueryResult` into a `FormattedTable`. Formats only."""

    def __init__(self, value_formatter: ValueFormatter | None = None) -> None:
        self._value_formatter = value_formatter or ValueFormatter()

    def format(self, query_result: QueryResult) -> FormattedTable:
        """Convert `query_result` into a `FormattedTable`.

        Raises `FormattingError` if a row's value count doesn't match
        `query_result.columns` -- internally inconsistent input
        `SQLExecutor`/`ResultFormatter` (the `sql_execution` one)
        should never actually produce, but formatting is where it would
        surface rather than failing silently.
        """
        column_count = len(query_result.columns)
        rows: list[FormattedRow] = []
        for row in query_result.rows:
            if len(row.values) != column_count:
                raise FormattingError(
                    f"Row has {len(row.values)} values but there are {column_count} columns."
                )
            rows.append(
                FormattedRow(values=tuple(self._value_formatter.format(v) for v in row.values))
            )
        return FormattedTable(columns=query_result.columns, rows=tuple(rows))
