"""The SQL Execution Engine — QueryMind Phase 13.

Executes validated (and, where needed, repaired) SQL read-only against
the real database, using the existing async SQLAlchemy engine — no
second engine, no ORM models, no writes. It does **not** generate,
repair, optimize, or explain SQL, does **not** summarize results, does
**not** generate charts, and does **not** answer questions — those are
later phases. `SQLExecutionEngine.execute` never raises for an ordinary
execution failure; every outcome is a structured `SQLExecutionResult`.

The public surface is `SQLExecutionEngine.execute` (and
`execute_repair_result`, a thin convenience over it).
"""

from __future__ import annotations

from querymind.sql_execution.cache import NoOpSQLExecutionCache, SQLExecutionCache
from querymind.sql_execution.connection import DatabaseConnectionProvider
from querymind.sql_execution.engine import SQLExecutionEngine
from querymind.sql_execution.exceptions import (
    DatabaseConnectionError,
    ExecutionFailureError,
    ExecutionRejectedError,
    ExecutionTimeoutError,
    ResultFormattingError,
    SQLExecutionConfigurationError,
    SQLExecutionError,
)
from querymind.sql_execution.executor import RawQueryResult, SQLExecutor
from querymind.sql_execution.formatter import ResultFormatter
from querymind.sql_execution.models import (
    ExecutionError,
    ExecutionStatistics,
    ExecutionStatus,
    QueryColumn,
    QueryResult,
    QueryRow,
    SQLExecutionResult,
)
from querymind.sql_execution.serializer import SQLExecutionSerializer
from querymind.sql_execution.validator import (
    DEFAULT_EXECUTION_TIMEOUT_SECONDS,
    ExecutionGuard,
    ExecutionPermit,
)

__all__ = [
    "DEFAULT_EXECUTION_TIMEOUT_SECONDS",
    "DatabaseConnectionError",
    "DatabaseConnectionProvider",
    "ExecutionError",
    "ExecutionFailureError",
    "ExecutionGuard",
    "ExecutionPermit",
    "ExecutionRejectedError",
    "ExecutionStatistics",
    "ExecutionStatus",
    "ExecutionTimeoutError",
    "NoOpSQLExecutionCache",
    "QueryColumn",
    "QueryResult",
    "QueryRow",
    "RawQueryResult",
    "ResultFormatter",
    "ResultFormattingError",
    "SQLExecutionCache",
    "SQLExecutionConfigurationError",
    "SQLExecutionEngine",
    "SQLExecutionError",
    "SQLExecutionResult",
    "SQLExecutionSerializer",
    "SQLExecutor",
]
