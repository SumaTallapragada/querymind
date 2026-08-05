"""Domain-specific exceptions for the Result Formatter / Answer Generator.

Unlike `querymind.sql_execution.engine.SQLExecutionEngine.execute` (which
catches every one of its own domain exceptions and converts them into a
result model), `ResultFormatterEngine.format` does **not** catch these --
there is no "failed" `BusinessAnswer` variant in this phase's model (no
`ExecutionError`-shaped field, no FAILED `AnswerType`), and this phase
starts only after `SQLExecutionResult.status` is already `SUCCESS`. A
raised exception here means the caller violated that precondition or a
formatting step hit a genuinely unexpected input -- there is nothing
sensible to encode as a "formatted answer" in that case.
"""

from __future__ import annotations


class ResultFormatterError(Exception):
    """Base class for every exception raised within `querymind.result_formatter`."""


class FormattingError(ResultFormatterError):
    """Raised by `ResultFormatter`/`ValueFormatter` when a `QueryResult` can't be formatted."""


class SummaryGenerationError(ResultFormatterError):
    """Raised by `SummaryGenerator` when an `AnswerSummary` can't be produced."""


class AnswerGenerationError(ResultFormatterError):
    """Raised by `AnswerGenerator` when an `AnswerType` can't be determined."""
