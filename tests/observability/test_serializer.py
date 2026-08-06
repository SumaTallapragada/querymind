"""Tests for `querymind.observability.serializer.ObservabilitySerializer`."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import yaml

from querymind.observability.models import MetricsSnapshot
from querymind.observability.serializer import ObservabilitySerializer


def _snapshot() -> MetricsSnapshot:
    return MetricsSnapshot(
        captured_at=datetime(2026, 8, 6, tzinfo=UTC),
        pipeline_run_count=3,
        pipeline_success_count=2,
        pipeline_failure_count=1,
        average_pipeline_latency_ms=120.5,
        validation_failure_count=1,
        repair_attempted_count=1,
        repair_success_count=1,
        repair_success_rate=1.0,
        sql_execution_count=2,
        total_rows_returned=42,
        llm_prompt_tokens=500,
        llm_completion_tokens=100,
        cache_hit_count=0,
        cache_miss_count=0,
    )


class TestToDict:
    def test_returns_json_safe_primitives(self) -> None:
        data = ObservabilitySerializer.to_dict(_snapshot())
        assert data["pipeline_run_count"] == 3
        assert isinstance(data["stage_metrics"], list)


class TestToJson:
    def test_round_trips_through_json(self) -> None:
        text = ObservabilitySerializer.to_json(_snapshot())
        parsed = json.loads(text)
        assert parsed["repair_success_rate"] == 1.0

    def test_indent_is_honored(self) -> None:
        text = ObservabilitySerializer.to_json(_snapshot(), indent=None)
        assert "\n" not in text


class TestToYaml:
    def test_round_trips_through_yaml(self) -> None:
        text = ObservabilitySerializer.to_yaml(_snapshot())
        parsed = yaml.safe_load(text)
        assert parsed["pipeline_success_count"] == 2
