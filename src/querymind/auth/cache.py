"""Cache abstraction for user lookups -- defined, but deliberately not wired up.

Mirrors `querymind.sql_execution.cache`/`querymind.llm.cache`/`querymind.sql_generation.cache`/
`querymind.sql_validation.cache`/`querymind.sql_repair.cache`'s reasoning exactly, applied to a
new, security-sensitive risk: caching a `User` lookup (e.g. by id, to avoid a DB round trip on
every authenticated request) would let a just-deactivated (`is_active=False`) or just-deleted
account keep authenticating successfully until the cache entry expires -- a correctness
regression this codebase's established pattern explicitly defers rather than ships with a
half-considered invalidation story. `NoOpAuthenticationCache` satisfies the protocol without
caching anything; `AuthenticationService` does not accept or call a cache at all in Phase 22A.
"""

from __future__ import annotations

from typing import Protocol

from querymind.auth.models import User


class AuthenticationCache(Protocol):
    """Interface for a cache of user id (as a string) -> `User`."""

    def get(self, key: str) -> User | None:
        """Return the cached user for `key`, or `None` if not cached."""
        ...

    def set(self, key: str, user: User) -> None:
        """Store `user` as the cached value for `key`."""
        ...

    def clear(self) -> None:
        """Discard every cached entry."""
        ...


class NoOpAuthenticationCache:
    """An `AuthenticationCache` that never caches anything -- always a miss, `set` is a no-op."""

    def get(self, key: str) -> User | None:
        return None

    def set(self, key: str, user: User) -> None:
        return None

    def clear(self) -> None:
        return None
