"""Domain-specific exceptions for the SQL Repair Engine.

A SQL query that stays invalid after every repair attempt is never an
exception — it's `RepairStatus.MAX_ATTEMPTS_REACHED`/`NO_PROGRESS`,
reported as data in a `SQLRepairResult`, exactly like a failed
`SQLValidationResult` is never raised by `querymind.sql_validation`.
These exceptions are reserved for failures the repair pipeline itself
cannot route around: a malformed repair configuration, or a repair LLM
response with no extractable SQL at all.
"""

from __future__ import annotations


class SQLRepairError(Exception):
    """Base class for every exception raised by `querymind.sql_repair`."""


class SQLRepairConfigurationError(SQLRepairError):
    """Raised when a `querymind.sql_repair` component is constructed with invalid settings.

    Mirrors `querymind.prompt_compiler.budget.InvalidTokenBudgetError` /
    `querymind.llm.exceptions.LLMConfigurationError` — a plain constructor
    argument check (e.g. `RepairStrategy.max_attempts`), never a per-query finding.
    """


class RepairedSQLExtractionError(SQLRepairError):
    """Raised when no usable SQL text could be extracted from a repair LLM response.

    Mirrors `querymind.sql_generation.exceptions.SQLExtractionError` exactly —
    `RepairedSQLExtractor` reuses `querymind.sql_generation`'s own
    `SQLExtractor`, so this simply wraps that same failure mode for
    callers that only import `querymind.sql_repair`.
    """
