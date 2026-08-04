from __future__ import annotations

from querymind.query_library.models import (
    Difficulty,
    QueryContextSummary,
    QueryExample,
    ResultShape,
)
from querymind.retrieval.cache import InMemoryRetrievalCache
from querymind.retrieval.matcher import ConceptSchemaKeywordMatcher, jaccard
from querymind.schema_linker.models import LinkedQueryContext


def test_jaccard_of_identical_sets_is_one() -> None:
    assert jaccard(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0


def test_jaccard_of_disjoint_sets_is_zero() -> None:
    assert jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0


def test_jaccard_of_two_empty_sets_is_zero() -> None:
    """Empty-empty is "no signal," not a perfect match."""
    assert jaccard(frozenset(), frozenset()) == 0.0


def test_jaccard_partial_overlap() -> None:
    assert jaccard(frozenset({"a", "b"}), frozenset({"b", "c"})) == 1 / 3


def test_context_business_concepts(linked_context: LinkedQueryContext) -> None:
    matcher = ConceptSchemaKeywordMatcher()
    assert matcher.context_business_concepts(linked_context) == frozenset({"customer", "revenue"})


def test_context_tables(linked_context: LinkedQueryContext) -> None:
    matcher = ConceptSchemaKeywordMatcher()
    assert matcher.context_tables(linked_context) == frozenset({"customers", "orders"})


def test_context_columns(linked_context: LinkedQueryContext) -> None:
    matcher = ConceptSchemaKeywordMatcher()
    assert matcher.context_columns(linked_context) == frozenset({"orders.total_amount"})


def test_context_schema_objects_is_union_of_tables_and_columns(
    linked_context: LinkedQueryContext,
) -> None:
    matcher = ConceptSchemaKeywordMatcher()
    assert matcher.context_schema_objects(linked_context) == frozenset(
        {"customers", "orders", "orders.total_amount"}
    )


def test_example_features_schema_object_set_includes_bare_table_names(
    matching_example: QueryExample,
) -> None:
    """Regression: the example side must also union in bare table names, matching the context side,
    or a context's table-level-only reference could never match a column-only example."""
    matcher = ConceptSchemaKeywordMatcher()
    features = matcher.example_features(matching_example)
    assert "customers" in features.schema_object_set
    assert "orders.total_amount" in features.schema_object_set


def test_matched_business_concepts(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    matcher = ConceptSchemaKeywordMatcher()
    assert matcher.matched_business_concepts(linked_context, matching_example) == ("revenue",)


def test_matched_schema_objects_finds_table_level_match(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    matcher = ConceptSchemaKeywordMatcher()
    matched = matcher.matched_schema_objects(linked_context, matching_example)
    assert "customers" in matched
    assert "orders.total_amount" in matched


def test_matched_tables_and_columns_are_distinct(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    """Both linked_context and matching_example touch customers *and* orders."""
    matcher = ConceptSchemaKeywordMatcher()
    assert matcher.matched_tables(linked_context, matching_example) == ("customers", "orders")
    assert matcher.matched_columns(linked_context, matching_example) == ("orders.total_amount",)


def test_matched_keywords(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    matcher = ConceptSchemaKeywordMatcher()
    matched = matcher.matched_keywords(linked_context, matching_example)
    assert "revenue" in matched
    assert "customers" in matched
    # stopwords never appear
    assert "who" not in matched
    assert "our" not in matched


def test_no_overlap_produces_empty_matches(
    linked_context: LinkedQueryContext, unrelated_example: QueryExample
) -> None:
    matcher = ConceptSchemaKeywordMatcher()
    assert matcher.matched_business_concepts(linked_context, unrelated_example) == ()
    assert matcher.matched_schema_objects(linked_context, unrelated_example) == ()


def test_example_features_are_cached() -> None:
    cache = InMemoryRetrievalCache()
    matcher = ConceptSchemaKeywordMatcher(cache=cache)
    example = QueryExample(
        id="x",
        title="X",
        natural_language_question="x?",
        normalized_question="x",
        query_context=QueryContextSummary(intent="count"),
        gold_sql="SELECT 1;",
        sql_explanation="x",
        difficulty=Difficulty.BEGINNER,
        expected_result_description="x",
        expected_result_shape=ResultShape.SCALAR,
    )
    first = matcher.example_features(example)
    second = matcher.example_features(example)
    assert first is second
    assert cache.get_example_features("x") is first
