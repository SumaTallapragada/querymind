"""Tests for `querymind.streaming.event_bus.EventBus` -- in-process, fan-out pub/sub."""

from __future__ import annotations

import asyncio

import pytest

from querymind.orchestrator.models import PipelineStage
from querymind.streaming.event_bus import EventBus
from querymind.streaming.exceptions import UnknownSubscriptionError
from querymind.streaming.models import StageStartedEvent

_CORRELATION_ID = "corr-1"


def _event(correlation_id: str = _CORRELATION_ID) -> StageStartedEvent:
    return StageStartedEvent.create(correlation_id=correlation_id, stage=PipelineStage.NLU)


class TestSubscribeAndPublish:
    async def test_a_subscriber_receives_a_published_event(self) -> None:
        bus = EventBus()
        subscription = await bus.subscribe(_CORRELATION_ID)
        event = _event()

        await bus.publish(event)

        received = await asyncio.wait_for(subscription.queue.get(), timeout=1.0)
        assert received is event

    async def test_events_arrive_in_publish_order(self) -> None:
        bus = EventBus()
        subscription = await bus.subscribe(_CORRELATION_ID)
        first, second = _event(), _event()

        await bus.publish(first)
        await bus.publish(second)

        assert await subscription.queue.get() is first
        assert await subscription.queue.get() is second

    async def test_publishing_with_no_subscribers_is_a_silent_no_op(self) -> None:
        bus = EventBus()
        await bus.publish(_event())  # must not raise

    async def test_a_subscriber_never_receives_another_correlation_ids_event(self) -> None:
        bus = EventBus()
        subscription = await bus.subscribe(_CORRELATION_ID)
        await bus.publish(_event(correlation_id="a-different-correlation-id"))

        assert subscription.queue.empty()


class TestFanOut:
    async def test_multiple_subscribers_on_the_same_correlation_id_all_receive_the_event(
        self,
    ) -> None:
        bus = EventBus()
        first_subscription = await bus.subscribe(_CORRELATION_ID)
        second_subscription = await bus.subscribe(_CORRELATION_ID)
        event = _event()

        await bus.publish(event)

        assert await first_subscription.queue.get() is event
        assert await second_subscription.queue.get() is event

    async def test_subscriber_count_reports_every_active_subscriber(self) -> None:
        bus = EventBus()
        assert bus.subscriber_count(_CORRELATION_ID) == 0
        await bus.subscribe(_CORRELATION_ID)
        await bus.subscribe(_CORRELATION_ID)
        assert bus.subscriber_count(_CORRELATION_ID) == 2


class TestUnsubscribe:
    async def test_an_unsubscribed_subscriber_stops_receiving_events(self) -> None:
        bus = EventBus()
        subscription = await bus.subscribe(_CORRELATION_ID)
        await bus.unsubscribe(subscription)

        await bus.publish(_event())

        assert subscription.queue.empty()
        assert bus.subscriber_count(_CORRELATION_ID) == 0

    async def test_unsubscribing_an_unknown_subscription_raises(self) -> None:
        bus = EventBus()
        subscription = await bus.subscribe(_CORRELATION_ID)
        await bus.unsubscribe(subscription)

        with pytest.raises(UnknownSubscriptionError):
            await bus.unsubscribe(subscription)

    async def test_unsubscribing_leaves_other_subscribers_on_the_same_topic_untouched(
        self,
    ) -> None:
        bus = EventBus()
        first_subscription = await bus.subscribe(_CORRELATION_ID)
        second_subscription = await bus.subscribe(_CORRELATION_ID)

        await bus.unsubscribe(first_subscription)
        event = _event()
        await bus.publish(event)

        assert await second_subscription.queue.get() is event
        assert bus.subscriber_count(_CORRELATION_ID) == 1
