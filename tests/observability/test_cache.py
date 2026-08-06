"""Tests for `querymind.observability.cache` — `NoOpObservabilityCache` is always a miss."""

from __future__ import annotations

from datetime import UTC, datetime

from querymind.observability.cache import NoOpObservabilityCache
from querymind.observability.models import MetricsSnapshot


class TestNoOpObservabilityCache:
    def test_get_is_always_a_miss(self) -> None:
        cache: NoOpObservabilityCache[MetricsSnapshot] = NoOpObservabilityCache()
        assert cache.get("any-key") is None

    def test_set_does_not_make_a_subsequent_get_a_hit(self) -> None:
        cache: NoOpObservabilityCache[MetricsSnapshot] = NoOpObservabilityCache()
        snapshot = MetricsSnapshot(
            captured_at=datetime.now(UTC),
            pipeline_run_count=0,
            pipeline_success_count=0,
            pipeline_failure_count=0,
            average_pipeline_latency_ms=0.0,
            validation_failure_count=0,
            repair_attempted_count=0,
            repair_success_count=0,
            repair_success_rate=0.0,
            sql_execution_count=0,
            total_rows_returned=0,
            llm_prompt_tokens=0,
            llm_completion_tokens=0,
            cache_hit_count=0,
            cache_miss_count=0,
        )
        cache.set("key", snapshot)
        assert cache.get("key") is None

    def test_clear_does_not_raise(self) -> None:
        cache: NoOpObservabilityCache[MetricsSnapshot] = NoOpObservabilityCache()
        cache.clear()

    def test_works_generically_for_a_different_artifact_type(self) -> None:
        cache: NoOpObservabilityCache[str] = NoOpObservabilityCache()
        cache.set("key", "some string artifact")
        assert cache.get("key") is None
