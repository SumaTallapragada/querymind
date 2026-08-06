"""Tests for `querymind.streaming.models` -- `PipelineEvent` and its nine subclasses.

Every subclass's `.create` is checked for the exact `event_type`/`pipeline_stage`/`payload`
shape it should produce; base-model invariants (frozen, `extra="forbid"`, a fresh `event_id`
and `timestamp` per construction) are checked once, against a representative subclass.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from querymind.orchestrator.models import (
    PipelineStage,
    PipelineStatistics,
    PipelineStatus,
    QueryMindResponse,
)
from querymind.streaming.models import (
    ClientDisconnectedEvent,
    HeartbeatEvent,
    PipelineCompletedEvent,
    PipelineEventType,
    PipelineFailedEvent,
    PipelineStartedEvent,
    StageCompletedEvent,
    StageFailedEvent,
    StageStartedEvent,
)

_CORRELATION_ID = "corr-123"


def _response(status: PipelineStatus = PipelineStatus.SUCCESS) -> QueryMindResponse:
    return QueryMindResponse(
        original_question="q",
        statistics=PipelineStatistics(
            total_latency_ms=1.0, stage_timings=(), repair_attempted=False, repair_performed=False
        ),
        status=status,
        error=None if status is PipelineStatus.SUCCESS else "boom",
    )


class TestPipelineEventBaseInvariants:
    def test_is_frozen(self) -> None:
        event = PipelineStartedEvent.create(correlation_id=_CORRELATION_ID, original_question="q")
        with pytest.raises(ValidationError):
            event.correlation_id = "different"  # type: ignore[misc]

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            PipelineStartedEvent(
                correlation_id=_CORRELATION_ID,
                event_type=PipelineEventType.PIPELINE_STARTED,
                unexpected_field="boom",  # type: ignore[call-arg]
            )

    def test_each_construction_gets_a_fresh_event_id(self) -> None:
        first = StageStartedEvent.create(correlation_id=_CORRELATION_ID, stage=PipelineStage.NLU)
        second = StageStartedEvent.create(correlation_id=_CORRELATION_ID, stage=PipelineStage.NLU)
        assert first.event_id != second.event_id

    def test_every_subclass_serializes_to_the_same_six_top_level_keys(self) -> None:
        event = HeartbeatEvent.create(correlation_id=_CORRELATION_ID, elapsed_ms=10.0)
        assert set(event.model_dump().keys()) == {
            "event_id",
            "correlation_id",
            "timestamp",
            "pipeline_stage",
            "event_type",
            "payload",
        }


class TestPipelineStartedEvent:
    def test_shape(self) -> None:
        event = PipelineStartedEvent.create(correlation_id=_CORRELATION_ID, original_question="q?")
        assert event.event_type is PipelineEventType.PIPELINE_STARTED
        assert event.pipeline_stage is None
        assert event.correlation_id == _CORRELATION_ID
        assert event.payload == {"original_question": "q?"}


class TestStageStartedEvent:
    def test_shape(self) -> None:
        event = StageStartedEvent.create(correlation_id=_CORRELATION_ID, stage=PipelineStage.NLU)
        assert event.event_type is PipelineEventType.STAGE_STARTED
        assert event.pipeline_stage is PipelineStage.NLU
        assert event.payload == {}


class TestStageCompletedEvent:
    def test_shape(self) -> None:
        event = StageCompletedEvent.create(
            correlation_id=_CORRELATION_ID, stage=PipelineStage.SQL_GENERATION, duration_ms=12.5
        )
        assert event.event_type is PipelineEventType.STAGE_COMPLETED
        assert event.pipeline_stage is PipelineStage.SQL_GENERATION
        assert event.payload == {"duration_ms": 12.5}


class TestStageFailedEvent:
    def test_shape(self) -> None:
        error = RuntimeError("boom")
        event = StageFailedEvent.create(
            correlation_id=_CORRELATION_ID,
            stage=PipelineStage.SQL_EXECUTION,
            duration_ms=3.0,
            error=error,
        )
        assert event.event_type is PipelineEventType.STAGE_FAILED
        assert event.pipeline_stage is PipelineStage.SQL_EXECUTION
        assert event.payload == {
            "duration_ms": 3.0,
            "error_type": "RuntimeError",
            "error_message": "boom",
        }


class TestPipelineCompletedEvent:
    def test_a_successful_response_carries_the_business_answer_payload_shape(self) -> None:
        event = PipelineCompletedEvent.create(correlation_id=_CORRELATION_ID, response=_response())
        assert event.event_type is PipelineEventType.PIPELINE_COMPLETED
        assert event.pipeline_stage is None
        assert event.payload["status"] == "success"
        assert event.payload["error"] is None

    def test_a_soft_failure_response_carries_the_error_and_no_business_answer(self) -> None:
        event = PipelineCompletedEvent.create(
            correlation_id=_CORRELATION_ID, response=_response(PipelineStatus.FAILED)
        )
        assert event.payload["status"] == "failed"
        assert event.payload["error"] == "boom"
        assert event.payload["business_answer"] is None


class TestPipelineFailedEvent:
    def test_shape(self) -> None:
        error = ValueError("nope")
        event = PipelineFailedEvent.create(correlation_id=_CORRELATION_ID, error=error)
        assert event.event_type is PipelineEventType.PIPELINE_FAILED
        assert event.pipeline_stage is None
        assert event.payload == {"error_type": "ValueError", "error_message": "nope"}

    def test_may_carry_the_failing_stage(self) -> None:
        event = PipelineFailedEvent.create(
            correlation_id=_CORRELATION_ID, error=ValueError("x"), stage=PipelineStage.SQL_REPAIR
        )
        assert event.pipeline_stage is PipelineStage.SQL_REPAIR


class TestHeartbeatEvent:
    def test_shape(self) -> None:
        event = HeartbeatEvent.create(correlation_id=_CORRELATION_ID, elapsed_ms=4200.0)
        assert event.event_type is PipelineEventType.HEARTBEAT
        assert event.pipeline_stage is None
        assert event.payload == {"elapsed_ms": 4200.0}


class TestClientDisconnectedEvent:
    def test_shape(self) -> None:
        event = ClientDisconnectedEvent.create(correlation_id=_CORRELATION_ID)
        assert event.event_type is PipelineEventType.CLIENT_DISCONNECTED
        assert event.pipeline_stage is None
        assert event.payload == {}
