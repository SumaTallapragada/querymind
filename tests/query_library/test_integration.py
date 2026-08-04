"""End-to-end tests against the real shipped `examples.yaml` catalog.

Unlike the rest of this test package (a small synthetic library built
for precise control), these tests exercise `QueryLibraryRegistry` and
`QueryLibraryValidator` against the actual catalog shipped with this
package — the one every real caller gets by default.
"""

from __future__ import annotations

import pytest

from querymind.query_library.loader import DEFAULT_LIBRARY_PATH
from querymind.query_library.models import Difficulty
from querymind.query_library.registry import QueryLibraryRegistry
from querymind.query_library.validator import QueryLibraryValidator


@pytest.fixture(scope="module")
def registry() -> QueryLibraryRegistry:
    registry = QueryLibraryRegistry()
    registry.load()
    return registry


def test_catalog_has_the_expected_count_and_unique_ids(registry: QueryLibraryRegistry) -> None:
    ids = registry.list_examples()
    assert len(ids) == 25
    assert len(set(ids)) == len(ids)


def test_shipped_catalog_passes_validation_with_no_errors() -> None:
    report = QueryLibraryValidator().validate_file(DEFAULT_LIBRARY_PATH)
    assert report.is_valid is True
    assert report.errors == ()


def test_every_example_has_non_empty_gold_sql_and_explanation(
    registry: QueryLibraryRegistry,
) -> None:
    for example_id in registry.list_examples():
        example = registry.get_example(example_id)
        assert example.gold_sql.strip()
        assert example.sql_explanation.strip()
        assert example.expected_result_description.strip()


@pytest.mark.parametrize(
    "domain",
    [
        "customers",
        "orders",
        "payments",
        "products",
        "suppliers",
        "inventory",
        "warehouses",
        "shipments",
        "promotions",
        "reviews",
        "returns",
    ],
)
def test_every_required_domain_has_at_least_one_example(
    registry: QueryLibraryRegistry, domain: str
) -> None:
    assert len(registry.search_by_tags(domain)) >= 1, f"no example tagged {domain!r}"


@pytest.mark.parametrize(
    "technique",
    [
        "financial-metrics",
        "time-based",
        "top-n",
        "trend-analysis",
        "filtering",
        "grouping",
        "joins",
        "aggregation",
    ],
)
def test_every_required_technique_has_at_least_one_example(
    registry: QueryLibraryRegistry, technique: str
) -> None:
    assert len(registry.search_by_tags(technique)) >= 1, f"no example tagged {technique!r}"


def test_search_by_difficulty_covers_every_level(registry: QueryLibraryRegistry) -> None:
    for difficulty in Difficulty:
        assert len(registry.search_by_difficulty(difficulty)) >= 1, f"no {difficulty.value} example"


def test_search_by_business_concept_finds_revenue_examples(registry: QueryLibraryRegistry) -> None:
    results = registry.search_by_business_concept("revenue")
    assert len(results) >= 1
    assert all("revenue" in example.business_concepts for example in results)


def test_search_by_keywords_finds_top_customers_example(registry: QueryLibraryRegistry) -> None:
    results = registry.search_by_keywords(("top", "customers"))
    assert "top_customers_by_revenue" in {example.id for example in results}
