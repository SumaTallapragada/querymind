from __future__ import annotations

from querymind.query_library.models import QueryExample
from querymind.retrieval.models import SignalName
from querymind.retrieval.scorer import DEFAULT_SIGNAL_WEIGHTS, RetrievalScorer
from querymind.schema_linker.models import LinkedQueryContext


def test_default_weights_sum_to_one() -> None:
    assert abs(sum(DEFAULT_SIGNAL_WEIGHTS.values()) - 1.0) < 1e-9


def test_score_produces_one_breakdown_entry_per_signal(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    scorer = RetrievalScorer()
    score = scorer.score(linked_context, matching_example)
    assert {entry.signal for entry in score.signal_scores} == set(SignalName)


def test_overall_score_is_sum_of_weighted_scores(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    scorer = RetrievalScorer()
    score = scorer.score(linked_context, matching_example)
    expected = sum(entry.weighted_score for entry in score.signal_scores)
    assert abs(score.overall_score - expected) < 1e-9


def test_relevant_example_scores_higher_than_unrelated(
    linked_context: LinkedQueryContext,
    matching_example: QueryExample,
    unrelated_example: QueryExample,
) -> None:
    scorer = RetrievalScorer()
    relevant_score = scorer.score(linked_context, matching_example)
    unrelated_score = scorer.score(linked_context, unrelated_example)
    assert relevant_score.overall_score > unrelated_score.overall_score


def test_ranking_reason_mentions_a_contributing_signal(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    scorer = RetrievalScorer()
    score = scorer.score(linked_context, matching_example)
    assert score.ranking_reason
    assert "no signals matched" not in score.ranking_reason.lower()


def test_custom_weights_are_respected(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    zero_weights = dict.fromkeys(SignalName, 0.0)
    scorer = RetrievalScorer(weights=zero_weights)
    score = scorer.score(linked_context, matching_example)
    assert score.overall_score == 0.0
    assert all(entry.weighted_score == 0.0 for entry in score.signal_scores)


def test_overall_score_never_exceeds_one(
    linked_context: LinkedQueryContext, matching_example: QueryExample
) -> None:
    # Weight everything at 1.0 to stress the upper clamp.
    inflated_weights = dict.fromkeys(SignalName, 1.0)
    scorer = RetrievalScorer(weights=inflated_weights)
    score = scorer.score(linked_context, matching_example)
    assert score.overall_score <= 1.0
