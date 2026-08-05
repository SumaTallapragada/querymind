"""Cache abstraction for repair results — defined, but deliberately not wired up.

Mirrors `querymind.llm.cache`/`querymind.sql_generation.cache`/
`querymind.sql_validation.cache`'s reasoning exactly: a `SQLRepairResult`
wraps one or more non-deterministic LLM calls, so it is not generally
safe to cache silently. `NoOpSQLRepairCache` satisfies the
`SQLRepairCache` protocol without caching anything; `SQLRepairEngine`
does not accept or call a cache at all in this phase.
"""

from __future__ import annotations

from typing import Protocol

from querymind.sql_repair.models import SQLRepairResult


class SQLRepairCache(Protocol):
    """Interface for a cache of request key -> `SQLRepairResult`."""

    def get(self, key: str) -> SQLRepairResult | None:
        """Return the cached result for `key`, or `None` if not cached."""
        ...

    def set(self, key: str, result: SQLRepairResult) -> None:
        """Store `result` as the cached value for `key`."""
        ...

    def clear(self) -> None:
        """Discard every cached entry."""
        ...


class NoOpSQLRepairCache:
    """A `SQLRepairCache` that never caches anything — always a miss, `set` is a no-op."""

    def get(self, key: str) -> SQLRepairResult | None:
        return None

    def set(self, key: str, result: SQLRepairResult) -> None:
        return None

    def clear(self) -> None:
        return None
