"""Tests for `querymind.llm.models`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from querymind.llm.models import (
    FinishReason,
    GenerationMetrics,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)


def _request(**overrides: object) -> LLMRequest:
    defaults: dict[str, object] = {
        "prompt": "Write SQL for X.",
        "model": "claude-sonnet-5",
        "temperature": 0.0,
        "max_tokens": 1024,
    }
    defaults.update(overrides)
    return LLMRequest(**defaults)  # type: ignore[arg-type]


def _metrics(**overrides: object) -> GenerationMetrics:
    defaults: dict[str, object] = {
        "provider": LLMProvider.CLAUDE,
        "model": "claude-sonnet-5",
        "latency_ms": 120.0,
        "token_usage": TokenUsage(prompt_tokens=10, completion_tokens=5),
        "retry_count": 0,
        "finish_reason": FinishReason.COMPLETE,
    }
    defaults.update(overrides)
    return GenerationMetrics(**defaults)  # type: ignore[arg-type]


class TestLLMProvider:
    def test_claude_value(self) -> None:
        assert LLMProvider.CLAUDE.value == "claude"

    def test_groq_value(self) -> None:
        assert LLMProvider.GROQ.value == "groq"

    def test_generation_metrics_accepts_groq(self) -> None:
        metrics = _metrics(provider=LLMProvider.GROQ)
        assert metrics.provider is LLMProvider.GROQ


class TestLLMRequest:
    def test_valid_request_constructs(self) -> None:
        request = _request()
        assert request.model == "claude-sonnet-5"

    def test_rejects_empty_prompt(self) -> None:
        with pytest.raises(ValidationError):
            _request(prompt="")

    @pytest.mark.parametrize("temperature", [-0.1, 2.1])
    def test_rejects_temperature_out_of_range(self, temperature: float) -> None:
        with pytest.raises(ValidationError):
            _request(temperature=temperature)

    @pytest.mark.parametrize("temperature", [0.0, 1.0, 1.5, 2.0])
    def test_accepts_temperature_across_the_full_widened_range(self, temperature: float) -> None:
        # Regression lock for the generic (provider-agnostic) temperature range fix: widened
        # from `le=1.0` to `le=2.0` to match `LLMProviderConfig.temperature`/
        # `Settings.llm_temperature` -- otherwise a config that accepted temperature=1.5 would
        # still fail here, inside `LLMAdapter.generate`, when the request is actually built.
        request = _request(temperature=temperature)
        assert request.temperature == temperature

    @pytest.mark.parametrize("max_tokens", [0, -1])
    def test_rejects_non_positive_max_tokens(self, max_tokens: int) -> None:
        with pytest.raises(ValidationError):
            _request(max_tokens=max_tokens)

    def test_is_frozen(self) -> None:
        request = _request()
        with pytest.raises(ValidationError):
            request.model = "other"  # type: ignore[misc]


class TestTokenUsage:
    def test_total_tokens_is_the_sum(self) -> None:
        usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
        assert usage.total_tokens == 15

    def test_total_tokens_with_zero_completion(self) -> None:
        usage = TokenUsage(prompt_tokens=10, completion_tokens=0)
        assert usage.total_tokens == 10

    def test_rejects_negative_counts(self) -> None:
        with pytest.raises(ValidationError):
            TokenUsage(prompt_tokens=-1, completion_tokens=0)


class TestGenerationMetrics:
    def test_valid_metrics_construct(self) -> None:
        metrics = _metrics()
        assert metrics.provider is LLMProvider.CLAUDE
        assert metrics.finish_reason is FinishReason.COMPLETE

    def test_rejects_negative_retry_count(self) -> None:
        with pytest.raises(ValidationError):
            _metrics(retry_count=-1)

    def test_rejects_negative_latency(self) -> None:
        with pytest.raises(ValidationError):
            _metrics(latency_ms=-1.0)


class TestLLMResponse:
    def test_construction(self) -> None:
        response = LLMResponse(content="SELECT 1;", metrics=_metrics())
        assert response.content == "SELECT 1;"

    def test_is_frozen(self) -> None:
        response = LLMResponse(content="SELECT 1;", metrics=_metrics())
        with pytest.raises(ValidationError):
            response.content = "SELECT 2;"  # type: ignore[misc]

    def test_unknown_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LLMResponse(content="x", metrics=_metrics(), bogus="nope")  # type: ignore[call-arg]
