from __future__ import annotations

from querymind.schema_linker.ambiguity import AmbiguityDetector
from querymind.schema_linker.models import LinkCandidate, MatchTier

_DETECTOR = AmbiguityDetector()


def _candidate(
    table: str,
    column: str | None,
    confidence: float,
    rank: int,
    tier: MatchTier = MatchTier.SYNONYM,
) -> LinkCandidate:
    return LinkCandidate(
        table_name=table,
        column_name=column,
        confidence=confidence,
        matching_reason=tier,
        candidate_rank=rank,
        matched_text=column or table,
    )


def test_no_candidates_is_ambiguous() -> None:
    decision = _DETECTOR.decide(())
    assert decision.is_confident is False
    assert decision.reason is not None
    assert "no candidate" in decision.reason.lower()


def test_single_strong_candidate_is_confident() -> None:
    decision = _DETECTOR.decide((_candidate("orders", "total_amount", 0.92, 1),))
    assert decision.is_confident is True
    assert decision.reason is None


def test_single_weak_candidate_is_ambiguous() -> None:
    """Even an unopposed candidate must clear the minimum confidence bar."""
    decision = _DETECTOR.decide((_candidate("orders", "notes", 0.3, 1, MatchTier.PARTIAL),))
    assert decision.is_confident is False
    assert "below the minimum" in (decision.reason or "")


def test_tied_top_candidates_are_ambiguous() -> None:
    candidates = (
        _candidate("customers", "region", 0.85, 1),
        _candidate("orders", "ship_region", 0.85, 2),
    )
    decision = _DETECTOR.decide(candidates)
    assert decision.is_confident is False
    assert "within" in (decision.reason or "")


def test_clear_margin_between_top_two_is_confident() -> None:
    candidates = (
        _candidate("orders", "total_amount", 1.0, 1, MatchTier.EXACT),
        _candidate("orders", "discount_amount", 0.5, 2, MatchTier.PARTIAL),
    )
    decision = _DETECTOR.decide(candidates)
    assert decision.is_confident is True


def test_margin_comfortably_above_the_threshold_is_confident() -> None:
    candidates = (
        _candidate("orders", "total_amount", 0.75, 1),
        _candidate("orders", "discount_amount", 0.60, 2),
    )
    decision = _DETECTOR.decide(candidates)
    assert decision.is_confident is True


def test_margin_comfortably_below_the_threshold_is_ambiguous() -> None:
    candidates = (
        _candidate("orders", "total_amount", 0.65, 1),
        _candidate("orders", "discount_amount", 0.60, 2),
    )
    decision = _DETECTOR.decide(candidates)
    assert decision.is_confident is False
