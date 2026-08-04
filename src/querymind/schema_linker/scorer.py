"""Confidence scoring: maps a `MatchResult` to a single `confidence` number.

Kept separate from `matcher.py` (which only decides *whether* and *how*
two strings match) so the scoring policy — the actual numbers — lives in
one place and can be tuned without touching the matching logic itself.
"""

from __future__ import annotations

from typing import ClassVar

from querymind.schema_linker.matcher import FUZZY_THRESHOLD, MatchResult
from querymind.schema_linker.models import MatchTier


class ConfidenceScorer:
    """Maps a `MatchResult` to a confidence score in `[0.0, 1.0]`.

    Tiers `EXACT`/`BUSINESS_DICTIONARY`/`SYNONYM`/`ALIAS` are exact-
    equality checks on different fields, so each has one fixed
    confidence — there's no "more or less exact" for an exact match, only
    a difference in *which* field justified it. `FUZZY`/`PARTIAL` are
    approximate, so their confidence scales linearly with the measured
    similarity within a documented band, and every value either can
    produce is kept strictly below the lowest exact-tier confidence
    (`ALIAS`) — an approximate match should never outrank a real one.
    """

    _TIER_CONFIDENCE: ClassVar[dict[MatchTier, float]] = {
        MatchTier.EXACT: 1.00,
        MatchTier.BUSINESS_DICTIONARY: 0.92,
        MatchTier.SYNONYM: 0.85,
        MatchTier.ALIAS: 0.78,
    }
    #: FUZZY confidence scales `similarity` from `[FUZZY_THRESHOLD, 1.0]`
    #: to this range.
    _FUZZY_RANGE: ClassVar[tuple[float, float]] = (0.45, 0.70)
    #: PARTIAL confidence scales the containment ratio from `[0.0, 1.0]`
    #: to this range — capped below `_FUZZY_RANGE`'s minimum, so even a
    #: perfect substring match never outscores even the weakest FUZZY match.
    _PARTIAL_RANGE: ClassVar[tuple[float, float]] = (0.25, 0.44)

    def score(self, result: MatchResult) -> float:
        """Return the confidence for `result`, per the tier's documented policy."""
        fixed = self._TIER_CONFIDENCE.get(result.tier)
        if fixed is not None:
            return fixed
        if result.tier is MatchTier.FUZZY:
            return self._scale(result.similarity, FUZZY_THRESHOLD, 1.0, *self._FUZZY_RANGE)
        if result.tier is MatchTier.PARTIAL:
            return self._scale(result.similarity, 0.0, 1.0, *self._PARTIAL_RANGE)
        raise AssertionError(f"unreachable: unscored MatchTier {result.tier}")  # pragma: no cover

    @staticmethod
    def _scale(
        value: float, source_low: float, source_high: float, target_low: float, target_high: float
    ) -> float:
        """Linearly map `value` from `[source_low, source_high]` to `[target_low, target_high]`, clamped."""
        span = source_high - source_low
        fraction = (value - source_low) / span if span else 1.0
        fraction = min(max(fraction, 0.0), 1.0)
        return round(target_low + (target_high - target_low) * fraction, 4)
