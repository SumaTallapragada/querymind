"""Shared fixtures for `querymind.auth` tests.

`settings`/`engine`/`session_factory` are built from the real, already-running local Postgres
instance (via the same `Settings`/`create_engine` the application itself uses), mirroring
`tests/sql_execution/conftest.py`'s "real infrastructure, no mocks" precedent -- used only by
`test_repository.py`/`test_integration.py`. Every other file in this package (`test_jwt.py`,
`test_passwords.py`, `test_service.py`, `test_cache.py`, `test_exceptions.py`,
`test_serializer.py`, `test_schemas.py`, `test_models.py`) never requests these fixtures and
needs no database connection at all.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from querymind.core.config import Settings
from querymind.db.engine import create_engine
from querymind.db.session import create_session_factory

#: A fixed, non-production secret shared by every unit test that needs one -- never read from
#: `Settings` (see `querymind.auth.jwt`'s own module docstring for why this package takes its
#: configuration as explicit parameters, not global config). Long enough (94 bytes) to stay
#: above PyJWT's minimum recommended HMAC key length for HS256/HS384/HS512 alike (32/48/64
#: bytes respectively) -- a shorter one triggers `InsecureKeyLengthWarning`, which this
#: project's `filterwarnings = ["error"]` (pyproject.toml) turns into a hard test failure.
TEST_JWT_SECRET_KEY = "unit-test-secret-key-never-used-in-production" * 2


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Function-scoped (not session-scoped): each async test runs in its own event loop, and an
    `AsyncEngine`'s connection pool holds loop-bound asyncio primitives -- see
    `tests/sql_execution/conftest.py`'s identical fixture for the empirical reason why.
    """
    db_engine = create_engine(settings)
    yield db_engine
    await db_engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)
