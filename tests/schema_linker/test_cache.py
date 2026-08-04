from __future__ import annotations

from querymind.schema_linker.cache import InMemoryLinkerCache
from querymind.schema_linker.models import LinkCandidate, MatchTier


def _candidate() -> tuple[LinkCandidate, ...]:
    return (
        LinkCandidate(
            table_name="orders",
            column_name="total_amount",
            confidence=0.85,
            matching_reason=MatchTier.SYNONYM,
            candidate_rank=1,
            matched_text="revenue",
        ),
    )


def test_get_returns_none_before_anything_is_cached() -> None:
    cache = InMemoryLinkerCache()
    assert cache.get((False, "revenue")) is None


def test_set_then_get_returns_the_stored_value() -> None:
    cache = InMemoryLinkerCache()
    candidates = _candidate()
    cache.set((False, "revenue"), candidates)
    assert cache.get((False, "revenue")) == candidates


def test_table_and_column_keys_are_independent() -> None:
    cache = InMemoryLinkerCache()
    cache.set((True, "customer"), ())
    assert cache.get((False, "customer")) is None


def test_clear_discards_every_entry() -> None:
    cache = InMemoryLinkerCache()
    cache.set((False, "revenue"), _candidate())
    cache.clear()
    assert cache.get((False, "revenue")) is None
