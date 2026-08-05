"""SQLExecutor: runs one SQL statement against an already-acquired connection.

Responsibilities only: execute, bind parameters, fetch rows, capture
timing. No formatting (that is `ResultFormatter`'s job — this module
returns a plain, unformatted `RawQueryResult`), no serialization, no
retry logic (a query that fails or times out fails; `SQLExecutor` never
tries again — see the package's `ARCHITECTURAL NOTES`).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

from querymind.sql_execution.exceptions import ExecutionFailureError, ExecutionTimeoutError


@dataclass(frozen=True, slots=True)
class RawQueryResult:
    """The unformatted result of one `SQLExecutor.execute` call — `ResultFormatter`'s input."""

    column_names: tuple[str, ...]
    column_type_oids: tuple[int | None, ...]
    rows: tuple[tuple[Any, ...], ...]
    execution_latency_ms: float


class SQLExecutor:
    """Executes one SQL statement against a given connection. Executes only."""

    async def execute(
        self,
        connection: AsyncConnection,
        sql: str,
        *,
        timeout_seconds: float,
        parameters: Mapping[str, object] | None = None,
    ) -> RawQueryResult:
        """Run `sql` (with optional bind `parameters` — future-ready, unused by any caller yet).

        Raises `ExecutionTimeoutError` if `timeout_seconds` is exceeded,
        or `ExecutionFailureError` for any other database-reported
        failure. Never retries.
        """
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                connection.execute(text(sql), parameters or {}), timeout=timeout_seconds
            )
        except TimeoutError as exc:
            raise ExecutionTimeoutError(
                f"Execution exceeded the {timeout_seconds}s timeout."
            ) from exc
        except SQLAlchemyError as exc:
            raise ExecutionFailureError(str(exc)) from exc

        try:
            column_names = tuple(result.keys())
            cursor_description = result.cursor.description if result.cursor is not None else None
            # `column[1]` (DBAPI `type_code`) is nominally an opaque `DBAPIType`, but
            # asyncpg's cursor description actually reports the real integer OID.
            type_oids: tuple[int | None, ...] = (
                tuple(
                    cast(int, column[1]) if column[1] is not None else None
                    for column in cursor_description
                )
                if cursor_description is not None
                else tuple(None for _ in column_names)
            )
            rows = tuple(tuple(row) for row in result.fetchall())
        except SQLAlchemyError as exc:
            raise ExecutionFailureError(str(exc)) from exc

        latency_ms = (time.perf_counter() - started) * 1000
        return RawQueryResult(
            column_names=column_names,
            column_type_oids=type_oids,
            rows=rows,
            execution_latency_ms=latency_ms,
        )
