"""Tests for `querymind.orchestrator.cache` — `NoOpQueryMindCache` is always a miss."""

from __future__ import annotations

from querymind.orchestrator.cache import NoOpQueryMindCache
from querymind.orchestrator.models import PipelineStatistics, PipelineStatus, QueryMindResponse


def _response() -> QueryMindResponse:
    return QueryMindResponse(
        original_question="Who are our top customers?",
        statistics=PipelineStatistics(
            total_latency_ms=1.0, stage_timings=(), repair_attempted=False, repair_performed=False
        ),
        status=PipelineStatus.FAILED,
        error="not run",
    )


class TestNoOpQueryMindCache:
    def test_get_is_always_a_miss(self) -> None:
        cache = NoOpQueryMindCache()
        assert cache.get("any-key") is None

    def test_set_does_not_make_a_subsequent_get_a_hit(self) -> None:
        cache = NoOpQueryMindCache()
        cache.set("key", _response())
        assert cache.get("key") is None

    def test_clear_does_not_raise(self) -> None:
        NoOpQueryMindCache().clear()
