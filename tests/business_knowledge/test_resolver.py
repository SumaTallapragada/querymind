from __future__ import annotations

from querymind.business_knowledge.models import BusinessKnowledgeCatalog
from querymind.business_knowledge.resolver import ConceptResolver


def test_exact_match_on_name(sample_catalog: BusinessKnowledgeCatalog) -> None:
    resolver = ConceptResolver(sample_catalog)
    concept = resolver.resolve("Revenue")
    assert concept is not None
    assert concept.id == "revenue"


def test_exact_match_is_case_and_underscore_insensitive(
    sample_catalog: BusinessKnowledgeCatalog,
) -> None:
    resolver = ConceptResolver(sample_catalog)
    assert resolver.resolve("average order value") is not None
    assert resolver.resolve("AVERAGE_ORDER_VALUE") is not None


def test_alias_match(sample_catalog: BusinessKnowledgeCatalog) -> None:
    resolver = ConceptResolver(sample_catalog)
    concept = resolver.resolve("AOV")
    assert concept is not None
    assert concept.id == "average_order_value"


def test_synonym_match_via_related_terms(sample_catalog: BusinessKnowledgeCatalog) -> None:
    resolver = ConceptResolver(sample_catalog)
    concept = resolver.resolve("Sales")
    assert concept is not None
    assert concept.id == "revenue"


def test_partial_match_on_substring(sample_catalog: BusinessKnowledgeCatalog) -> None:
    resolver = ConceptResolver(sample_catalog)
    concept = resolver.resolve("Turno")
    assert concept is not None
    assert concept.id == "revenue"


def test_partial_match_requires_a_minimum_length(sample_catalog: BusinessKnowledgeCatalog) -> None:
    resolver = ConceptResolver(sample_catalog)
    assert resolver.resolve("ov") is None


def test_no_match_returns_none(sample_catalog: BusinessKnowledgeCatalog) -> None:
    resolver = ConceptResolver(sample_catalog)
    assert resolver.resolve("nonexistent_concept_xyz") is None


def test_priority_order_exact_beats_alias_beats_synonym_beats_partial(
    sample_catalog: BusinessKnowledgeCatalog,
) -> None:
    resolver = ConceptResolver(sample_catalog)
    # "Order Value" is the *exact* name of one concept, but is also a
    # substring of a different concept's name ("Average Order Value").
    # EXACT must win regardless of catalog order.
    concept = resolver.resolve("Order Value")
    assert concept is not None
    assert concept.id == "order_value"


def test_partial_match_ties_are_broken_by_catalog_order(
    sample_catalog: BusinessKnowledgeCatalog,
) -> None:
    """ "value" is a substring of both remaining concepts' names — the earlier one in the catalog wins."""
    resolver = ConceptResolver(sample_catalog)
    concept = resolver.resolve("value")
    assert concept is not None
    assert concept.id == "average_order_value"


def test_partial_matching_does_not_search_related_terms(
    sample_catalog: BusinessKnowledgeCatalog,
) -> None:
    """Regression: a term must not partially match a concept purely because that concept's
    `related_terms` happens to reference another concept whose name contains the term."""
    resolver = ConceptResolver(sample_catalog)
    # "revenue"'s related_terms is ("Sales",) — "ales" is a substring of
    # "Sales" but must not partial-match "revenue" through that field.
    concept = resolver.resolve("ales")
    assert concept is None


def test_resolve_many_skips_unmatched_terms(sample_catalog: BusinessKnowledgeCatalog) -> None:
    resolver = ConceptResolver(sample_catalog)
    resolved = resolver.resolve_many(["Revenue", "nonexistent_concept_xyz", "AOV"])
    assert [c.id for c in resolved] == ["revenue", "average_order_value"]


def test_resolve_many_deduplicates_by_concept_id(sample_catalog: BusinessKnowledgeCatalog) -> None:
    resolver = ConceptResolver(sample_catalog)
    resolved = resolver.resolve_many(["Revenue", "Turnover", "Sales"])
    assert [c.id for c in resolved] == ["revenue"]
