"""The SQL Execution Engine: runs validated (and, where needed, repaired) SQL read-only.

`SQLExecutionEngine` is the single public entry point for this package.
It orchestrates *only* — every actual piece of work is delegated to a
dedicated, single-responsibility, constructor-injected collaborator:
`ExecutionGuard` decides whether execution is permitted,
`DatabaseConnectionProvider` acquires a connection from the existing
async SQLAlchemy engine, `SQLExecutor` runs the query, and
`ResultFormatter` builds the immutable result models. The engine never
opens a raw connection, executes SQL directly, inspects SQL itself,
formats rows, or creates a database session.

Every exception these collaborators raise is caught here and converted
into a `SQLExecutionResult` with the matching `ExecutionStatus` — this
method never raises for an ordinary execution failure; see
`querymind.sql_execution.exceptions` for why.
"""

from __future__ import annotations

import time

from querymind.sql_execution.connection import DatabaseConnectionProvider
from querymind.sql_execution.exceptions import (
    DatabaseConnectionError,
    ExecutionFailureError,
    ExecutionRejectedError,
    ExecutionTimeoutError,
    ResultFormattingError,
)
from querymind.sql_execution.executor import SQLExecutor
from querymind.sql_execution.formatter import ResultFormatter
from querymind.sql_execution.models import (
    ExecutionError,
    ExecutionStatistics,
    ExecutionStatus,
    SQLExecutionResult,
)
from querymind.sql_execution.validator import ExecutionGuard
from querymind.sql_generation.models import GeneratedSQL
from querymind.sql_repair.models import SQLRepairResult
from querymind.sql_validation.models import SQLValidationResult


class SQLExecutionEngine:
    """Executes validated SQL read-only, orchestrating the collaborators listed above.

    Every collaborator is constructor-injected with a sensible default,
    so a caller can swap in a stricter guard, a different executor, or a
    different formatter without touching this class.
    `connection_provider` has no sensible default — it must be built from
    the application's own, already-existing `AsyncEngine`.
    """

    def __init__(
        self,
        connection_provider: DatabaseConnectionProvider,
        guard: ExecutionGuard | None = None,
        executor: SQLExecutor | None = None,
        formatter: ResultFormatter | None = None,
    ) -> None:
        self._connection_provider = connection_provider
        self._guard = guard or ExecutionGuard()
        self._executor = executor or SQLExecutor()
        self._formatter = formatter or ResultFormatter()

    async def execute(
        self, generated_sql: GeneratedSQL, validation_result: SQLValidationResult
    ) -> SQLExecutionResult:
        """Execute `generated_sql`, whose `validation_result` should report it as valid.

        Always returns a `SQLExecutionResult` — never raises for a
        rejection, a connection problem, a timeout, a database error, or
        a formatting problem. Rows are returned exactly as the database
        produced them; nothing here performs a business calculation.
        """
        started = time.perf_counter()

        try:
            permit = self._guard.check(generated_sql, validation_result)
        except ExecutionRejectedError as exc:
            return self._result(
                generated_sql,
                status=ExecutionStatus.REJECTED,
                sql=generated_sql.sql,
                error=ExecutionError(code="execution_rejected", message=exc.reason),
                started=started,
            )

        try:
            async with self._connection_provider.acquire() as connection:
                raw_result = await self._executor.execute(
                    connection, permit.sql, timeout_seconds=permit.timeout_seconds
                )
        except ExecutionTimeoutError as exc:
            return self._result(
                generated_sql,
                status=ExecutionStatus.TIMEOUT,
                sql=permit.sql,
                error=ExecutionError(code="execution_timeout", message=str(exc)),
                started=started,
            )
        except (DatabaseConnectionError, ExecutionFailureError) as exc:
            code = (
                "database_connection_error"
                if isinstance(exc, DatabaseConnectionError)
                else "execution_failed"
            )
            return self._result(
                generated_sql,
                status=ExecutionStatus.FAILED,
                sql=permit.sql,
                error=ExecutionError(code=code, message=str(exc)),
                started=started,
            )

        try:
            query_result = self._formatter.format(raw_result)
        except ResultFormattingError as exc:
            return self._result(
                generated_sql,
                status=ExecutionStatus.FAILED,
                sql=permit.sql,
                error=ExecutionError(code="result_formatting_failed", message=str(exc)),
                started=started,
            )

        latency_ms = (time.perf_counter() - started) * 1000
        return SQLExecutionResult(
            status=ExecutionStatus.SUCCESS,
            executed_sql=permit.sql,
            query_result=query_result,
            statistics=ExecutionStatistics(
                execution_latency_ms=latency_ms,
                rows_returned=query_result.row_count,
                columns_returned=len(query_result.columns),
                database_name=self._connection_provider.database_name,
                dialect=generated_sql.dialect,
            ),
            execution_error=None,
        )

    async def execute_repair_result(self, repair_result: SQLRepairResult) -> SQLExecutionResult:
        """Execute the outcome of a repair run: a thin convenience over `execute`.

        Unpacks `repair_result.final_sql`/`repair_result.final_validation_result`
        and delegates — no new logic of its own.
        """
        return await self.execute(repair_result.final_sql, repair_result.final_validation_result)

    def _result(
        self,
        generated_sql: GeneratedSQL,
        *,
        status: ExecutionStatus,
        sql: str,
        error: ExecutionError,
        started: float,
    ) -> SQLExecutionResult:
        latency_ms = (time.perf_counter() - started) * 1000
        return SQLExecutionResult(
            status=status,
            executed_sql=sql,
            query_result=None,
            statistics=ExecutionStatistics(
                execution_latency_ms=latency_ms,
                rows_returned=0,
                columns_returned=0,
                database_name=self._connection_provider.database_name,
                dialect=generated_sql.dialect,
            ),
            execution_error=error,
        )
