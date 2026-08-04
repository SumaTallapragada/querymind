"""Tests for `querymind.llm.metrics`."""

from __future__ import annotations

from querymind.llm.metrics import InMemoryMetricsCollector
from querymind.llm.models import FinishReason, GenerationMetrics, LLMProvider, TokenUsage


def _metrics(**overrides: object) -> GenerationMetrics:
    defaults: dict[str, object] = {
        "provider": LLMProvider.CLAUDE,
        "model": "claude-sonnet-5",
        "latency_ms": 100.0,
        "token_usage": TokenUsage(prompt_tokens=10, completion_tokens=5),
        "retry_count": 0,
        "finish_reason": FinishReason.COMPLETE,
    }
    defaults.update(overrides)
    return GenerationMetrics(**defaults)  # type: ignore[arg-type]


class TestInMemoryMetricsCollector:
    def test_starts_empty(self) -> None:
        collector = InMemoryMetricsCollector()
        assert collector.all() == ()

    def test_record_appends(self) -> None:
        collector = InMemoryMetricsCollector()
        metrics = _metrics()
        collector.record(metrics)
        assert collector.all() == (metrics,)

    def test_records_are_kept_in_order(self) -> None:
        collector = InMemoryMetricsCollector()
        first = _metrics(latency_ms=1.0)
        second = _metrics(latency_ms=2.0)
        collector.record(first)
        collector.record(second)
        assert collector.all() == (first, second)

    def test_all_returns_a_tuple_snapshot(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.record(_metrics())
        result = collector.all()
        assert isinstance(result, tuple)
