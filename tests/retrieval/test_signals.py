from __future__ import annotations

from querymind.query_library.models import Difficulty, QueryExample
from querymind.retrieval.matcher import ConceptSchemaKeywordMatcher
from querymind.retrieval.signals import (
    BusinessConceptOverlapSignal,
    ColumnOverlapSignal,
    DifficultySimilaritySignal,
    IntentSimilaritySignal,
    KeywordOverlapSignal,
    SchemaOverlapSignal,
    SQLFeatureOverlapSignal,
    TableOverlapSignal,
)
from querymind.schema_linker.models import LinkedQueryContext

from .conftest import make_example, make_linked_context


def test_intent_similarity_matches() -> None:
    result = IntentSimilaritySignal().compute(make_linked_context(), make_example())
    assert result.score == 1.0


def test_intent_similarity_differs() -> None:
    example = make_example(
        query_context=make_example().query_context.model_copy(update={"intent": "count"})
    )
    result = IntentSimilaritySignal().compute(make_linked_context(), example)
    assert result.score == 0.0


def test_business_concept_overlap(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    signal = BusinessConceptOverlapSignal(ConceptSchemaKeywordMatcher())
    result = signal.compute(linked_context, matching_example)
    assert 0.0 < result.score <= 1.0
    assert "revenue" in result.detail


def test_business_concept_overlap_no_overlap(
    linked_context: LinkedQueryContext, unrelated_example: QueryExample
) -> None:
    signal = BusinessConceptOverlapSignal(ConceptSchemaKeywordMatcher())
    result = signal.compute(linked_context, unrelated_example)
    assert result.score == 0.0


def test_schema_overlap(linked_context: LinkedQueryContext, matching_example: QueryExample) -> None:
    signal = SchemaOverlapSignal(ConceptSchemaKeywordMatcher())
    result = signal.compute(linked_context, matching_example)
    assert result.score > 0.0


def test_table_overlap(linked_context: LinkedQueryContext, matching_example: QueryExample) -> None:
    signal = TableOverlapSignal(ConceptSchemaKeywordMatcher())
    result = signal.compute(linked_context, matching_example)
    assert result.score == 1.0  # both tables fully shared


def test_column_overlap(linked_context: LinkedQueryContext, matching_example: QueryExample) -> None:
    """context has 1 column (orders.total_amount); the example has 2 (that one plus
    customers.customer_id) -> Jaccard = 1/2."""
    signal = ColumnOverlapSignal(ConceptSchemaKeywordMatcher())
    result = signal.compute(linked_context, matching_example)
    assert result.score == 0.5


def test_column_overlap_no_overlap(
    linked_context: LinkedQueryContext, unrelated_example: QueryExample
) -> None:
    signal = ColumnOverlapSignal(ConceptSchemaKeywordMatcher())
    result = signal.compute(linked_context, unrelated_example)
    assert result.score == 0.0


def test_keyword_overlap(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    signal = KeywordOverlapSignal(ConceptSchemaKeywordMatcher())
    result = signal.compute(linked_context, matching_example)
    assert result.score > 0.0


def test_sql_feature_overlap_all_features_present() -> None:
    """linked_context implies JOIN + GROUP BY + aggregate function; matching_example's gold_sql has all three."""
    result = SQLFeatureOverlapSignal().compute(make_linked_context(), make_example())
    assert result.score == 1.0


def test_sql_feature_overlap_no_requirements_is_vacuously_satisfied() -> None:
    """A context resolving only a single table, with no aggregation/sort/filters, implies no
    particular SQL structure — even a trivial `SELECT 1;` can't fail this check."""
    minimal_context = make_linked_context(
        metrics=()
    )  # drop the revenue metric -> single table, no aggregation
    result = SQLFeatureOverlapSignal().compute(minimal_context, make_example(gold_sql="SELECT 1;"))
    assert result.score == 1.0


def test_sql_feature_overlap_missing_features_scores_partially() -> None:
    example = make_example(gold_sql="SELECT * FROM orders;")
    result = SQLFeatureOverlapSignal().compute(make_linked_context(), example)
    assert 0.0 <= result.score < 1.0


def test_difficulty_similarity_exact_match_scores_one() -> None:
    """linked_context's implied complexity (1 join + 1 aggregation = intermediate) matches an
    intermediate example exactly."""
    result = DifficultySimilaritySignal().compute(
        make_linked_context(), make_example(difficulty=Difficulty.INTERMEDIATE)
    )
    assert result.score == 1.0


def test_difficulty_similarity_gives_partial_credit_for_adjacent_levels() -> None:
    close = DifficultySimilaritySignal().compute(
        make_linked_context(), make_example(difficulty=Difficulty.ADVANCED)
    )
    far = DifficultySimilaritySignal().compute(
        make_linked_context(), make_example(difficulty=Difficulty.EXPERT)
    )
    assert 0.0 < far.score < close.score < 1.0
