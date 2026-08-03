"""ASGI middleware for cross-cutting request concerns."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Binds a request ID to structlog's contextvars for the request's lifetime.

    Every log line emitted while handling a request — from any module,
    at any call depth — automatically carries this ID, which is what makes
    it possible to grep a centralized log store for every line belonging
    to one request. The ID is accepted from an inbound ``X-Request-ID``
    header when present (so it survives across service boundaries) and
    otherwise generated fresh, then echoed back on the response.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
