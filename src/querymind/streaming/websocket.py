"""`/ws/query` -- one question's pipeline progress, as WebSocket text frames.

Same contract as `POST /query/stream` (`querymind.streaming.sse`), over
a different transport: the client sends one `{"question": "..."}` JSON
message, the server streams the same `PipelineEvent`s SSE would, one per
text frame, and closes the connection after the terminal event. No SQL
generation, validation, repair, execution, or formatting happens in this
module; see rule 1 of the Phase 17 spec.

Unlike HTTP routes, a WebSocket connection never passes through
`querymind.api.middleware.RequestContextMiddleware` (Starlette's
`BaseHTTPMiddleware` only wraps `http`-scope requests, never `websocket`-
scope ones) -- this module binds its own request/correlation ID pair and
`structlog` context instead, mirroring what that middleware does for
every HTTP request.

Requires at least `ANALYST` (Phase 22B), same as `POST /query/stream` -- but not via
`RequireAnalyst`/`Depends()`. Verified empirically that `fastapi.security.OAuth2PasswordBearer`
(what `RequireAnalyst`/`CurrentUser` are built on) raises a bare `TypeError` on a WebSocket
route: FastAPI never injects a `Request` for a `websocket`-scope connection, and
`OAuth2PasswordBearer.__call__`'s signature requires one. `_authenticate_and_authorize` below
is the necessary substitute -- it still delegates entirely to
`AuthenticationService.get_current_user`/`.require_role` (no JWT decoding or role comparison of
its own), it just can't be a `Depends()`-resolved dependency here. It also accepts the token via
a `token` query parameter as well as the `Authorization` header, since a browser's native
`WebSocket` API cannot set custom headers at all -- only non-browser WebSocket clients can.

Phase 22D's per-user query rate limit (`RateLimitQuery`/`check_query_rate_limit` in
`querymind.api.dependencies`, shared with `POST /query`/`/query/stream`/etc.) is checked here
too, for the same reason authentication is: this route can't use `Depends()` at all, so
`_authenticate_and_authorize` calls `container.rate_limiter` directly, using the exact same
`f"query:user:{user.id}"` key and `Settings.rate_limit_query_per_minute` limit every other
query-family route uses, keeping one shared bucket per user regardless of which surface they
use. Checked *before* `.accept()`, same as authentication -- a caller over the limit never gets
a connection at all, and individual frames within an already-open connection are never
rate-limited (there is only ever one question per connection to begin with; see this module's
own opening paragraph).
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from querymind.api.container import ApplicationContainer
from querymind.api.dependencies import ContainerDep, EventBusDep, LoggerDep, QueryMindEngineDep
from querymind.api.models.request import QuestionRequest
from querymind.auth.exceptions import AuthenticationError, AuthorizationError
from querymind.auth.models import UserRole
from querymind.auth.schemas import UserRead
from querymind.streaming.serializer import serialize_event
from querymind.streaming.subscriber import stream_pipeline_events

router = APIRouter(tags=["streaming"])


async def _authenticate_and_authorize(
    websocket: WebSocket, container: ApplicationContainer
) -> UserRead | None:
    """Resolve and role-check the caller *before* `.accept()`, rejecting the handshake outright
    on failure (verified: closing before accept correctly surfaces as a rejected connection to
    the client, not a silently-accepted-then-dropped one) rather than catching an exception --
    a WebSocket route's own errors don't flow through the HTTP-response-shaped
    `querymind.api.exception_handlers` the way an HTTP route's do, so this mirrors the
    established inline-validation pattern already used a few lines below for an invalid request
    body, not that mechanism. The same reasoning covers the rate-limit check added here in
    Phase 22D -- see this module's own docstring.
    """
    authorization = websocket.headers.get("Authorization", "")
    token = authorization.removeprefix("Bearer ").strip() or websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Not authenticated.")
        return None
    try:
        user = await container.authentication_service.get_current_user(token)
        container.authentication_service.require_role(user, UserRole.ANALYST)
    except (AuthenticationError, AuthorizationError) as exc:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(exc)[:120])
        return None

    capacity = container.settings.rate_limit_query_per_minute
    decision = await container.rate_limiter.check(
        f"query:user:{user.id}", capacity=capacity, refill_per_second=capacity / 60
    )
    if not decision.allowed:
        await websocket.close(
            code=status.WS_1013_TRY_AGAIN_LATER,
            reason="Too many requests. Please slow down and try again shortly.",
        )
        return None

    return user


@router.websocket("/ws/query")
async def stream_query_ws(
    websocket: WebSocket,
    engine: QueryMindEngineDep,
    event_bus: EventBusDep,
    logger: LoggerDep,
    container: ContainerDep,
) -> None:
    if await _authenticate_and_authorize(websocket, container) is None:
        return

    await websocket.accept()

    correlation_id = uuid.uuid4().hex
    structlog.contextvars.bind_contextvars(request_id=correlation_id, correlation_id=correlation_id)
    logger.info("websocket_connection_opened", correlation_id=correlation_id)

    try:
        raw_message = await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("websocket_client_disconnected", correlation_id=correlation_id)
        return

    try:
        request = QuestionRequest.model_validate_json(raw_message)
    except ValidationError as exc:
        logger.info(f"websocket_invalid_request ({exc})", correlation_id=correlation_id)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid request.")
        return

    try:
        async for event in stream_pipeline_events(
            query_mind_engine=engine,
            event_bus=event_bus,
            question=request.question,
            correlation_id=correlation_id,
            logger=logger,
        ):
            logger.debug(
                f"websocket_event_sent (type={event.event_type.value})",
                correlation_id=correlation_id,
            )
            await websocket.send_text(serialize_event(event))
    except WebSocketDisconnect:
        logger.info("websocket_client_disconnected", correlation_id=correlation_id)
        return
    finally:
        structlog.contextvars.clear_contextvars()
        logger.info("websocket_connection_closed", correlation_id=correlation_id)

    await websocket.close()
