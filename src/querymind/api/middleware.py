"""ASGI middleware for cross-cutting request concerns.

CORS and GZip compression are Starlette's own built-in middleware,
registered directly in `querymind.api.app.create_app` -- there is
nothing project-specific about them worth wrapping here.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from querymind.api.container import ApplicationContainer
from querymind.observability.logger import StageInstrumentation

REQUEST_ID_HEADER = "X-Request-ID"
CORRELATION_ID_HEADER = "X-Correlation-ID"

#: Deliberately no `Content-Security-Policy` here (Phase 22D) -- this API only ever returns
#: JSON (or a `text/event-stream`/WebSocket upgrade), never browser-rendered HTML/JS/CSS of its
#: own, so a CSP protects nothing on a normal response and actively breaks the one place this
#: process *does* serve HTML: FastAPI's own `/docs` (Swagger UI) and `/redoc`, both of which
#: load their JS/CSS from a CDN (`cdn.jsdelivr.net`) by default. `X-Frame-Options`/`frame-
#: ancestors` are skipped for the same reason this project's actual browser-rendered surface
#: (the React app, served by nginx) is where clickjacking protection belongs --
#: `frontend/nginx.conf` carries both. Strict-Transport-Security is added conditionally, below,
#: only when `Settings.is_production` -- see `SecurityHeadersMiddleware`'s own docstring.
_BASELINE_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}

_HSTS_HEADER = "Strict-Transport-Security"
_HSTS_VALUE = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds baseline security headers to every API response.

    `is_production` is read once, from `Settings.is_production` (Phase 1's existing "what
    environment is this" indicator -- reused rather than a duplicate `Settings` field), at
    construction time, not per-request -- the environment doesn't change while a process is
    running. Strict-Transport-Security is emitted only then: sending it over plain HTTP in
    development would tell a browser to remember an HTTPS-only policy for a host that doesn't
    even serve HTTPS, which is actively wrong, not merely unnecessary.

    `auth_path_prefix` (e.g. `/api/v1/auth`, built from `Settings.api_v1_prefix` so this stays
    correct if that's ever reconfigured) gets `Cache-Control: no-store` on top of the baseline
    set -- every response under it can carry a fresh access/refresh token pair or the current
    user's identity, none of which should ever be cached by a browser or an intermediary proxy.
    """

    def __init__(self, app: ASGIApp, *, is_production: bool, auth_path_prefix: str) -> None:
        super().__init__(app)
        self._is_production = is_production
        self._auth_path_prefix = auth_path_prefix

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)

        for name, value in _BASELINE_HEADERS.items():
            response.headers[name] = value

        if self._is_production:
            response.headers[_HSTS_HEADER] = _HSTS_VALUE

        if request.url.path.startswith(self._auth_path_prefix):
            response.headers["Cache-Control"] = "no-store"

        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Binds request/correlation IDs, and reuses `StageInstrumentation` for structured
    per-request logging and timing -- one started/completed/failed log event per request,
    exactly like any pipeline stage.

    Request and correlation IDs are both accepted from inbound headers
    when present (so they survive across service boundaries) and
    otherwise generated fresh; both are echoed back on the response.
    `structlog.contextvars` binding is unchanged from Phase 1 -- every
    log line emitted while handling a request, from any module, at any
    call depth, still automatically carries both IDs.

    Structured request logging goes through `ApplicationContainer.logger`
    (`querymind.observability`), not `structlog` directly -- reusing the
    existing observability package rather than a second, parallel
    logging path, per this phase's explicit rule. If no container is on
    `app.state` yet (defensive only; `querymind.api.lifespan` always sets
    one before any request can be routed), the request still proceeds
    normally, just without that extra structured event.

    `request.state.request_id`/`.correlation_id` (Phase 17) let a route
    reuse the same IDs this middleware already generated/echoed, rather
    than minting a second, different pair -- `querymind.streaming.sse`'s
    `POST /query/stream` is the first route to do so. Note this
    middleware never runs for a `/ws/query` WebSocket connection at all
    (Starlette's `BaseHTTPMiddleware` only wraps `http`-scope requests);
    `querymind.streaming.websocket` binds its own IDs for that reason.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid.uuid4()))
        correlation_id = request.headers.get(CORRELATION_ID_HEADER, request_id)
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, correlation_id=correlation_id)

        container: ApplicationContainer | None = getattr(request.app.state, "container", None)
        stage_name = f"{request.method} {request.url.path}"

        if container is None:
            response = await call_next(request)
        else:
            with StageInstrumentation(
                container.logger, stage_name, correlation_id=correlation_id, request_id=request_id
            ):
                response = await call_next(request)

        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
