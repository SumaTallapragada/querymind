"""Lightweight in-memory caching for concept resolution.

Fuzzy/partial matching scans every table and column in the schema for
every concept — cheap at QueryMind's schema size, but there is no reason
to redo the scan for the same concept twice within one process. Mirrors
`querymind.metadata.cache`'s design: a `Protocol` so
`querymind.schema_linker.candidates.CandidateGenerator` depends on the
cache *interface*, not a concrete implementation, and a plain in-memory
default with no TTL or distributed backing — schema metadata used for
matching doesn't change within a process lifetime any more than the
Metadata Engine's own snapshot does.
"""

from __future__ import annotations

from typing import Protocol

from querymind.schema_linker.models import LinkCandidate

#: `(is_table_lookup, normalized_concept)` — table-level and column-level
#: resolution are cached under separate keys even for the same concept
#: string, since they scan different metadata and can legitimately
#: return different candidates (e.g. `"payment"` matching the `payments`
#: table vs. `payments.payment_method`).
CacheKey = tuple[bool, str]


class LinkerCache(Protocol):
    """Interface for a cache of concept -> ranked-candidates lookups."""

    def get(self, key: CacheKey) -> tuple[LinkCandidate, ...] | None:
        """Return the cached candidates for `key`, or `None` if not cached."""
        ...

    def set(self, key: CacheKey, candidates: tuple[LinkCandidate, ...]) -> None:
        """Store `candidates` as the cached value for `key`."""
        ...

    def clear(self) -> None:
        """Discard every cached entry."""
        ...


class InMemoryLinkerCache:
    """The default `LinkerCache`: a plain `dict` held in process memory."""

    def __init__(self) -> None:
        self._store: dict[CacheKey, tuple[LinkCandidate, ...]] = {}

    def get(self, key: CacheKey) -> tuple[LinkCandidate, ...] | None:
        return self._store.get(key)

    def set(self, key: CacheKey, candidates: tuple[LinkCandidate, ...]) -> None:
        self._store[key] = candidates

    def clear(self) -> None:
        self._store.clear()
