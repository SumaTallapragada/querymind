from __future__ import annotations

from querymind.business_knowledge.cache import InMemoryKnowledgeCache
from querymind.business_knowledge.models import BusinessKnowledgeCatalog


def test_starts_empty() -> None:
    cache: InMemoryKnowledgeCache[BusinessKnowledgeCatalog] = InMemoryKnowledgeCache()
    assert cache.get() is None
    assert cache.is_populated is False


def test_set_then_get_returns_the_stored_value(sample_catalog: BusinessKnowledgeCatalog) -> None:
    cache: InMemoryKnowledgeCache[BusinessKnowledgeCatalog] = InMemoryKnowledgeCache()
    cache.set(sample_catalog)
    assert cache.get() is sample_catalog
    assert cache.is_populated is True


def test_set_replaces_the_previous_value(sample_catalog: BusinessKnowledgeCatalog) -> None:
    from querymind.business_knowledge.catalog import build_catalog

    cache: InMemoryKnowledgeCache[BusinessKnowledgeCatalog] = InMemoryKnowledgeCache()
    cache.set(sample_catalog)
    other = build_catalog(())
    cache.set(other)
    assert cache.get() is other


def test_clear_discards_the_cached_value(sample_catalog: BusinessKnowledgeCatalog) -> None:
    cache: InMemoryKnowledgeCache[BusinessKnowledgeCatalog] = InMemoryKnowledgeCache()
    cache.set(sample_catalog)
    cache.clear()
    assert cache.get() is None
    assert cache.is_populated is False
