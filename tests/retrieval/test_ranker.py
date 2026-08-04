from __future__ import annotations

import pytest

from querymind.query_library.models import QueryExample
from querymind.retrieval.exceptions import InvalidTopKError
from querymind.retrieval.models import RetrievalScore
from querymind.retrieval.ranker import ExampleRanker

from .conftest import make_example


def _scored(example_id: str, overall_score: float) -> tuple[QueryExample, RetrievalScore]:
    example = make_example(id=example_id)
    score = RetrievalScore(overall_score=overall_score, signal_scores=(), ranking_reason="x")
    return example, score


def test_ranks_by_score_descending() -> None:
    ranker = ExampleRanker()
    scored = [_scored("low", 0.2), _scored("high", 0.9), _scored("mid", 0.5)]
    ranked = ranker.rank(scored, top_k=3)
    assert [example.id for example, _score in ranked] == ["high", "mid", "low"]


def test_truncates_to_top_k() -> None:
    ranker = ExampleRanker()
    scored = [_scored("a", 0.9), _scored("b", 0.8), _scored("c", 0.7)]
    ranked = ranker.rank(scored, top_k=2)
    assert [example.id for example, _score in ranked] == ["a", "b"]


def test_top_k_larger_than_candidate_count_returns_everything() -> None:
    ranker = ExampleRanker()
    scored = [_scored("a", 0.9)]
    ranked = ranker.rank(scored, top_k=5)
    assert len(ranked) == 1


def test_empty_candidates_returns_empty() -> None:
    ranker = ExampleRanker()
    assert ranker.rank([], top_k=5) == ()


def test_tied_scores_are_broken_by_example_id_ascending() -> None:
    ranker = ExampleRanker()
    scored = [_scored("zebra", 0.5), _scored("alpha", 0.5), _scored("mango", 0.5)]
    ranked = ranker.rank(scored, top_k=3)
    assert [example.id for example, _score in ranked] == ["alpha", "mango", "zebra"]


def test_tie_break_is_deterministic_regardless_of_input_order() -> None:
    ranker = ExampleRanker()
    forward = [_scored("alpha", 0.5), _scored("zebra", 0.5)]
    backward = [_scored("zebra", 0.5), _scored("alpha", 0.5)]
    assert ranker.rank(forward, top_k=2) == ranker.rank(backward, top_k=2)


def test_mixed_ties_and_distinct_scores() -> None:
    ranker = ExampleRanker()
    scored = [_scored("b_tied", 0.5), _scored("winner", 0.9), _scored("a_tied", 0.5)]
    ranked = ranker.rank(scored, top_k=3)
    assert [example.id for example, _score in ranked] == ["winner", "a_tied", "b_tied"]


@pytest.mark.parametrize("top_k", [0, -1, -5])
def test_non_positive_top_k_raises(top_k: int) -> None:
    ranker = ExampleRanker()
    with pytest.raises(InvalidTopKError):
        ranker.rank([_scored("a", 0.5)], top_k=top_k)
