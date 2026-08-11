"""Shared fixtures for `querymind.security` tests -- mirrors `tests/auth/conftest.py` exactly
(real, already-running local Postgres via the real `Settings`/`create_engine`), used only by
`test_repository.py` (real-DB integration tests). `test_audit.py` needs no database at all -- it
uses a fake `AuditRepository`, matching `tests/auth/test_service.py`'s own "fake repository, no
I/O" precedent for `AuthenticationService`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from querymind.core.config import Settings
from querymind.db.engine import create_engine
from querymind.db.session import create_session_factory


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Function-scoped (not session-scoped): each async test runs in its own event loop, and an
    `AsyncEngine`'s connection pool holds loop-bound asyncio primitives -- see
    `tests/auth/conftest.py`'s identical fixture for the empirical reason why.
    """
    db_engine = create_engine(settings)
    yield db_engine
    await db_engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)
