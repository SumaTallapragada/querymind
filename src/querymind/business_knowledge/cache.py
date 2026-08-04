"""In-memory cache abstraction for the loaded `BusinessKnowledgeCatalog` snapshot.

The catalog rarely changes — it's re-derived from a static YAML file, not
live data — so there is no TTL, no expiry, and no distributed cache here:
just a single cached value that `BusinessKnowledgeRegistry.load()` reuses
until something explicitly calls `refresh()`. Defined as a `Protocol` so
`BusinessKnowledgeRegistry` depends on the interface, not a concrete
implementation. Mirrors `querymind.metadata.cache` exactly.
"""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar

T = TypeVar("T")


class KnowledgeCache(Protocol[T]):
    """Interface for a single-value cache holding the latest catalog snapshot."""

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


class InMemoryKnowledgeCache(Generic[T]):
    """The default `KnowledgeCache`: a single value held in a plain attribute.

    No Redis, no disk, no TTL — just process memory, the simplest thing
    that satisfies `KnowledgeCache`.
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
