"""Cache abstraction for execution results — defined, but deliberately not wired up.

Mirrors `querymind.llm.cache`/`querymind.sql_generation.cache`/
`querymind.sql_validation.cache`/`querymind.sql_repair.cache`'s reasoning
exactly: a `SQLExecutionResult` reflects the database's state at the
instant it ran, so caching it silently risks serving stale rows after
the underlying data changes. `NoOpSQLExecutionCache` satisfies the
`SQLExecutionCache` protocol without caching anything;
`SQLExecutionEngine` does not accept or call a cache at all in this
phase — the package's `ARCHITECTURAL NOTES` also explicitly ask that
caching be deferred, not designed away.
"""

from __future__ import annotations

from typing import Protocol

from querymind.sql_execution.models import SQLExecutionResult


class SQLExecutionCache(Protocol):
    """Interface for a cache of request key -> `SQLExecutionResult`."""

    def get(self, key: str) -> SQLExecutionResult | None:
        """Return the cached result for `key`, or `None` if not cached."""
        ...

    def set(self, key: str, result: SQLExecutionResult) -> None:
        """Store `result` as the cached value for `key`."""
        ...

    def clear(self) -> None:
        """Discard every cached entry."""
        ...


class NoOpSQLExecutionCache:
    """A `SQLExecutionCache` that never caches anything — always a miss, `set` is a no-op."""

    def get(self, key: str) -> SQLExecutionResult | None:
        return None

    def set(self, key: str, result: SQLExecutionResult) -> None:
        return None

    def clear(self) -> None:
        return None
