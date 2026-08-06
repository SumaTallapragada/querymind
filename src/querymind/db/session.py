"""Async session factory and transaction-scoped session helper.

This module is intentionally framework-agnostic (no FastAPI imports): it
only knows how to turn an :class:`AsyncEngine` into sessions. Wiring this
up as a FastAPI dependency — which needs access to the request-scoped
engine on ``app.state`` — lives in ``querymind.api.dependencies``. Keeping
the two separate means the persistence layer stays usable outside of a web
request (e.g. from a CLI script or a background worker).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build a session factory bound to the given engine.

    ``expire_on_commit=False`` so ORM instances remain usable (e.g. for
    serialization into an API response) after their transaction commits,
    without triggering a lazy-load round trip.
    """
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def transactional_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield a session wrapped in a commit/rollback transaction boundary.

    On success the transaction is committed; on any exception it is rolled
    back and the exception re-raised. Callers never need to remember to
    call ``commit()`` themselves.
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
