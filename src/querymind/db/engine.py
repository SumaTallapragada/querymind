"""Async SQLAlchemy engine construction.

The engine is created once per process from :class:`~querymind.core.config.Settings`
and reused for the lifetime of the application; it owns the connection pool
and must be explicitly disposed on shutdown (see ``main.py``'s lifespan
handler) so pooled connections are closed cleanly.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from querymind.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Build the application's async SQLAlchemy engine from settings."""
    return create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout,
        # Guards against stale connections (e.g. after a DB restart or a
        # load balancer idle-timeout) by validating a connection with a
        # cheap ping before handing it out of the pool.
        pool_pre_ping=True,
    )
