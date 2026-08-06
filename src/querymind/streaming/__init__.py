"""Streaming — Phase 17.

Exposes `QueryMindEngine.ask`'s progress in real time, over both
Server-Sent Events (`POST /query/stream`) and WebSockets (`/ws/query`),
without generating, validating, repairing, executing, or formatting
anything itself, and without duplicating `PipelineRunner`'s sequencing.

The pieces, in dependency order:

- `models` -- `PipelineEvent` and its nine subclasses: the one wire
  shape both transports serialize.
- `event_bus` -- `EventBus`, an in-process, async, fan-out pub/sub keyed
  by `correlation_id`. No external broker, no persistent subscriptions.
- `publisher` -- `EventPublisher`, the thin seam between "something has
  a `PipelineEvent`" and the bus.
- `events` -- `PipelineEventEmitter`, the adapter that implements
  `querymind.orchestrator.events.StageEventPublisher` (structurally, no
  import the other direction) and turns `PipelineRunner`'s callbacks
  into `PipelineEvent`s via `EventPublisher`.
- `subscriber` -- `EventSubscriber` plus `stream_pipeline_events`, the
  transport-agnostic driver that runs one pipeline call as a background
  task, runs a heartbeat task alongside it, and yields events until a
  terminal one arrives, cleaning up on cancellation/disconnect.
- `serializer` -- `serialize_event`, the one JSON encoding both
  transports use.
- `sse` / `websocket` -- the two thin FastAPI endpoints themselves.
- `cache` -- `EventReplayCache`, defined but not wired up (Phase 17
  stops at "expose progress," not "survive a reconnect").
- `exceptions` -- transport-level failures only; a pipeline failure is
  always a `StageFailedEvent`/`PipelineFailedEvent`, never raised here.

This package never generates, validates, repairs, executes, or formats
SQL, and never sequences pipeline stages itself -- `querymind.orchestrator
.pipeline.PipelineRunner` remains the single source of truth for both.
"""

from __future__ import annotations

from querymind.streaming.cache import EventReplayCache, NoOpEventReplayCache
from querymind.streaming.event_bus import EventBus, Subscription
from querymind.streaming.events import PipelineEventEmitter
from querymind.streaming.exceptions import (
    InvalidStreamRequestError,
    StreamingConfigurationError,
    StreamingError,
    UnknownSubscriptionError,
)
from querymind.streaming.models import (
    ClientDisconnectedEvent,
    HeartbeatEvent,
    PipelineCompletedEvent,
    PipelineEvent,
    PipelineEventType,
    PipelineFailedEvent,
    PipelineStartedEvent,
    StageCompletedEvent,
    StageFailedEvent,
    StageStartedEvent,
)
from querymind.streaming.publisher import EventPublisher
from querymind.streaming.serializer import serialize_event
from querymind.streaming.subscriber import EventSubscriber, stream_pipeline_events

__all__ = [
    "ClientDisconnectedEvent",
    "EventBus",
    "EventPublisher",
    "EventReplayCache",
    "EventSubscriber",
    "HeartbeatEvent",
    "InvalidStreamRequestError",
    "NoOpEventReplayCache",
    "PipelineCompletedEvent",
    "PipelineEvent",
    "PipelineEventEmitter",
    "PipelineEventType",
    "PipelineFailedEvent",
    "PipelineStartedEvent",
    "StageCompletedEvent",
    "StageFailedEvent",
    "StageStartedEvent",
    "StreamingConfigurationError",
    "StreamingError",
    "Subscription",
    "UnknownSubscriptionError",
    "serialize_event",
    "stream_pipeline_events",
]
