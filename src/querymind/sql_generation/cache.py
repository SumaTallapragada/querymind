"""Cache abstraction for generated SQL — defined, but deliberately not wired up.

Mirrors `querymind.llm.cache`'s reasoning exactly: every `GeneratedSQL`
wraps one LLM call, and an LLM call is not generally safe to cache
silently (temperature > 0 makes generation non-deterministic even for
an identical prompt, and a cached SQL answer can go stale).
`NoOpGeneratedSQLCache` satisfies the `GeneratedSQLCache` protocol
without caching anything; `SQLGenerationEngine` does not accept or call
a cache at all in this phase — a future phase can wire a real
implementation in without changing this abstraction.
"""

from __future__ import annotations

from typing import Protocol

from querymind.sql_generation.models import GeneratedSQL


class GeneratedSQLCache(Protocol):
    """Interface for a cache of request key -> `GeneratedSQL`."""

    def get(self, key: str) -> GeneratedSQL | None:
        """Return the cached result for `key`, or `None` if not cached."""
        ...

    def set(self, key: str, generated: GeneratedSQL) -> None:
        """Store `generated` as the cached value for `key`."""
        ...

    def clear(self) -> None:
        """Discard every cached entry."""
        ...


class NoOpGeneratedSQLCache:
    """A `GeneratedSQLCache` that never caches anything — always a miss, `set` is a no-op."""

    def get(self, key: str) -> GeneratedSQL | None:
        return None

    def set(self, key: str, generated: GeneratedSQL) -> None:
        return None

    def clear(self) -> None:
        return None
