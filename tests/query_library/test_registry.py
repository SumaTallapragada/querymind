from __future__ import annotations

import pytest

from querymind.query_library.exceptions import ExampleNotFoundError, LibraryNotLoadedError
from querymind.query_library.models import Difficulty, QueryExampleLibrary
from querymind.query_library.registry import QueryLibraryRegistry


def _registry(library: QueryExampleLibrary) -> QueryLibraryRegistry:
    """A registry whose library source is the given fixture — dependency injection, no real file I/O."""
    return QueryLibraryRegistry(library_source=lambda: library)


def test_raises_before_load(sample_library: QueryExampleLibrary) -> None:
    registry = _registry(sample_library)
    with pytest.raises(LibraryNotLoadedError):
        registry.get_example("customer_count")


def test_load_returns_the_library(sample_library: QueryExampleLibrary) -> None:
    registry = _registry(sample_library)
    assert registry.load() == sample_library


def test_load_only_calls_the_source_once(sample_library: QueryExampleLibrary) -> None:
    calls = 0

    def source() -> QueryExampleLibrary:
        nonlocal calls
        calls += 1
        return sample_library

    registry = QueryLibraryRegistry(library_source=source)
    registry.load()
    registry.load()
    assert calls == 1


def test_refresh_always_calls_the_source(sample_library: QueryExampleLibrary) -> None:
    calls = 0

    def source() -> QueryExampleLibrary:
        nonlocal calls
        calls += 1
        return sample_library

    registry = QueryLibraryRegistry(library_source=source)
    registry.load()
    registry.refresh()
    assert calls == 2


def test_get_example_by_id(sample_library: QueryExampleLibrary) -> None:
    registry = _registry(sample_library)
    registry.load()
    example = registry.get_example("customer_count")
    assert example.title == "Total Customer Count"


def test_get_example_missing_raises(sample_library: QueryExampleLibrary) -> None:
    registry = _registry(sample_library)
    registry.load()
    with pytest.raises(ExampleNotFoundError, match="nonexistent"):
        registry.get_example("nonexistent")


def test_list_examples_returns_every_id_in_catalog_order(
    sample_library: QueryExampleLibrary,
) -> None:
    registry = _registry(sample_library)
    registry.load()
    assert registry.list_examples() == (
        "customer_count",
        "top_customers_by_revenue",
        "monthly_revenue_trend",
    )


def test_find_examples_by_predicate(sample_library: QueryExampleLibrary) -> None:
    registry = _registry(sample_library)
    registry.load()
    results = registry.find_examples(lambda e: e.difficulty is Difficulty.BEGINNER)
    assert [e.id for e in results] == ["customer_count"]


def test_search_by_tags(sample_library: QueryExampleLibrary) -> None:
    registry = _registry(sample_library)
    registry.load()
    assert [e.id for e in registry.search_by_tags("top-n")] == ["top_customers_by_revenue"]


def test_search_by_difficulty(sample_library: QueryExampleLibrary) -> None:
    registry = _registry(sample_library)
    registry.load()
    assert [e.id for e in registry.search_by_difficulty(Difficulty.ADVANCED)] == [
        "monthly_revenue_trend"
    ]


def test_search_by_business_concept(sample_library: QueryExampleLibrary) -> None:
    registry = _registry(sample_library)
    registry.load()
    results = registry.search_by_business_concept("top_customer")
    assert [e.id for e in results] == ["top_customers_by_revenue"]


def test_search_by_title(sample_library: QueryExampleLibrary) -> None:
    registry = _registry(sample_library)
    registry.load()
    results = registry.search_by_title("trend")
    assert [e.id for e in results] == ["monthly_revenue_trend"]


def test_search_by_keywords(sample_library: QueryExampleLibrary) -> None:
    registry = _registry(sample_library)
    registry.load()
    results = registry.search_by_keywords(("top", "revenue"))
    assert [e.id for e in results] == ["top_customers_by_revenue"]


def test_refresh_picks_up_a_changed_library() -> None:
    """Confirms search reflects the latest `refresh()`, not a stale cached search index."""
    from querymind.query_library.catalog import build_library
    from querymind.query_library.models import (
        Difficulty,
        QueryContextSummary,
        QueryExample,
        ResultShape,
    )

    def make(tag: str) -> QueryExampleLibrary:
        return build_library(
            [
                QueryExample(
                    id="x",
                    title="X",
                    natural_language_question="x?",
                    normalized_question="x",
                    query_context=QueryContextSummary(intent="count"),
                    gold_sql="SELECT 1;",
                    sql_explanation="x",
                    difficulty=Difficulty.BEGINNER,
                    tags=(tag,),
                    expected_result_description="x",
                    expected_result_shape=ResultShape.SCALAR,
                )
            ]
        )

    libraries = iter([make("alpha"), make("beta")])
    registry = QueryLibraryRegistry(library_source=lambda: next(libraries))

    registry.load()
    assert registry.search_by_tags("beta") == ()

    registry.refresh()
    assert len(registry.search_by_tags("beta")) == 1
