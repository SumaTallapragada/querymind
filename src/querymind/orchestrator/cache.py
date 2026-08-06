"""Cache abstraction for end-to-end responses — defined, but deliberately not wired up.

Mirrors `querymind.sql_execution.cache`/`querymind.result_formatter.cache`'s
reasoning exactly: a `QueryMindResponse` embeds a `SQLExecutionResult`
that reflects the database's state at the instant it ran, so caching the
whole response silently risks serving a stale answer after the
underlying data changes. `NoOpQueryMindCache` satisfies the
`QueryMindCache` protocol without caching anything; `QueryMindEngine`
does not call it in this phase.
"""

from __future__ import annotations

from typing import Protocol

from querymind.orchestrator.models import QueryMindResponse


class QueryMindCache(Protocol):
    """Interface for a cache of request key -> `QueryMindResponse`."""

    def get(self, key: str) -> QueryMindResponse | None:
        """Return the cached response for `key`, or `None` if not cached."""
        ...

    def set(self, key: str, response: QueryMindResponse) -> None:
        """Store `response` as the cached value for `key`."""
        ...

    def clear(self) -> None:
        """Discard every cached entry."""
        ...


class NoOpQueryMindCache:
    """A `QueryMindCache` that never caches anything — always a miss, `set` is a no-op."""

    def get(self, key: str) -> QueryMindResponse | None:
        return None

    def set(self, key: str, response: QueryMindResponse) -> None:
        return None

    def clear(self) -> None:
        return None
