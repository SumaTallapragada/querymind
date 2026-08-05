"""Tests for `querymind.sql_execution.connection.DatabaseConnectionProvider`.

Runs against the real, already-running local Postgres instance (via the
same `Settings`/`create_engine` the application itself uses) rather than
a mock `AsyncEngine` — `AsyncConnection` is a thin, concrete SQLAlchemy
wrapper with no public seam worth faking, and the behavior under test
(read-only enforcement, real connection-failure translation) is only
meaningful against a real database.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from querymind.core.config import Settings
from querymind.sql_execution.connection import DatabaseConnectionProvider
from querymind.sql_execution.exceptions import DatabaseConnectionError


class TestAcquire:
    async def test_yields_a_working_connection(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        async with connection_provider.acquire() as connection:
            result = await connection.execute(text("SELECT 1;"))
            assert result.scalar_one() == 1

    async def test_connection_is_read_only(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        async with connection_provider.acquire() as connection:
            with pytest.raises(DBAPIError, match="read-only"):
                await connection.execute(
                    text("UPDATE customers SET customer_id = customer_id WHERE false;")
                )

    async def test_database_name_reflects_the_engine(
        self, connection_provider: DatabaseConnectionProvider, settings: Settings
    ) -> None:
        assert connection_provider.database_name == settings.postgres_db

    async def test_caller_exceptions_are_not_reclassified_as_connection_errors(
        self, connection_provider: DatabaseConnectionProvider
    ) -> None:
        """A failure raised by caller code *inside* `acquire()`'s `async with` body must
        propagate unchanged, not be mislabeled as a `DatabaseConnectionError`."""
        with pytest.raises(DBAPIError):
            async with connection_provider.acquire() as connection:
                await connection.execute(text("SELECT * FROM this_table_does_not_exist;"))


class TestAcquireFailure:
    async def test_an_unreachable_database_raises_database_connection_error(self) -> None:
        bad_engine = create_async_engine(
            "postgresql+asyncpg://nobody:nowhere@localhost:1/does_not_exist"
        )
        provider = DatabaseConnectionProvider(bad_engine)
        try:
            with pytest.raises(DatabaseConnectionError):
                async with provider.acquire():
                    pass
        finally:
            await bad_engine.dispose()
