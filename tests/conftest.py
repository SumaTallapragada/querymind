"""Shared pytest fixtures.

Tests construct their own :class:`Settings` explicitly rather than relying
on a real ``.env`` file, so the suite is hermetic and runnable in CI
without any local configuration.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from querymind.api.app import create_app
from querymind.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        postgres_user="test",
        postgres_password="test",  # type: ignore[arg-type]
        postgres_db="test",
        postgres_host="localhost",
        log_format="console",
    )


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired directly to the ASGI app, lifespan included.

    Using ``LifespanManager`` runs the app's startup/shutdown hooks (engine
    creation/disposal) exactly as they'd run in production, without
    binding a real network port.
    """
    app = create_app(settings=settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
