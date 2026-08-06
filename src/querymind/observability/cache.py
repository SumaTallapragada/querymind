"""Cache abstraction for observability artifacts — defined, but deliberately not wired up.

Mirrors every other phase's `<Phase>Cache` Protocol + `NoOp<Phase>Cache`
pair exactly, with one difference: unlike a single-result-type phase
(e.g. `result_formatter` always produces a `BusinessAnswer`), this
package produces several distinct artifact types (`MetricsSnapshot`,
`BenchmarkReport`, `DiagnosticsReport`, `HealthReport`, `PipelineProfile`)
with no one obvious "the" result — so `ObservabilityCache` is generic
over the cached value type `T` instead of naming one concrete model.
`NoOpObservabilityCache` satisfies it for any `T` without caching
anything; nothing in this package accepts or calls a cache instance.
"""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar

T = TypeVar("T")


class ObservabilityCache(Protocol[T]):
    """Interface for a cache of request key -> some observability artifact `T`."""

    def get(self, key: str) -> T | None:
        """Return the cached value for `key`, or `None` if not cached."""
        ...

    def set(self, key: str, value: T) -> None:
        """Store `value` as the cached value for `key`."""
        ...

    def clear(self) -> None:
        """Discard every cached entry."""
        ...


class NoOpObservabilityCache(Generic[T]):
    """An `ObservabilityCache` that never caches anything — always a miss, `set` is a no-op."""

    def get(self, key: str) -> T | None:
        return None

    def set(self, key: str, value: T) -> None:
        return None

    def clear(self) -> None:
        return None
