"""Tests for `querymind.streaming.subscriber` -- `EventSubscriber` and `stream_pipeline_events`,
the transport-agnostic driver both `sse.py` and `websocket.py` reuse.
"""

from __future__ import annotations

import asyncio

from querymind.observability.logger import StructuredLogger
from querymind.orchestrator.models import PipelineStage
from querymind.streaming.event_bus import EventBus
from querymind.streaming.models import PipelineEventType, StageStartedEvent
from querymind.streaming.subscriber import EventSubscriber, stream_pipeline_events

from .conftest import FakeQueryMindEngine, make_success_response

_CORRELATION_ID = "corr-1"


class TestEventSubscriber:
    async def test_events_yields_everything_published_for_its_correlation_id(self) -> None:
        bus = EventBus()
        subscription = await bus.subscribe(_CORRELATION_ID)
        subscriber = EventSubscriber(bus, subscription)
        event = StageStartedEvent.create(correlation_id=_CORRELATION_ID, stage=PipelineStage.NLU)
        await bus.publish(event)

        received = await subscriber.events().__anext__()

        assert received is event

    async def test_aclose_unsubscribes(self) -> None:
        bus = EventBus()
        subscription = await bus.subscribe(_CORRELATION_ID)
        subscriber = EventSubscriber(bus, subscription)

        await subscriber.aclose()

        assert bus.subscriber_count(_CORRELATION_ID) == 0

    async def test_aclose_is_idempotent(self) -> None:
        bus = EventBus()
        subscription = await bus.subscribe(_CORRELATION_ID)
        subscriber = EventSubscriber(bus, subscription)

        await subscriber.aclose()
        await subscriber.aclose()  # must not raise a second time

    async def test_async_context_manager_unsubscribes_on_exit(self) -> None:
        bus = EventBus()
        subscription = await bus.subscribe(_CORRELATION_ID)

        async with EventSubscriber(bus, subscription):
            assert bus.subscriber_count(_CORRELATION_ID) == 1

        assert bus.subscriber_count(_CORRELATION_ID) == 0


class TestStreamPipelineEvents:
    async def test_yields_every_event_the_engine_publishes_in_order(self) -> None:
        bus = EventBus()
        engine = FakeQueryMindEngine(make_success_response())
        logger = StructuredLogger()

        events = [
            event
            async for event in stream_pipeline_events(
                query_mind_engine=engine,  # type: ignore[arg-type]
                event_bus=bus,
                question="q",
                correlation_id=_CORRELATION_ID,
                logger=logger,
            )
        ]

        assert [e.event_type for e in events] == [
            PipelineEventType.PIPELINE_STARTED,
            PipelineEventType.STAGE_STARTED,
            PipelineEventType.STAGE_COMPLETED,
            PipelineEventType.PIPELINE_COMPLETED,
        ]

    async def test_passes_the_question_through_to_the_engine(self) -> None:
        bus = EventBus()
        engine = FakeQueryMindEngine(make_success_response())
        logger = StructuredLogger()

        async for _ in stream_pipeline_events(
            query_mind_engine=engine,  # type: ignore[arg-type]
            event_bus=bus,
            question="Who are our top customers?",
            correlation_id=_CORRELATION_ID,
            logger=logger,
        ):
            pass

        assert engine.received_questions == ["Who are our top customers?"]

    async def test_unsubscribes_once_the_stream_ends_normally(self) -> None:
        bus = EventBus()
        engine = FakeQueryMindEngine(make_success_response())
        logger = StructuredLogger()

        async for _ in stream_pipeline_events(
            query_mind_engine=engine,  # type: ignore[arg-type]
            event_bus=bus,
            question="q",
            correlation_id=_CORRELATION_ID,
            logger=logger,
        ):
            pass

        assert bus.subscriber_count(_CORRELATION_ID) == 0

    async def test_heartbeats_are_emitted_while_a_stage_is_still_running(self) -> None:
        bus = EventBus()
        engine = FakeQueryMindEngine(
            make_success_response(), delay_seconds=0.05, stages=(PipelineStage.NLU,)
        )
        logger = StructuredLogger()

        event_types = [
            event.event_type
            async for event in stream_pipeline_events(
                query_mind_engine=engine,  # type: ignore[arg-type]
                event_bus=bus,
                question="q",
                correlation_id=_CORRELATION_ID,
                logger=logger,
                heartbeat_interval_seconds=0.01,
            )
        ]

        assert PipelineEventType.HEARTBEAT in event_types
        # The stream must still end on a terminal event, heartbeats notwithstanding.
        assert event_types[-1] is PipelineEventType.PIPELINE_COMPLETED

    async def test_a_pipeline_task_that_violates_the_never_raises_contract_yields_a_synthetic_failure(
        self,
    ) -> None:
        bus = EventBus()
        error = RuntimeError("ask() itself blew up")
        engine = FakeQueryMindEngine(raise_error=error, stages=())
        logger = StructuredLogger()

        events = [
            event
            async for event in stream_pipeline_events(
                query_mind_engine=engine,  # type: ignore[arg-type]
                event_bus=bus,
                question="q",
                correlation_id=_CORRELATION_ID,
                logger=logger,
            )
        ]

        assert events[-1].event_type is PipelineEventType.PIPELINE_FAILED
        assert events[-1].payload["error_type"] == "RuntimeError"
        assert events[-1].payload["error_message"] == "ask() itself blew up"

    async def test_stopping_consumption_early_cancels_the_pipeline_task_and_unsubscribes(
        self,
    ) -> None:
        bus = EventBus()
        engine = FakeQueryMindEngine(delay_seconds=10.0, stages=(PipelineStage.NLU,))
        logger = StructuredLogger()

        generator = stream_pipeline_events(
            query_mind_engine=engine,  # type: ignore[arg-type]
            event_bus=bus,
            question="q",
            correlation_id=_CORRELATION_ID,
            logger=logger,
            heartbeat_interval_seconds=100.0,
        )
        first_event = await generator.__anext__()
        assert first_event.event_type is PipelineEventType.PIPELINE_STARTED

        await generator.aclose()
        await asyncio.sleep(0)

        assert bus.subscriber_count(_CORRELATION_ID) == 0
