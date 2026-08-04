"""Metrics collection for the LLM Adapter.

Captures exactly what Phase 10B asks for — provider, model, latency,
token usage, retry count, finish reason — as one `GenerationMetrics` per
`LLMAdapter.generate` call. `InMemoryMetricsCollector` is the default,
matching every other Phase's `Protocol` + in-memory-default pattern
(e.g. `querymind.prompt_compiler.cache.PromptCache` /
`InMemoryPromptCache`); a production deployment can inject a collector
that forwards to a real metrics backend without touching `LLMAdapter`.
"""

from __future__ import annotations

from typing import Protocol

from querymind.llm.models import GenerationMetrics


class MetricsCollector(Protocol):
    """Records `GenerationMetrics` from completed `LLMAdapter.generate` calls."""

    def record(self, metrics: GenerationMetrics) -> None:
        """Record one call's metrics."""
        ...

    def all(self) -> tuple[GenerationMetrics, ...]:
        """Return every metrics record collected so far, oldest first."""
        ...


class InMemoryMetricsCollector:
    """The default `MetricsCollector`: an in-process list. No external metrics backend."""

    def __init__(self) -> None:
        self._records: list[GenerationMetrics] = []

    def record(self, metrics: GenerationMetrics) -> None:
        self._records.append(metrics)

    def all(self) -> tuple[GenerationMetrics, ...]:
        return tuple(self._records)
