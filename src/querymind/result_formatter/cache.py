"""Cache abstraction for formatted answers — defined, but deliberately not wired up.

Mirrors `querymind.sql_execution.cache`'s reasoning exactly: a
`BusinessAnswer` reflects the database's state at the instant its
`SQLExecutionResult` ran, so caching it silently risks serving a stale
answer after the underlying data changes. `NoOpResultFormatterCache`
satisfies the `ResultFormatterCache` protocol without caching anything;
`ResultFormatterEngine` does not accept or call a cache at all in this
phase.
"""

from __future__ import annotations

from typing import Protocol

from querymind.result_formatter.models import BusinessAnswer


class ResultFormatterCache(Protocol):
    """Interface for a cache of request key -> `BusinessAnswer`."""

    def get(self, key: str) -> BusinessAnswer | None:
        """Return the cached answer for `key`, or `None` if not cached."""
        ...

    def set(self, key: str, answer: BusinessAnswer) -> None:
        """Store `answer` as the cached value for `key`."""
        ...

    def clear(self) -> None:
        """Discard every cached entry."""
        ...


class NoOpResultFormatterCache:
    """A `ResultFormatterCache` that never caches anything — always a miss, `set` is a no-op."""

    def get(self, key: str) -> BusinessAnswer | None:
        return None

    def set(self, key: str, answer: BusinessAnswer) -> None:
        return None

    def clear(self) -> None:
        return None
