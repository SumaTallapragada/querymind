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
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from querymind.api.dependencies import EventBusDep, LoggerDep, QueryMindEngineDep
from querymind.api.models.request import QuestionRequest
from querymind.streaming.serializer import serialize_event
from querymind.streaming.subscriber import stream_pipeline_events

router = APIRouter(tags=["streaming"])


@router.websocket("/ws/query")
async def stream_query_ws(
    websocket: WebSocket,
    engine: QueryMindEngineDep,
    event_bus: EventBusDep,
    logger: LoggerDep,
) -> None:
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
