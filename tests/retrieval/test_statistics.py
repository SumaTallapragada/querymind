from __future__ import annotations

from querymind.retrieval.models import RetrievedExample, SignalBreakdown, SignalName
from querymind.retrieval.statistics import RetrievalStatisticsCollector

from .conftest import make_example


def _retrieved(
    overall_score: float, signal_scores: tuple[SignalBreakdown, ...] = ()
) -> RetrievedExample:
    return RetrievedExample(
        example=make_example(),
        overall_score=overall_score,
        signal_breakdown=signal_scores,
        selection_explanation="x",
    )


def test_collect_records_latency_and_top_k() -> None:
    collector = RetrievalStatisticsCollector()
    stats = collector.collect(latency_ms=12.5, top_k=5, candidate_count=25, retrieved=())
    assert stats.retrieval_latency_ms == 12.5
    assert stats.top_k == 5
    assert stats.candidate_count == 25


def test_average_score_is_mean_of_retrieved() -> None:
    collector = RetrievalStatisticsCollector()
    retrieved = (_retrieved(0.8), _retrieved(0.4))
    stats = collector.collect(latency_ms=1.0, top_k=2, candidate_count=10, retrieved=retrieved)
    assert abs(stats.average_score - 0.6) < 1e-9


def test_average_score_is_zero_when_nothing_retrieved() -> None:
    collector = RetrievalStatisticsCollector()
    stats = collector.collect(latency_ms=1.0, top_k=5, candidate_count=0, retrieved=())
    assert stats.average_score == 0.0
    assert stats.signal_contribution == ()


def test_signal_contribution_averages_weighted_scores_across_retrieved() -> None:
    collector = RetrievalStatisticsCollector()
    retrieved = (
        _retrieved(
            0.6,
            (
                SignalBreakdown(
                    signal=SignalName.INTENT_SIMILARITY,
                    score=1.0,
                    weight=0.4,
                    weighted_score=0.4,
                    detail="x",
                ),
            ),
        ),
        _retrieved(
            0.2,
            (
                SignalBreakdown(
                    signal=SignalName.INTENT_SIMILARITY,
                    score=0.0,
                    weight=0.4,
                    weighted_score=0.0,
                    detail="x",
                ),
            ),
        ),
    )
    stats = collector.collect(latency_ms=1.0, top_k=2, candidate_count=10, retrieved=retrieved)
    assert len(stats.signal_contribution) == 1
    assert stats.signal_contribution[0].signal is SignalName.INTENT_SIMILARITY
    assert stats.signal_contribution[0].average_weighted_score == 0.2
