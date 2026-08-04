from __future__ import annotations

from querymind.query_library.models import QueryExample
from querymind.retrieval.explanations import ExplanationBuilder
from querymind.retrieval.matcher import ConceptSchemaKeywordMatcher
from querymind.retrieval.scorer import RetrievalScorer
from querymind.schema_linker.models import LinkedQueryContext


def test_build_populates_every_required_field(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    scorer = RetrievalScorer()
    score = scorer.score(linked_context, matching_example)
    builder = ExplanationBuilder(ConceptSchemaKeywordMatcher())
    retrieved = builder.build(linked_context, matching_example, score)

    assert retrieved.example is matching_example
    assert retrieved.overall_score == score.overall_score
    assert retrieved.signal_breakdown == score.signal_scores
    assert retrieved.matched_business_concepts == ("revenue",)
    assert "customers" in retrieved.matched_schema_objects
    assert retrieved.matched_keywords
    assert retrieved.selection_explanation


def test_explanation_mentions_overall_score(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    scorer = RetrievalScorer()
    score = scorer.score(linked_context, matching_example)
    builder = ExplanationBuilder(ConceptSchemaKeywordMatcher())
    retrieved = builder.build(linked_context, matching_example, score)
    assert f"{score.overall_score:.2f}" in retrieved.selection_explanation


def test_explanation_mentions_matched_concepts_when_present(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    scorer = RetrievalScorer()
    score = scorer.score(linked_context, matching_example)
    builder = ExplanationBuilder(ConceptSchemaKeywordMatcher())
    retrieved = builder.build(linked_context, matching_example, score)
    assert "revenue" in retrieved.selection_explanation


def test_no_matches_still_produces_a_readable_explanation(
    linked_context: LinkedQueryContext, unrelated_example: QueryExample
) -> None:
    scorer = RetrievalScorer()
    score = scorer.score(linked_context, unrelated_example)
    builder = ExplanationBuilder(ConceptSchemaKeywordMatcher())
    retrieved = builder.build(linked_context, unrelated_example, score)
    assert retrieved.matched_business_concepts == ()
    assert retrieved.selection_explanation
