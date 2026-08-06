"""Tests for `querymind.streaming.cache.NoOpEventReplayCache` -- defined, not wired up.

Mirrors `tests/orchestrator/test_cache.py`-style precedent (a cache
Protocol's `NoOp` implementation gets exactly enough coverage to prove
it satisfies its own contract, nothing more, since nothing in this
package calls it yet).
"""

from __future__ import annotations

from querymind.orchestrator.models import PipelineStage
from querymind.streaming.cache import NoOpEventReplayCache
from querymind.streaming.models import StageStartedEvent

_CORRELATION_ID = "corr-1"


class TestNoOpEventReplayCache:
    def test_recent_is_always_empty(self) -> None:
        cache = NoOpEventReplayCache()
        assert cache.recent(_CORRELATION_ID) == ()

    def test_append_does_not_make_recent_return_anything(self) -> None:
        cache = NoOpEventReplayCache()
        event = StageStartedEvent.create(correlation_id=_CORRELATION_ID, stage=PipelineStage.NLU)

        cache.append(_CORRELATION_ID, event)

        assert cache.recent(_CORRELATION_ID) == ()

    def test_clear_never_raises_even_with_nothing_buffered(self) -> None:
        NoOpEventReplayCache().clear(_CORRELATION_ID)
