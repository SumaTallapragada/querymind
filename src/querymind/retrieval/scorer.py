"""Combines every signal into one overall, explainable `RetrievalScore`.

`RetrievalScorer` owns the *scoring policy* (which signals run, how much
each counts) — the signals themselves (`querymind.retrieval.signals`)
only know how to measure their own one dimension.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from querymind.business_knowledge.registry import BusinessKnowledgeRegistry
from querymind.query_library.models import QueryExample
from querymind.retrieval.cache import RetrievalCache
from querymind.retrieval.matcher import ConceptSchemaKeywordMatcher
from querymind.retrieval.models import RetrievalScore, SignalBreakdown, SignalName
from querymind.retrieval.signals import (
    BusinessConceptOverlapSignal,
    ColumnOverlapSignal,
    DifficultySimilaritySignal,
    IntentSimilaritySignal,
    KeywordOverlapSignal,
    RetrievalSignal,
    SchemaOverlapSignal,
    SQLFeatureOverlapSignal,
    TableOverlapSignal,
)
from querymind.schema_linker.models import LinkedQueryContext

#: Default relative importance of each signal, summing to 1.0. Business
#: concept overlap counts most (it most directly reflects *what* the
#: question is about); difficulty similarity counts least (a nice-to-have,
#: not a strong relevance indicator on its own).
DEFAULT_SIGNAL_WEIGHTS: Mapping[SignalName, float] = {
    SignalName.BUSINESS_CONCEPT_OVERLAP: 0.20,
    SignalName.TABLE_OVERLAP: 0.15,
    SignalName.COLUMN_OVERLAP: 0.15,
    SignalName.INTENT_SIMILARITY: 0.15,
    SignalName.SCHEMA_OVERLAP: 0.10,
    SignalName.SQL_FEATURE_OVERLAP: 0.10,
    SignalName.KEYWORD_OVERLAP: 0.10,
    SignalName.DIFFICULTY_SIMILARITY: 0.05,
}


def default_signals(matcher: ConceptSchemaKeywordMatcher) -> tuple[RetrievalSignal, ...]:
    """The eight signals `RetrievalScorer` uses when none are explicitly injected."""
    return (
        IntentSimilaritySignal(),
        BusinessConceptOverlapSignal(matcher),
        SchemaOverlapSignal(matcher),
        TableOverlapSignal(matcher),
        ColumnOverlapSignal(matcher),
        SQLFeatureOverlapSignal(),
        KeywordOverlapSignal(matcher),
        DifficultySimilaritySignal(),
    )


class RetrievalScorer:
    """Scores one `QueryExample` against one `LinkedQueryContext` using every configured signal.

    Both `signals` and `weights` are constructor-injected (defaulting to
    `default_signals`/`DEFAULT_SIGNAL_WEIGHTS`) — a caller can add,
    remove, or re-weight signals without touching this class.
    """

    def __init__(
        self,
        business_knowledge: BusinessKnowledgeRegistry | None = None,
        cache: RetrievalCache | None = None,
        signals: Sequence[RetrievalSignal] | None = None,
        weights: Mapping[SignalName, float] | None = None,
    ) -> None:
        matcher = ConceptSchemaKeywordMatcher(business_knowledge=business_knowledge, cache=cache)
        self._signals = tuple(signals) if signals is not None else default_signals(matcher)
        self._weights = dict(weights) if weights is not None else dict(DEFAULT_SIGNAL_WEIGHTS)

    def score(self, context: LinkedQueryContext, example: QueryExample) -> RetrievalScore:
        """Score `example` against `context` across every configured signal."""
        breakdown: list[SignalBreakdown] = []
        for signal in self._signals:
            result = signal.compute(context, example)
            weight = self._weights.get(signal.name, 0.0)
            breakdown.append(
                SignalBreakdown(
                    signal=signal.name,
                    score=result.score,
                    weight=weight,
                    weighted_score=result.score * weight,
                    detail=result.detail,
                )
            )
        overall_score = min(1.0, sum(entry.weighted_score for entry in breakdown))
        return RetrievalScore(
            overall_score=overall_score,
            signal_scores=tuple(breakdown),
            ranking_reason=self._build_ranking_reason(breakdown),
        )

    @staticmethod
    def _build_ranking_reason(breakdown: Sequence[SignalBreakdown]) -> str:
        contributing = [entry for entry in breakdown if entry.score > 0.0]
        if not contributing:
            return "No signals matched; this is a low-confidence, fallback-only candidate."
        top = sorted(contributing, key=lambda entry: -entry.weighted_score)[:2]
        parts = [f"{entry.signal.value.replace('_', ' ')} ({entry.score:.2f})" for entry in top]
        return "Strongest match on " + " and ".join(parts) + "."
