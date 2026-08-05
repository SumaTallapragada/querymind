"""The Result Formatter Engine: turns a successful `SQLExecutionResult` into a `BusinessAnswer`.

`ResultFormatterEngine` is the single public entry point for this
package. It orchestrates *only* -- every actual piece of work is
delegated to a dedicated, single-responsibility, constructor-injected
collaborator: `ResultFormatter` builds the `FormattedTable`,
`SummaryGenerator` builds the `AnswerSummary`, `AnswerGenerator`
determines the `AnswerType`, and `StatisticsBuilder` builds the
`AnswerStatistics`. The engine never formats a value itself, never
writes summary text itself, and never inspects SQL itself.

This phase starts only after successful SQL execution: `format` raises
`FormattingError` immediately if `execution_result.status` is not
`SUCCESS` or `execution_result.query_result` is `None` -- it is the
caller's responsibility to only invoke this phase once
`SQLExecutionResult.status is ExecutionStatus.SUCCESS`, exactly as the
phase pipeline (`SQLExecutionResult -> ResultFormatter -> ... ->
BusinessAnswer`) describes. Unlike `SQLExecutionEngine.execute`, this
method does not catch its own domain exceptions -- see
`querymind.result_formatter.exceptions` for why.
"""

from __future__ import annotations

import time

from querymind.result_formatter.answer_generator import AnswerGenerator
from querymind.result_formatter.exceptions import FormattingError
from querymind.result_formatter.formatter import ResultFormatter
from querymind.result_formatter.models import BusinessAnswer
from querymind.result_formatter.statistics import StatisticsBuilder
from querymind.result_formatter.summarizer import SummaryGenerator
from querymind.sql_execution import ExecutionStatus, SQLExecutionResult


class ResultFormatterEngine:
    """Formats a successful `SQLExecutionResult` into a `BusinessAnswer`.

    Every collaborator is constructor-injected with a sensible default,
    so a caller can swap in a different formatter, summarizer, answer
    generator, or statistics builder without touching this class.
    """

    def __init__(
        self,
        result_formatter: ResultFormatter | None = None,
        summarizer: SummaryGenerator | None = None,
        answer_generator: AnswerGenerator | None = None,
        statistics_builder: StatisticsBuilder | None = None,
    ) -> None:
        self._result_formatter = result_formatter or ResultFormatter()
        self._summarizer = summarizer or SummaryGenerator()
        self._answer_generator = answer_generator or AnswerGenerator()
        self._statistics_builder = statistics_builder or StatisticsBuilder()

    def format(self, execution_result: SQLExecutionResult) -> BusinessAnswer:
        """Build a `BusinessAnswer` from `execution_result`.

        Raises `FormattingError` if `execution_result` was not a
        successful execution. Raises `SummaryGenerationError`/
        `AnswerGenerationError` if the corresponding collaborator fails.
        """
        if (
            execution_result.status is not ExecutionStatus.SUCCESS
            or execution_result.query_result is None
        ):
            raise FormattingError(
                "ResultFormatterEngine.format requires a successful SQLExecutionResult "
                f"with a query_result; got status={execution_result.status!r}."
            )

        started = time.perf_counter()

        formatted_table = self._result_formatter.format(execution_result.query_result)
        summary = self._summarizer.generate(formatted_table)
        answer_type = self._answer_generator.determine(execution_result, formatted_table)

        latency_ms = (time.perf_counter() - started) * 1000
        statistics = self._statistics_builder.build(formatted_table, latency_ms)

        return BusinessAnswer(
            answer_type=answer_type,
            summary=summary,
            formatted_table=formatted_table,
            statistics=statistics,
            execution_result=execution_result,
        )
