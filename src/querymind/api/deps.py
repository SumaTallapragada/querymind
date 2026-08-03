"""Shared FastAPI dependencies.

Centralizing dependency callables here (rather than redefining
``Depends(...)`` calls inline in every router) gives every endpoint the
same typed, reusable building blocks and is the one place tests need to
patch via ``app.dependency_overrides`` to swap in fakes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from querymind.core.config import Settings, get_settings
from querymind.db.session import transactional_session

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a transaction-scoped async DB session for the current request.

    The session factory is read off ``app.state`` (populated once at
    startup in ``main.py``'s lifespan handler) rather than constructed
    here, so the engine's connection pool is created exactly once per
    process and shared across all requests.
    """
    session_factory = request.app.state.session_factory
    async with transactional_session(session_factory) as session:
        yield session


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
