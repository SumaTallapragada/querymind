"""Application composition root.

This is the only module that wires concrete infrastructure (the DB engine,
logging, middleware, routers) together into a running FastAPI app. Using an
``create_app()`` factory instead of a module-level ``app = FastAPI()``
keeps the app importable and reconfigurable in tests (e.g. constructing a
fresh app per test with dependency overrides) without relying on import
side effects.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from querymind.api.middleware import RequestContextMiddleware
from querymind.api.v1.router import api_router
from querymind.core.config import Settings, get_settings
from querymind.core.logging import configure_logging, get_logger
from querymind.db.engine import create_engine
from querymind.db.session import create_session_factory

logger = get_logger(module=__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage resources whose lifetime spans the whole process.

    The DB engine (and the connection pool it owns) is created once here at
    startup and disposed once at shutdown — never per-request — and is
    handed to request handlers via ``app.state`` and the ``get_db_session``
    dependency.
    """
    settings: Settings = app.state.settings
    engine = create_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    logger.info("application_startup", app_env=settings.app_env)
    try:
        yield
    finally:
        await engine.dispose()
        logger.info("application_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application instance."""
    settings = settings or get_settings()
    configure_logging(log_level=settings.log_level, log_format=settings.log_format)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(RequestContextMiddleware)

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Last-resort handler so unexpected errors never leak internals.

        Logs the full exception server-side (with the request ID already
        bound by ``RequestContextMiddleware``) while returning a generic,
        client-safe payload.
        """
        structlog.get_logger().exception(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    return app


app = create_app()
