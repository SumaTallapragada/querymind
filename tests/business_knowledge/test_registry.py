from __future__ import annotations

import pytest

from querymind.business_knowledge.exceptions import ConceptNotFoundError, KnowledgeNotLoadedError
from querymind.business_knowledge.models import BusinessConceptType, BusinessKnowledgeCatalog
from querymind.business_knowledge.registry import BusinessKnowledgeRegistry


def _registry(catalog: BusinessKnowledgeCatalog) -> BusinessKnowledgeRegistry:
    """A registry whose catalog source is the given fixture — dependency injection, no real file I/O."""
    return BusinessKnowledgeRegistry(catalog_source=lambda: catalog)


def test_raises_before_load(sample_catalog: BusinessKnowledgeCatalog) -> None:
    registry = _registry(sample_catalog)
    with pytest.raises(KnowledgeNotLoadedError):
        registry.get_concept("revenue")


def test_load_returns_the_catalog(sample_catalog: BusinessKnowledgeCatalog) -> None:
    registry = _registry(sample_catalog)
    assert registry.load() == sample_catalog


def test_load_only_calls_the_source_once(sample_catalog: BusinessKnowledgeCatalog) -> None:
    calls = 0

    def source() -> BusinessKnowledgeCatalog:
        nonlocal calls
        calls += 1
        return sample_catalog

    registry = BusinessKnowledgeRegistry(catalog_source=source)
    registry.load()
    registry.load()
    assert calls == 1


def test_refresh_always_calls_the_source(sample_catalog: BusinessKnowledgeCatalog) -> None:
    calls = 0

    def source() -> BusinessKnowledgeCatalog:
        nonlocal calls
        calls += 1
        return sample_catalog

    registry = BusinessKnowledgeRegistry(catalog_source=source)
    registry.load()
    registry.refresh()
    assert calls == 2


def test_get_concept_by_id(sample_catalog: BusinessKnowledgeCatalog) -> None:
    registry = _registry(sample_catalog)
    registry.load()
    concept = registry.get_concept("revenue")
    assert concept.name == "Revenue"


def test_get_concept_missing_raises(sample_catalog: BusinessKnowledgeCatalog) -> None:
    registry = _registry(sample_catalog)
    registry.load()
    with pytest.raises(ConceptNotFoundError, match="nonexistent"):
        registry.get_concept("nonexistent")


def test_find_concepts_by_predicate(sample_catalog: BusinessKnowledgeCatalog) -> None:
    registry = _registry(sample_catalog)
    registry.load()
    segments = registry.find_concepts(lambda c: c.concept_type is BusinessConceptType.SEGMENT)
    assert [c.id for c in segments] == ["top_customer"]


def test_list_concepts_returns_every_id_in_catalog_order(
    sample_catalog: BusinessKnowledgeCatalog,
) -> None:
    registry = _registry(sample_catalog)
    registry.load()
    assert registry.list_concepts() == (
        "revenue",
        "average_order_value",
        "order_value",
        "top_customer",
    )


def test_list_metrics_returns_only_metric_concepts(
    sample_catalog: BusinessKnowledgeCatalog,
) -> None:
    registry = _registry(sample_catalog)
    registry.load()
    metrics = registry.list_metrics()
    assert {m.id for m in metrics} == {"revenue", "average_order_value", "order_value"}
    assert all(m.concept_type is BusinessConceptType.METRIC for m in metrics)


def test_resolve_delegates_to_the_resolver(sample_catalog: BusinessKnowledgeCatalog) -> None:
    registry = _registry(sample_catalog)
    registry.load()
    concept = registry.resolve("AOV")
    assert concept is not None
    assert concept.id == "average_order_value"


def test_resolve_many_delegates_to_the_resolver(sample_catalog: BusinessKnowledgeCatalog) -> None:
    registry = _registry(sample_catalog)
    registry.load()
    resolved = registry.resolve_many(["Revenue", "AOV", "nonexistent"])
    assert [c.id for c in resolved] == ["revenue", "average_order_value"]


def test_refresh_picks_up_a_changed_catalog() -> None:
    """Confirms `resolve`/`get_concept` reflect the latest `refresh()`, not a stale cached resolver."""
    from querymind.business_knowledge.catalog import build_catalog
    from querymind.business_knowledge.models import BusinessConcept

    first = build_catalog(
        [
            BusinessConcept(
                id="revenue",
                name="Revenue",
                concept_type=BusinessConceptType.METRIC,
                description="x",
                calculation_description="x",
            )
        ]
    )
    second = build_catalog(
        [
            BusinessConcept(
                id="revenue",
                name="Revenue",
                concept_type=BusinessConceptType.METRIC,
                description="x",
                calculation_description="x",
                aliases=["Turnover"],
            )
        ]
    )
    catalogs = iter([first, second])
    registry = BusinessKnowledgeRegistry(catalog_source=lambda: next(catalogs))

    registry.load()
    assert registry.resolve("Turnover") is None

    registry.refresh()
    assert registry.resolve("Turnover") is not None
