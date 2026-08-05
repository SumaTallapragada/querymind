"""SummaryGenerator: a concise, deterministic summary of a `FormattedTable`.

Built strictly from what `FormattedTable`/`SQLExecutionResult` already
contain -- row count, column count, column names, column python_types --
never from inferred business meaning (e.g. never guesses that a
`region`/`revenue` pair means "revenue by region"; that would be
interpreting the *content*, not reporting the *shape*, of the result).
"""

from __future__ import annotations

from querymind.result_formatter.models import AnswerSummary, FormattedTable

_NUMERIC_PYTHON_TYPES = frozenset({"int", "float", "Decimal"})
_TEMPORAL_PYTHON_TYPES = frozenset({"date", "datetime"})


class SummaryGenerator:
    """Generates an `AnswerSummary` from a `FormattedTable`. Never raises for valid input."""

    def generate(self, formatted_table: FormattedTable) -> AnswerSummary:
        row_count = len(formatted_table.rows)
        column_count = len(formatted_table.columns)
        contains_numeric = any(
            column.python_type in _NUMERIC_PYTHON_TYPES for column in formatted_table.columns
        )
        contains_dates = any(
            column.python_type in _TEMPORAL_PYTHON_TYPES for column in formatted_table.columns
        )

        title, description = self._text(row_count, column_count, formatted_table)

        return AnswerSummary(
            title=title,
            description=description,
            row_count=row_count,
            column_count=column_count,
            contains_numeric=contains_numeric,
            contains_dates=contains_dates,
        )

    @staticmethod
    def _text(
        row_count: int, column_count: int, formatted_table: FormattedTable
    ) -> tuple[str, str]:
        if row_count == 0:
            return "No records found.", "The query returned no records."

        if row_count == 1 and column_count == 1:
            column_name = formatted_table.columns[0].name
            return "Returned one record.", f"Returned a single value from column '{column_name}'."

        column_names = ", ".join(column.name for column in formatted_table.columns)
        if row_count == 1:
            return (
                "Returned one record.",
                f"Returned one record with {column_count} columns: {column_names}.",
            )

        return (
            f"Returned {row_count} rows.",
            f"Returned {row_count} rows across {column_count} columns: {column_names}.",
        )
