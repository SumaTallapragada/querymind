"""The Result Formatter / Answer Generator — QueryMind Phase 14.

Turns a successful `querymind.sql_execution.SQLExecutionResult` into an
immutable `BusinessAnswer`: a formatted table, a deterministic summary,
and an `AnswerType` classification. It does **not** execute, validate,
generate, or repair SQL, does **not** call the LLM, and does **not**
produce any visualization (HTML, markdown tables, CSV, Excel, charts,
images) -- those are later phases.

The public surface is `ResultFormatterEngine.format`.
"""

from __future__ import annotations

from querymind.result_formatter.answer_generator import AnswerGenerator
from querymind.result_formatter.cache import NoOpResultFormatterCache, ResultFormatterCache
from querymind.result_formatter.engine import ResultFormatterEngine
from querymind.result_formatter.exceptions import (
    AnswerGenerationError,
    FormattingError,
    ResultFormatterError,
    SummaryGenerationError,
)
from querymind.result_formatter.formatter import ResultFormatter
from querymind.result_formatter.models import (
    AnswerStatistics,
    AnswerSummary,
    AnswerType,
    BusinessAnswer,
    FormattedRow,
    FormattedTable,
    FormattedValue,
)
from querymind.result_formatter.serializer import ResultFormatterSerializer
from querymind.result_formatter.statistics import StatisticsBuilder
from querymind.result_formatter.summarizer import SummaryGenerator
from querymind.result_formatter.value_formatter import ValueFormatter

__all__ = [
    "AnswerGenerationError",
    "AnswerGenerator",
    "AnswerStatistics",
    "AnswerSummary",
    "AnswerType",
    "BusinessAnswer",
    "FormattedRow",
    "FormattedTable",
    "FormattedValue",
    "FormattingError",
    "NoOpResultFormatterCache",
    "ResultFormatter",
    "ResultFormatterCache",
    "ResultFormatterEngine",
    "ResultFormatterError",
    "ResultFormatterSerializer",
    "StatisticsBuilder",
    "SummaryGenerationError",
    "SummaryGenerator",
    "ValueFormatter",
]
