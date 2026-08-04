from __future__ import annotations

import pytest

from querymind.schema_linker.matcher import FUZZY_THRESHOLD, MatchResult
from querymind.schema_linker.models import MatchTier
from querymind.schema_linker.scorer import ConfidenceScorer

_SCORER = ConfidenceScorer()


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        (MatchTier.EXACT, 1.00),
        (MatchTier.BUSINESS_DICTIONARY, 0.92),
        (MatchTier.SYNONYM, 0.85),
        (MatchTier.ALIAS, 0.78),
    ],
)
def test_exact_equality_tiers_have_a_fixed_confidence(tier: MatchTier, expected: float) -> None:
    result = MatchResult(tier=tier, similarity=1.0, matched_text="x")
    assert _SCORER.score(result) == expected


def test_fuzzy_confidence_increases_with_similarity() -> None:
    low = _SCORER.score(MatchResult(MatchTier.FUZZY, FUZZY_THRESHOLD, "x"))
    high = _SCORER.score(MatchResult(MatchTier.FUZZY, 1.0, "x"))
    assert low < high


def test_partial_confidence_increases_with_similarity() -> None:
    low = _SCORER.score(MatchResult(MatchTier.PARTIAL, 0.1, "x"))
    high = _SCORER.score(MatchResult(MatchTier.PARTIAL, 0.9, "x"))
    assert low < high


def test_fuzzy_confidence_never_reaches_the_lowest_exact_tier() -> None:
    """An approximate match must never outrank even the weakest exact-equality tier."""
    perfect_fuzzy = _SCORER.score(MatchResult(MatchTier.FUZZY, 1.0, "x"))
    assert perfect_fuzzy < _SCORER.score(MatchResult(MatchTier.ALIAS, 1.0, "x"))


def test_partial_confidence_never_reaches_fuzzy_confidence() -> None:
    perfect_partial = _SCORER.score(MatchResult(MatchTier.PARTIAL, 1.0, "x"))
    weakest_fuzzy = _SCORER.score(MatchResult(MatchTier.FUZZY, FUZZY_THRESHOLD, "x"))
    assert perfect_partial < weakest_fuzzy
