"""EventSubscriber: consumes one correlation_id's events off the `EventBus`.

`EventSubscriber` itself is a small, transport-agnostic primitive: wrap
one `Subscription`, expose its events as an async iterator, and always
unsubscribe on exit -- via `async with` or an explicit `aclose()`, even
if the consumer stops early or raises. `stream_pipeline_events` (below)
is the higher-level driver both `querymind.streaming.sse` and
`.websocket` use: it starts the actual pipeline run as a background
task, starts a periodic heartbeat task, and yields every event for one
correlation_id until a terminal event arrives -- handling cancellation
and cleanup (rule 8 of the Phase 17 spec) identically for both
transports, so neither transport module needs to know anything about
tasks, heartbeats, or cancellation itself (rule 1: "streaming is
presentation only").
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator, AsyncIterator

from querymind.observability.logger import Logger
from querymind.orchestrator import QueryMindEngine
from querymind.streaming.event_bus import EventBus, Subscription
from querymind.streaming.events import PipelineEventEmitter
from querymind.streaming.models import (
    HeartbeatEvent,
    PipelineEvent,
    PipelineEventType,
    PipelineFailedEvent,
)
from querymind.streaming.publisher import EventPublisher

_DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 5.0

_TERMINAL_EVENT_TYPES = frozenset(
    {PipelineEventType.PIPELINE_COMPLETED, PipelineEventType.PIPELINE_FAILED}
)


class EventSubscriber:
    """Wraps one `Subscription`, exposing its events as an async iterator.

    Always unsubscribes from the `EventBus` on exit, exactly once, even
    if the consumer stops iterating early or an exception propagates
    through it -- a subscriber that never cleans up is exactly the "leak
    a task/resource" failure rule 8 forbids.
    """

    def __init__(self, event_bus: EventBus, subscription: Subscription) -> None:
        self._event_bus = event_bus
        self._subscription = subscription
        self._closed = False

    async def __aenter__(self) -> EventSubscriber:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            await self._event_bus.unsubscribe(self._subscription)

    async def events(self) -> AsyncIterator[PipelineEvent]:
        """Yield every event published for this subscription's correlation_id, forever --
        the caller decides when to stop (typically on a terminal event type).
        """
        while True:
            yield await self._subscription.queue.get()


async def _emit_heartbeats(
    publisher: EventPublisher,
    correlation_id: str,
    pipeline_task: asyncio.Task[object],
    interval_seconds: float,
) -> None:
    """Publish a `HeartbeatEvent` every `interval_seconds` for as long as `pipeline_task` is
    still running -- never once it has finished. `asyncio.shield` is required here: without
    it, `wait_for`'s own timeout would cancel `pipeline_task` itself the first time it fires,
    since `pipeline_task` is the thing being awaited -- `shield` lets the *wait* time out
    while `pipeline_task` keeps running underneath, exactly rule 5's "heartbeats must not
    interfere with execution."
    """
    started = time.perf_counter()
    while not pipeline_task.done():
        try:
            await asyncio.wait_for(asyncio.shield(pipeline_task), timeout=interval_seconds)
        except TimeoutError:
            elapsed_ms = (time.perf_counter() - started) * 1000
            await publisher.publish(
                HeartbeatEvent.create(correlation_id=correlation_id, elapsed_ms=elapsed_ms)
            )
        except (Exception, asyncio.CancelledError):
            # `pipeline_task` itself finished (successfully, by raising, or by being
            # cancelled) during this wait -- either way, nothing left to heartbeat for.
            return


async def stream_pipeline_events(
    *,
    query_mind_engine: QueryMindEngine,
    event_bus: EventBus,
    question: str,
    correlation_id: str,
    logger: Logger,
    heartbeat_interval_seconds: float = _DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
) -> AsyncGenerator[PipelineEvent, None]:
    """Run `question` through `query_mind_engine.ask`, yielding every `PipelineEvent` it
    publishes -- plus periodic `HeartbeatEvent`s once the run has taken a while -- until a
    terminal event arrives.

    Transport-agnostic: `querymind.streaming.sse`/`.websocket` both just
    iterate this. If the consumer stops iterating early (a client
    disconnect closes this async generator), the `finally` block cancels
    the still-running pipeline task and the heartbeat task and
    unsubscribes -- nothing is ever left running or leaked (rule 8).
    `QueryMindEngine.ask` never raises and always publishes a terminal
    event itself before returning, so the defensive branch below (racing
    the next queued event against `pipeline_task`'s own completion, and
    synthesizing a `PipelineFailedEvent` if it finished without ever
    publishing one) only matters if that contract is somehow violated --
    but "always emit a final event before closing" (the spec's Error
    Handling rule) must hold regardless.
    """
    subscription = await event_bus.subscribe(correlation_id)
    publisher = EventPublisher(event_bus)
    emitter = PipelineEventEmitter(publisher, correlation_id=correlation_id)

    pipeline_task: asyncio.Task[object] = asyncio.create_task(
        query_mind_engine.ask(question, event_publisher=emitter)
    )
    heartbeat_task = asyncio.create_task(
        _emit_heartbeats(publisher, correlation_id, pipeline_task, heartbeat_interval_seconds)
    )

    get_event_task: asyncio.Task[PipelineEvent] | None = None
    try:
        while True:
            get_event_task = asyncio.ensure_future(subscription.queue.get())
            done, _pending = await asyncio.wait(
                {get_event_task, pipeline_task}, return_when=asyncio.FIRST_COMPLETED
            )

            if get_event_task in done:
                event = get_event_task.result()
                yield event
                if event.event_type in (
                    PipelineEventType.PIPELINE_COMPLETED,
                    PipelineEventType.PIPELINE_FAILED,
                ):
                    return
                continue

            # `pipeline_task` finished without ever publishing a terminal event -- see the
            # docstring's note on `QueryMindEngine.ask`'s contract.
            get_event_task.cancel()
            pipeline_exc = pipeline_task.exception() if not pipeline_task.cancelled() else None
            if pipeline_exc is not None:
                logger.error(
                    "streaming_pipeline_task_raised_unexpectedly",
                    correlation_id=correlation_id,
                    error=pipeline_exc,
                )
                yield PipelineFailedEvent.create(correlation_id=correlation_id, error=pipeline_exc)
            return
    finally:
        heartbeat_task.cancel()
        if not pipeline_task.done():
            pipeline_task.cancel()
        pending_cleanup = [pipeline_task, heartbeat_task]
        if get_event_task is not None and not get_event_task.done():
            get_event_task.cancel()
            pending_cleanup.append(get_event_task)
        await asyncio.gather(*pending_cleanup, return_exceptions=True)
        await event_bus.unsubscribe(subscription)
