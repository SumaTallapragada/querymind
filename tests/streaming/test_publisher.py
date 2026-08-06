"""Tests for `querymind.streaming.publisher.EventPublisher` -- the thin seam to `EventBus`."""

from __future__ import annotations

from querymind.orchestrator.models import PipelineStage
from querymind.streaming.event_bus import EventBus
from querymind.streaming.models import StageStartedEvent
from querymind.streaming.publisher import EventPublisher

_CORRELATION_ID = "corr-1"


class TestEventPublisher:
    async def test_publish_delegates_to_the_event_bus(self) -> None:
        bus = EventBus()
        subscription = await bus.subscribe(_CORRELATION_ID)
        publisher = EventPublisher(bus)
        event = StageStartedEvent.create(correlation_id=_CORRELATION_ID, stage=PipelineStage.NLU)

        await publisher.publish(event)

        assert subscription.queue.get_nowait() is event

    async def test_never_touches_a_correlation_id_it_was_not_given(self) -> None:
        bus = EventBus()
        subscription = await bus.subscribe("some-other-correlation-id")
        publisher = EventPublisher(bus)

        await publisher.publish(
            StageStartedEvent.create(correlation_id=_CORRELATION_ID, stage=PipelineStage.NLU)
        )

        assert subscription.queue.empty()
