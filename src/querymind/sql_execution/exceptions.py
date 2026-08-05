"""Domain-specific exceptions for the SQL Execution Engine.

Unlike every prior phase's exception hierarchy, **every one of these is
caught by `querymind.sql_execution.engine.SQLExecutionEngine.execute`**
and converted into a `SQLExecutionResult` with the matching
`ExecutionStatus` — the engine's public method never raises for an
ordinary execution failure (a rejection, a connection problem, a timeout,
a database error, a formatting problem). This is deliberate: unlike an
LLM call (where a failure is arguably the caller's problem to handle),
"a real database briefly refused a connection" or "a query timed out" are
ordinary, expected outcomes of touching a live external system, and a
caller of this phase should never receive a raw, undocumented exception
type from a database driver — see the package's `ARCHITECTURAL NOTES`.
"""

from __future__ import annotations


class SQLExecutionError(Exception):
    """Base class for every exception raised within `querymind.sql_execution`."""


class SQLExecutionConfigurationError(SQLExecutionError):
    """Raised when a `querymind.sql_execution` component is constructed with invalid settings.

    A plain constructor-argument check (e.g. a non-positive timeout),
    mirroring `querymind.llm.retry.RetryPolicy`'s `max_retries` check —
    never a per-query finding.
    """


class ExecutionRejectedError(SQLExecutionError):
    """Raised by `ExecutionGuard` when execution is not permitted.

    `reason` is a short, human-readable explanation — validation didn't
    pass, the SQL is empty, more than one statement was found, the
    statement isn't a read-only `SELECT`/`WITH ... SELECT`, or it
    contains a write operation hidden inside a CTE.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class DatabaseConnectionError(SQLExecutionError):
    """Raised by `DatabaseConnectionProvider` when a connection cannot be acquired."""


class ExecutionTimeoutError(SQLExecutionError):
    """Raised by `SQLExecutor` when execution exceeds the configured timeout."""


class ExecutionFailureError(SQLExecutionError):
    """Raised by `SQLExecutor` when the database itself rejects or fails the query."""


class ResultFormattingError(SQLExecutionError):
    """Raised by `ResultFormatter` when raw database rows can't be converted into result models."""
