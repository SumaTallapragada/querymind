"""Collects observability data about one retrieval run.

Kept as a separate pure step from `querymind.retrieval.engine.RetrievalEngine`
so the "what do we measure about a retrieval" policy lives in one place,
independently testable without running a full retrieval.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from querymind.retrieval.models import (
    RetrievalStatistics,
    RetrievedExample,
    SignalContribution,
    SignalName,
)


class RetrievalStatisticsCollector:
    """Builds a `RetrievalStatistics` snapshot from one retrieval run's inputs and results."""

    def collect(
        self,
        *,
        latency_ms: float,
        top_k: int,
        candidate_count: int,
        retrieved: Sequence[RetrievedExample],
    ) -> RetrievalStatistics:
        average_score = (
            sum(example.overall_score for example in retrieved) / len(retrieved)
            if retrieved
            else 0.0
        )
        return RetrievalStatistics(
            retrieval_latency_ms=latency_ms,
            top_k=top_k,
            candidate_count=candidate_count,
            average_score=average_score,
            signal_contribution=self._signal_contribution(retrieved),
        )

    @staticmethod
    def _signal_contribution(
        retrieved: Sequence[RetrievedExample],
    ) -> tuple[SignalContribution, ...]:
        if not retrieved:
            return ()
        totals: dict[SignalName, float] = defaultdict(float)
        for example in retrieved:
            for entry in example.signal_breakdown:
                totals[entry.signal] += entry.weighted_score
        return tuple(
            SignalContribution(signal=signal, average_weighted_score=total / len(retrieved))
            for signal, total in totals.items()
        )
