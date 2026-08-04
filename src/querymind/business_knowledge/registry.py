"""The single point of access to the business knowledge catalog.

Every future consumer — a Prompt Builder, a future Schema Linker
integration, an admin UI — is expected to depend on
`BusinessKnowledgeRegistry`, never read `concepts.yaml` directly.
Coordinates three independent pieces this package builds: a catalog
source (`querymind.business_knowledge.catalog.load_catalog` by default),
`ConceptResolver` (rebuilt from whatever's currently loaded), and
`KnowledgeCache` (avoiding re-reading the YAML file on every call) —
without being any of them itself. Mirrors
`querymind.metadata.registry.MetadataRegistry`'s design exactly.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from querymind.business_knowledge.cache import InMemoryKnowledgeCache, KnowledgeCache
from querymind.business_knowledge.catalog import load_catalog
from querymind.business_knowledge.exceptions import ConceptNotFoundError, KnowledgeNotLoadedError
from querymind.business_knowledge.models import (
    BusinessConcept,
    BusinessConceptType,
    BusinessKnowledgeCatalog,
    BusinessMetric,
)
from querymind.business_knowledge.resolver import ConceptResolver


class BusinessKnowledgeRegistry:
    """Loads, caches, and answers questions about the business knowledge catalog.

    Constructed with its dependencies (a catalog source callable,
    optional cache) rather than building them itself — there is no
    module-level singleton anywhere in this package. Callers that want a
    process-wide shared instance are expected to construct one
    `BusinessKnowledgeRegistry` themselves and pass it around, the same
    way `MetadataRegistry` works.
    """

    def __init__(
        self,
        catalog_source: Callable[[], BusinessKnowledgeCatalog] = load_catalog,
        cache: KnowledgeCache[BusinessKnowledgeCatalog] | None = None,
    ) -> None:
        self._catalog_source = catalog_source
        self._cache: KnowledgeCache[BusinessKnowledgeCatalog] = cache or InMemoryKnowledgeCache()

    def load(self) -> BusinessKnowledgeCatalog:
        """Return the loaded catalog, reading it once and reusing the cache thereafter."""
        cached = self._cache.get()
        if cached is not None:
            return cached
        return self.refresh()

    def refresh(self) -> BusinessKnowledgeCatalog:
        """Force re-reading the catalog source, bypassing whatever is cached."""
        catalog = self._catalog_source()
        self._cache.set(catalog)
        return catalog

    def get_concept(self, concept_id: str) -> BusinessConcept:
        """Return one concept by id. Raises `ConceptNotFoundError` if it doesn't exist."""
        catalog = self._require_loaded()
        for concept in catalog.concepts:
            if concept.id == concept_id:
                return concept
        raise ConceptNotFoundError(concept_id)

    def find_concepts(
        self, predicate: Callable[[BusinessConcept], bool]
    ) -> tuple[BusinessConcept, ...]:
        """Return every concept for which `predicate` is true."""
        catalog = self._require_loaded()
        return tuple(concept for concept in catalog.concepts if predicate(concept))

    def list_concepts(self) -> tuple[str, ...]:
        """Return every concept id, in catalog order."""
        catalog = self._require_loaded()
        return tuple(concept.id for concept in catalog.concepts)

    def list_metrics(self) -> tuple[BusinessMetric, ...]:
        """Return every `METRIC`-typed concept, as `BusinessMetric` views."""
        metrics = self.find_concepts(
            lambda concept: concept.concept_type is BusinessConceptType.METRIC
        )
        return tuple(BusinessMetric.from_concept(concept) for concept in metrics)

    def resolve(self, term: str) -> BusinessConcept | None:
        """Resolve one business term to its matching concept, or `None`. See `ConceptResolver.resolve`."""
        return self._resolver().resolve(term)

    def resolve_many(self, terms: Iterable[str]) -> tuple[BusinessConcept, ...]:
        """Resolve every term in `terms`, skipping any that don't match anything."""
        return self._resolver().resolve_many(terms)

    def _resolver(self) -> ConceptResolver:
        return ConceptResolver(self._require_loaded())

    def _require_loaded(self) -> BusinessKnowledgeCatalog:
        loaded = self._cache.get()
        if loaded is None:
            raise KnowledgeNotLoadedError()
        return loaded
