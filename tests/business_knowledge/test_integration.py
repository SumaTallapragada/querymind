"""End-to-end tests against the real shipped `concepts.yaml` catalog.

Unlike the rest of this test package (a small synthetic catalog built
for precise control), these tests exercise `BusinessKnowledgeRegistry`
against the actual catalog shipped with this package — the one every
real caller gets by default.
"""

from __future__ import annotations

import pytest

from querymind.business_knowledge.models import BusinessConceptType
from querymind.business_knowledge.registry import BusinessKnowledgeRegistry


@pytest.fixture(scope="module")
def registry() -> BusinessKnowledgeRegistry:
    registry = BusinessKnowledgeRegistry()
    registry.load()
    return registry


def test_catalog_has_every_ids_unique_and_the_expected_count(
    registry: BusinessKnowledgeRegistry,
) -> None:
    ids = registry.list_concepts()
    assert len(ids) == 22
    assert len(set(ids)) == len(ids)


def test_every_concept_has_the_required_fields_populated(
    registry: BusinessKnowledgeRegistry,
) -> None:
    for concept_id in registry.list_concepts():
        concept = registry.get_concept(concept_id)
        assert concept.id
        assert concept.name
        assert concept.description
        assert concept.calculation_description
        # preferred_schema_objects is optional in the model but every
        # real catalog entry should still ground itself in the schema.
        assert concept.preferred_schema_objects


@pytest.mark.parametrize(
    ("term", "expected_id"),
    [
        ("Revenue", "revenue"),
        ("AOV", "average_order_value"),
        ("CLV", "customer_lifetime_value"),
        ("GMV", "gross_revenue"),
        ("Top Customer", "top_customer"),
        ("Churned Customer", "inactive_customer"),
        ("Star Rating", "review_rating"),
        ("Vendor Performance", "supplier_performance"),
    ],
)
def test_resolves_known_terms_to_the_expected_concept(
    registry: BusinessKnowledgeRegistry, term: str, expected_id: str
) -> None:
    concept = registry.resolve(term)
    assert concept is not None
    assert concept.id == expected_id


def test_resolves_a_synonym_via_related_terms(registry: BusinessKnowledgeRegistry) -> None:
    concept = registry.resolve("Income")
    assert concept is not None
    assert concept.id == "revenue"


def test_list_metrics_only_returns_metric_typed_concepts(
    registry: BusinessKnowledgeRegistry,
) -> None:
    metrics = registry.list_metrics()
    assert len(metrics) > 0
    assert all(m.concept_type is BusinessConceptType.METRIC for m in metrics)
    metric_ids = {m.id for m in metrics}
    assert "revenue" in metric_ids
    assert "top_customer" not in metric_ids  # a SEGMENT, not a METRIC


def test_unresolvable_term_returns_none(registry: BusinessKnowledgeRegistry) -> None:
    assert registry.resolve("completely made up business jargon xyz") is None
