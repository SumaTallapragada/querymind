"""Tests for `querymind.streaming.serializer.serialize_event` -- the one JSON encoding both
SSE and WebSocket frames share.
"""

from __future__ import annotations

import json

from querymind.orchestrator.models import PipelineStage
from querymind.streaming.models import PipelineEvent, PipelineEventType, StageCompletedEvent
from querymind.streaming.serializer import serialize_event


class TestSerializeEvent:
    def test_returns_valid_json(self) -> None:
        event = StageCompletedEvent.create(
            correlation_id="corr-1", stage=PipelineStage.NLU, duration_ms=2.5
        )
        parsed = json.loads(serialize_event(event))
        assert parsed["correlation_id"] == "corr-1"
        assert parsed["event_type"] == "stage_completed"
        assert parsed["pipeline_stage"] == "nlu"
        assert parsed["payload"] == {"duration_ms": 2.5}

    def test_round_trips_through_the_same_model(self) -> None:
        event = StageCompletedEvent.create(
            correlation_id="corr-2", stage=PipelineStage.SQL_VALIDATION, duration_ms=9.0
        )
        restored = StageCompletedEvent.model_validate_json(serialize_event(event))
        assert restored == event

    def test_every_event_type_serializes_without_error(self) -> None:
        for event_type in PipelineEventType:
            event = PipelineEvent(correlation_id="corr-3", event_type=event_type)
            assert event_type.value in serialize_event(event)
