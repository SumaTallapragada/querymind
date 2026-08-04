"""Cache abstraction for validation results — defined, but deliberately not wired up.

Mirrors `querymind.llm.cache`/`querymind.sql_generation.cache`'s
reasoning exactly: a `SQLValidationResult` is only correct for as long
as the schema, relationships, and business knowledge it was checked
against haven't changed — silently caching it risks serving a stale
verdict after a metadata refresh. `NoOpSQLValidationCache` satisfies the
`SQLValidationCache` protocol without caching anything;
`SQLValidationEngine` does not accept or call a cache at all in this
phase — a future phase can wire a real implementation in without
changing this abstraction.
"""

from __future__ import annotations

from typing import Protocol

from querymind.sql_validation.models import SQLValidationResult


class SQLValidationCache(Protocol):
    """Interface for a cache of request key -> `SQLValidationResult`."""

    def get(self, key: str) -> SQLValidationResult | None:
        """Return the cached result for `key`, or `None` if not cached."""
        ...

    def set(self, key: str, result: SQLValidationResult) -> None:
        """Store `result` as the cached value for `key`."""
        ...

    def clear(self) -> None:
        """Discard every cached entry."""
        ...


class NoOpSQLValidationCache:
    """A `SQLValidationCache` that never caches anything — always a miss, `set` is a no-op."""

    def get(self, key: str) -> SQLValidationResult | None:
        return None

    def set(self, key: str, result: SQLValidationResult) -> None:
        return None

    def clear(self) -> None:
        return None
