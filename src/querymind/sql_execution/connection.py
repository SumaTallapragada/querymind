"""Acquires and releases database connections, reusing the existing async SQLAlchemy engine.

`DatabaseConnectionProvider` never constructs its own `AsyncEngine` — the
one built once at application startup by
`querymind.db.engine.create_engine` is injected via its constructor, and
this module never imports that function itself (constructing the engine
is the composition root's job, not this package's).

Every connection handed out is opened read-only at the database level
(`postgresql_readonly=True`) — a second, database-enforced defense
alongside `ExecutionGuard`'s AST-level checks (verified against a real
PostgreSQL instance during development: a write attempted on a
`postgresql_readonly=True` connection raises
`asyncpg.exceptions.ReadOnlySQLTransactionError`, not merely a
SQLAlchemy-level rejection) — so a write can never succeed through this
path even if an AST check were somehow bypassed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from querymind.sql_execution.exceptions import DatabaseConnectionError


class DatabaseConnectionProvider:
    """Acquires read-only connections from the existing async SQLAlchemy engine. Manages connections only."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[AsyncConnection]:
        """Yield a read-only database connection. Raises `DatabaseConnectionError` if one can't be acquired.

        Only the acquisition step itself (opening the connection, tagging
        it read-only) is wrapped in error translation — deliberately not
        the `yield` — so an exception raised by *the caller's own code*
        while using the connection (e.g. a query failure inside
        `SQLExecutor.execute`) propagates unchanged, rather than being
        misreported as a connection-acquisition failure.

        Catches `Exception` broadly, not just `sqlalchemy.exc.SQLAlchemyError`
        -- verified empirically that a real connection failure (unreachable
        host, wrong password) surfaces as a raw, un-translated driver/OS
        exception at this specific step (a bare `OSError` for a refused TCP
        connection; an `asyncpg.exceptions.InvalidPasswordError` for bad
        credentials), not a `SQLAlchemyError`. SQLAlchemy's usual exception
        translation only wraps statement *execution*, not initial connection
        acquisition, for the async driver.
        """
        async with AsyncExitStack() as stack:
            try:
                connection = await stack.enter_async_context(self._engine.connect())
                read_only_connection = await connection.execution_options(postgresql_readonly=True)
            except Exception as exc:
                raise DatabaseConnectionError(str(exc)) from exc
            yield read_only_connection

    @property
    def database_name(self) -> str:
        """The name of the database this provider's engine is connected to."""
        return self._engine.url.database or ""
