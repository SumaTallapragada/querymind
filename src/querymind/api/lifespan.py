"""Application lifespan: startup and shutdown, for resources whose lifetime spans the process.

Startup builds the one `ApplicationContainer` for the process (loading
metadata, business knowledge, and the query library; constructing every
engine down to `QueryMindEngine`) and logs how long that took. Shutdown
disposes the database engine -- the one real resource anything here
holds -- and logs that it did.

`app.state.session_factory` is still populated here too, unchanged from
Phase 1, backing the existing `/api/v1/health/ready` endpoint -- built
from the *same* `AsyncEngine` the container itself uses
(`container.engine`), never a second one.

If `querymind.api.app.create_app` was given an `llm_transport` (tests
only -- an `httpx.MockTransport`-backed one, never in production), it is
threaded through to `ApplicationContainer.build` here via
`app.state.llm_transport`.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from querymind.api.container import ApplicationContainer
from querymind.core.config import Settings
from querymind.db.session import create_session_factory
from querymind.llm.client import HTTPTransport


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the `ApplicationContainer` on startup; dispose its database engine on shutdown."""
    settings: Settings = app.state.settings
    llm_transport: HTTPTransport | None = getattr(app.state, "llm_transport", None)

    started = time.perf_counter()
    container = ApplicationContainer.build(settings, llm_transport=llm_transport)
    startup_duration_ms = (time.perf_counter() - started) * 1000

    app.state.container = container
    app.state.engine = container.engine
    app.state.session_factory = create_session_factory(container.engine)

    container.logger.info(
        f"application_startup (env={settings.app_env})",
        duration_ms=startup_duration_ms,
    )
    try:
        yield
    finally:
        await container.dispose()
        container.logger.info("application_shutdown")
