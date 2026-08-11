"""The real `create_app()` factory for the FastAPI service layer (Phase 16; streaming, Phase 17).

Wires together, in order: `Settings`, structured logging, `lifespan`
(builds/disposes the one `ApplicationContainer`), middleware (GZip, CORS,
then `RequestContextMiddleware` -- Starlette runs middleware innermost-
first for requests, so listing `RequestContextMiddleware` last here means
it's the *first* to see each request and the *last* to see each
response, giving every other middleware and every route a request ID
already bound), the aggregate `api_router` (which now includes
`querymind.streaming.sse`'s `POST /query/stream`), the unversioned
`querymind.streaming.websocket` router (`/ws/query`), this phase's
exception handlers, and the pre-existing generic `Exception` handler.

`querymind.main` re-exports `create_app`/`app` from here unchanged --
this module, not `main.py`, is now the actual composition root.
"""

from __future__ import annotations

import structlog
from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from querymind.api.dependencies import check_general_rate_limit
from querymind.api.exception_handlers import register_exception_handlers
from querymind.api.lifespan import lifespan
from querymind.api.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from querymind.api.v1.router import api_router
from querymind.core.config import Settings, get_settings
from querymind.core.logging import configure_logging
from querymind.llm.client import HTTPTransport
from querymind.streaming import websocket


def create_app(
    settings: Settings | None = None, *, llm_transport: HTTPTransport | None = None
) -> FastAPI:
    """Build and configure the FastAPI application instance.

    `llm_transport` is test-only (see `querymind.api.lifespan`'s
    docstring) -- always `None` in production, in which case
    `ApplicationContainer.build` has `ClaudeProvider` open its own real
    HTTP transport.
    """
    settings = settings or get_settings()
    configure_logging(log_level=settings.log_level, log_format=settings.log_format)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.llm_transport = llm_transport

    app.add_middleware(GZipMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
    # Added last, so it's the *outermost* wrapper (Starlette middleware runs innermost-first for
    # requests) -- it sees, and can stamp headers onto, literally every response this process
    # produces: a normal route response, a mapped-exception `JSONResponse`
    # (`querymind.api.exception_handlers`), and the generic `Exception` handler's fallback below.
    app.add_middleware(
        SecurityHeadersMiddleware,
        is_production=settings.is_production,
        auth_path_prefix=f"{settings.api_v1_prefix}/auth",
    )

    # `dependencies=[Depends(check_general_rate_limit)]` here, not on `api_router` itself
    # (`querymind.api.v1.router`), applies Phase 22D's one coarse, application-wide ceiling to
    # every route under `settings.api_v1_prefix` in one place -- `/ws/query` below is
    # unversioned and unauthenticated-at-this-point-in-the-connection, so it can't use this
    # mechanism at all; it checks the same `RateLimiter` directly instead (see
    # `querymind.streaming.websocket`'s own docstring).
    app.include_router(
        api_router,
        prefix=settings.api_v1_prefix,
        dependencies=[Depends(check_general_rate_limit)],
    )
    # Unversioned, matching the Phase 17 spec's literal `/ws/query` path -- every other
    # streaming endpoint (`POST /query/stream`) lives under `settings.api_v1_prefix` above,
    # alongside the rest of the `/query/*` family.
    app.include_router(websocket.router)

    register_exception_handlers(app)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Last-resort handler so unexpected errors never leak internals.

        Logs the full exception server-side (with the request ID already
        bound by ``RequestContextMiddleware``) while returning a generic,
        client-safe payload. Unchanged from Phase 1.
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
