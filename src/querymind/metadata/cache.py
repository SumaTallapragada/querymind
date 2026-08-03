"""In-memory cache abstraction for the loaded `DatabaseMetadata` snapshot.

Metadata rarely changes — it's re-derived from the SQLAlchemy registry,
not from live data — so there is no TTL, no expiry, and no distributed
cache here: just a single cached value that `MetadataRegistry.load()`
reuses until something explicitly calls `refresh()`. Defined as a
`Protocol` so `MetadataRegistry` depends on the interface, not a concrete
implementation — a test can inject a fake cache (or none at all) without
this module knowing about it.
"""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar

T = TypeVar("T")


class MetadataCache(Protocol[T]):
    """Interface for a single-value cache holding the latest metadata snapshot."""

    def get(self) -> T | None:
        """Return the cached value, or `None` if nothing has been cached yet."""
        ...

    def set(self, value: T) -> None:
        """Store `value` as the cached value, replacing whatever was there."""
        ...

    def clear(self) -> None:
        """Discard the cached value, if any."""
        ...

    @property
    def is_populated(self) -> bool:
        """Whether a value is currently cached."""
        ...


class InMemoryMetadataCache(Generic[T]):
    """The default `MetadataCache`: a single value held in a plain attribute.

    No Redis, no disk, no TTL — just process memory. This is deliberately
    the simplest thing that satisfies `MetadataCache`; if a future phase
    needs cross-process sharing, that's a different implementation of the
    same protocol, not a change to `MetadataRegistry`.
    """

    def __init__(self) -> None:
        self._value: T | None = None

    def get(self) -> T | None:
        return self._value

    def set(self, value: T) -> None:
        self._value = value

    def clear(self) -> None:
        self._value = None

    @property
    def is_populated(self) -> bool:
        return self._value is not None
