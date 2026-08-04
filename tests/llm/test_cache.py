"""Tests for `querymind.llm.cache`."""

from __future__ import annotations

from querymind.llm.cache import NoOpLLMResponseCache
from querymind.llm.models import (
    FinishReason,
    GenerationMetrics,
    LLMProvider,
    LLMResponse,
    TokenUsage,
)


def _response() -> LLMResponse:
    return LLMResponse(
        content="SELECT 1;",
        metrics=GenerationMetrics(
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-5",
            latency_ms=100.0,
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
            retry_count=0,
            finish_reason=FinishReason.COMPLETE,
        ),
    )


class TestNoOpLLMResponseCache:
    def test_get_always_returns_none(self) -> None:
        cache = NoOpLLMResponseCache()
        assert cache.get("any-key") is None

    def test_set_does_not_make_get_return_it(self) -> None:
        cache = NoOpLLMResponseCache()
        cache.set("key", _response())
        assert cache.get("key") is None

    def test_clear_does_not_raise(self) -> None:
        cache = NoOpLLMResponseCache()
        cache.clear()  # should be a harmless no-op
