"""EventPublisher: the thin seam between "something has a `PipelineEvent`" and the `EventBus`
that fans it out.

Deliberately does nothing else -- no knowledge of what a stage is, what
a pipeline is, or who (if anyone) is subscribed. `querymind.streaming.events
.PipelineEventEmitter` is the adapter that actually builds `PipelineEvent`s
from `PipelineRunner`'s stage-by-stage callbacks and calls `publish` here;
`querymind.streaming.subscriber`'s heartbeat loop is `EventPublisher`'s
other caller. Keeping this class this thin is what makes rule 3 ("never
couple business logic to SSE/WebSocket implementations") true by
construction -- a publisher is never given a transport, a request, or a
connection to reach into.
"""

from __future__ import annotations

from querymind.streaming.event_bus import EventBus
from querymind.streaming.models import PipelineEvent


class EventPublisher:
    """Publishes one `PipelineEvent` at a time onto an injected `EventBus`."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def publish(self, event: PipelineEvent) -> None:
        await self._event_bus.publish(event)
