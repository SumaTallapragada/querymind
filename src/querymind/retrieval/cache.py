"""In-memory cache for reusable per-example computations.

Caches `ExampleFeatures` — the derived concept/schema/table/column/
keyword sets `querymind.retrieval.matcher.ConceptSchemaKeywordMatcher`
computes for a `QueryExample` — keyed by `example.id`. These never
change across retrieval calls (the library is static, loaded once), so
recomputing them for every candidate on every `retrieve()` call would be
pure waste.

Deliberately does **not** cache final rankings: a `RetrievedKnowledgeBundle`
depends on the specific `LinkedQueryContext` passed in, which is
different on every call — caching *that* would silently serve a stale
answer to a different question. Only the example-derived, query-independent
half of the computation is reusable, and that is all this module caches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExampleFeatures:
    """Derived, query-independent feature sets for one `QueryExample`."""

    concept_set: frozenset[str]
    schema_object_set: frozenset[str]
    table_set: frozenset[str]
    column_set: frozenset[str]
    keyword_set: frozenset[str]


class RetrievalCache(Protocol):
    """Interface for a cache of `example_id -> ExampleFeatures`."""

    def get_example_features(self, example_id: str) -> ExampleFeatures | None:
        """Return the cached features for `example_id`, or `None` if not cached."""
        ...

    def set_example_features(self, example_id: str, features: ExampleFeatures) -> None:
        """Store `features` as the cached value for `example_id`."""
        ...

    def clear(self) -> None:
        """Discard every cached entry."""
        ...


class InMemoryRetrievalCache:
    """The default `RetrievalCache`: a plain `dict` held in process memory. No Redis, no TTL."""

    def __init__(self) -> None:
        self._store: dict[str, ExampleFeatures] = {}

    def get_example_features(self, example_id: str) -> ExampleFeatures | None:
        return self._store.get(example_id)

    def set_example_features(self, example_id: str, features: ExampleFeatures) -> None:
        self._store[example_id] = features

    def clear(self) -> None:
        self._store.clear()
