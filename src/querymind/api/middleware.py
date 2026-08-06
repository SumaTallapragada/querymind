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

from querymind.api.container import ApplicationContainer
from querymind.observability.logger import StageInstrumentation

REQUEST_ID_HEADER = "X-Request-ID"
CORRELATION_ID_HEADER = "X-Correlation-ID"


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
