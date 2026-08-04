from __future__ import annotations

from querymind.query_library.models import Difficulty, QueryExample
from querymind.query_library.search import QueryExampleSearch


def test_by_title_substring_match(sample_examples: tuple[QueryExample, ...]) -> None:
    """ "Total Customer Count" and "Top 10 Customers by Revenue" both contain "customer"."""
    search = QueryExampleSearch(sample_examples)
    results = search.by_title("customer")
    assert {e.id for e in results} == {"customer_count", "top_customers_by_revenue"}


def test_by_title_is_case_insensitive(sample_examples: tuple[QueryExample, ...]) -> None:
    search = QueryExampleSearch(sample_examples)
    assert search.by_title("REVENUE TREND") != ()


def test_by_tag_exact_match(sample_examples: tuple[QueryExample, ...]) -> None:
    search = QueryExampleSearch(sample_examples)
    results = search.by_tag("top-n")
    assert [e.id for e in results] == ["top_customers_by_revenue"]


def test_by_tag_does_not_partial_match(sample_examples: tuple[QueryExample, ...]) -> None:
    search = QueryExampleSearch(sample_examples)
    assert search.by_tag("top") == ()


def test_by_business_concept(sample_examples: tuple[QueryExample, ...]) -> None:
    search = QueryExampleSearch(sample_examples)
    results = search.by_business_concept("revenue")
    assert {e.id for e in results} == {"top_customers_by_revenue", "monthly_revenue_trend"}


def test_by_difficulty(sample_examples: tuple[QueryExample, ...]) -> None:
    search = QueryExampleSearch(sample_examples)
    assert [e.id for e in search.by_difficulty(Difficulty.ADVANCED)] == ["monthly_revenue_trend"]


def test_by_keywords_requires_all_keywords(sample_examples: tuple[QueryExample, ...]) -> None:
    search = QueryExampleSearch(sample_examples)
    results = search.by_keywords(["top", "10", "customers"])
    assert [e.id for e in results] == ["top_customers_by_revenue"]


def test_by_keywords_is_order_independent(sample_examples: tuple[QueryExample, ...]) -> None:
    search = QueryExampleSearch(sample_examples)
    assert search.by_keywords(["customers", "top"]) == search.by_keywords(["top", "customers"])


def test_by_keywords_with_no_keywords_returns_nothing(
    sample_examples: tuple[QueryExample, ...],
) -> None:
    search = QueryExampleSearch(sample_examples)
    assert search.by_keywords([]) == ()
    assert search.by_keywords(["  "]) == ()


def test_no_match_returns_empty_tuple(sample_examples: tuple[QueryExample, ...]) -> None:
    search = QueryExampleSearch(sample_examples)
    assert search.by_title("nonexistent xyz") == ()
    assert search.by_tag("nonexistent") == ()
    assert search.by_business_concept("nonexistent") == ()
    assert search.by_keywords(["nonexistent"]) == ()
