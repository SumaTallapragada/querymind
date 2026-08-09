"""`POST /query/stream` -- one question's pipeline progress, as Server-Sent Events.

The route does exactly what every other Phase 16 route does: validate
the request body, resolve its dependencies, and delegate -- here, to
`querymind.streaming.subscriber.stream_pipeline_events`, formatting each
`PipelineEvent` it yields as one SSE frame. No SQL generation,
validation, repair, execution, or formatting happens in this module; see
rule 1 of the Phase 17 spec.

Requires at least `ANALYST` (Phase 22B) -- streams the exact same pipeline `POST /query` runs,
protected the same way (`RequireAnalyst`, ranked -- `ADMIN` satisfies it too). An ordinary HTTP
route, so `CurrentUser`'s `OAuth2PasswordBearer`-based extraction works unmodified here; see
`querymind.streaming.websocket`'s own docstring for why `/ws/query` needs a different mechanism.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse

from querymind.api.dependencies import EventBusDep, LoggerDep, QueryMindEngineDep, RequireAnalyst
from querymind.api.models.request import QuestionRequest
from querymind.streaming.models import PipelineEvent
from querymind.streaming.serializer import serialize_event
from querymind.streaming.subscriber import stream_pipeline_events

router = APIRouter(prefix="/query/stream", tags=["streaming"])


def _format_sse_frame(event: PipelineEvent) -> str:
    """One Server-Sent Event frame: `event:`/`id:`/`data:` lines, blank-line terminated.

    `event:` is set to `event.event_type`'s value so a browser `EventSource`
    can `addEventListener("stage_completed", ...)` per event kind rather
    than parsing every message's `data:` payload to find out what it is.
    """
    return (
        f"id: {event.event_id}\n"
        f"event: {event.event_type.value}\n"
        f"data: {serialize_event(event)}\n\n"
    )


@router.post(
    "",
    status_code=status.HTTP_200_OK,
    summary="Stream one question's pipeline progress via Server-Sent Events",
    description=(
        "Runs the complete QueryMind pipeline exactly as `POST /query` does -- identical SQL "
        "generated, identical validation, identical repair, identical execution, identical "
        "`BusinessAnswer` -- while streaming `pipeline_started`, `stage_started`, "
        "`stage_completed`, `stage_failed`, `heartbeat` (periodically, once a run has taken a "
        "few seconds), and a final `pipeline_completed`/`pipeline_failed` event as they happen. "
        "The final `pipeline_completed` event's payload carries the `BusinessAnswer`. Requires "
        "at least the `analyst` role."
    ),
    responses={
        200: {
            "description": "text/event-stream -- one frame per pipeline event.",
            "content": {
                "text/event-stream": {
                    "example": (
                        "event: pipeline_started\n"
                        'data: {"event_type": "pipeline_started", "...": "..."}\n\n'
                    )
                }
            },
        }
    },
)
async def stream_query(
    request: Request,
    body: QuestionRequest,
    engine: QueryMindEngineDep,
    event_bus: EventBusDep,
    logger: LoggerDep,
    _analyst: RequireAnalyst,
) -> StreamingResponse:
    correlation_id: str = (
        getattr(request.state, "correlation_id", None)
        or request.headers.get("X-Correlation-ID")
        or uuid.uuid4().hex
    )

    async def event_source() -> AsyncIterator[str]:
        logger.info("sse_connection_opened", correlation_id=correlation_id)
        try:
            async for event in stream_pipeline_events(
                query_mind_engine=engine,
                event_bus=event_bus,
                question=body.question,
                correlation_id=correlation_id,
                logger=logger,
            ):
                logger.debug(
                    f"sse_event_sent (type={event.event_type.value})", correlation_id=correlation_id
                )
                yield _format_sse_frame(event)
        except BaseException:
            logger.info("sse_client_disconnected", correlation_id=correlation_id)
            raise
        finally:
            logger.info("sse_connection_closed", correlation_id=correlation_id)

    return StreamingResponse(event_source(), media_type="text/event-stream")
