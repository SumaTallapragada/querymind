"""Tests for `querymind.llm.adapter.LLMAdapter`."""

from __future__ import annotations

import pytest

from querymind.llm.adapter import LLMAdapter
from querymind.llm.config import DEFAULT_TEMPERATURE, LLMProviderConfig
from querymind.llm.exceptions import LLMPermanentError, LLMTransientError, RetryExhaustedError
from querymind.llm.metrics import InMemoryMetricsCollector
from querymind.llm.models import (
    FinishReason,
    GenerationMetrics,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
from querymind.llm.providers.base import ProviderClient
from querymind.llm.retry import RetryPolicy
from querymind.prompt_compiler.models import CompiledPrompt

from .conftest import RecordingSleep


class ScriptedProvider:
    """A `ProviderClient` that returns/raises a scripted sequence of outcomes."""

    def __init__(self, outcomes: list[LLMResponse | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _response(*, retry_count: int = 0, content: str = "SELECT 1;") -> LLMResponse:
    return LLMResponse(
        content=content,
        metrics=GenerationMetrics(
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-5",
            latency_ms=100.0,
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
            retry_count=retry_count,
            finish_reason=FinishReason.COMPLETE,
        ),
    )


class TestGenerateBuildsTheRequest:
    def test_builds_an_llm_request_from_config_and_prompt_text(
        self, compiled_prompt: CompiledPrompt, config: LLMProviderConfig
    ) -> None:
        provider = ScriptedProvider([_response()])
        adapter = LLMAdapter(provider, config)
        adapter.generate(compiled_prompt)
        request = provider.requests[0]
        assert request.prompt == compiled_prompt.as_text()
        assert request.model == config.model
        assert request.temperature == config.temperature
        assert request.max_tokens == config.max_tokens


class TestGenerateWithWidenedTemperatureRange:
    """End-to-end regression lock for the temperature-range fix: a config/`Settings` value above
    1.0 (legal for Groq and other OpenAI-compatible providers, previously rejected only because
    `LLMRequest.temperature` still capped at `le=1.0`) must actually reach the provider through
    `LLMAdapter.generate`, not just construct successfully in isolation.
    """

    def test_temperature_1_5_reaches_the_provider_through_generate(
        self, compiled_prompt: CompiledPrompt, groq_config: LLMProviderConfig
    ) -> None:
        config = groq_config.model_copy(update={"temperature": 1.5})
        provider = ScriptedProvider([_response()])
        adapter = LLMAdapter(provider, config)

        response = adapter.generate(compiled_prompt)

        assert response.content == "SELECT 1;"
        assert provider.requests[0].temperature == 1.5

    def test_temperature_2_0_reaches_the_provider_through_generate(
        self, compiled_prompt: CompiledPrompt, groq_config: LLMProviderConfig
    ) -> None:
        config = groq_config.model_copy(update={"temperature": 2.0})
        provider = ScriptedProvider([_response()])
        adapter = LLMAdapter(provider, config)

        adapter.generate(compiled_prompt)

        assert provider.requests[0].temperature == 2.0

    def test_claude_default_temperature_still_reaches_the_provider_unchanged(
        self, compiled_prompt: CompiledPrompt, config: LLMProviderConfig
    ) -> None:
        # `config` (the Claude fixture) is left at its default temperature -- proves the widened
        # upper bound didn't change Claude's own effective behavior at all.
        provider = ScriptedProvider([_response()])
        adapter = LLMAdapter(provider, config)

        adapter.generate(compiled_prompt)

        assert provider.requests[0].temperature == config.temperature == DEFAULT_TEMPERATURE


class TestGenerateSuccess:
    def test_returns_the_provider_response(
        self, compiled_prompt: CompiledPrompt, config: LLMProviderConfig
    ) -> None:
        provider = ScriptedProvider([_response(content="SELECT * FROM customers;")])
        adapter = LLMAdapter(provider, config)
        response = adapter.generate(compiled_prompt)
        assert response.content == "SELECT * FROM customers;"

    def test_records_metrics_on_success(
        self, compiled_prompt: CompiledPrompt, config: LLMProviderConfig
    ) -> None:
        collector = InMemoryMetricsCollector()
        provider = ScriptedProvider([_response()])
        adapter = LLMAdapter(provider, config, metrics_collector=collector)
        adapter.generate(compiled_prompt)
        assert len(collector.all()) == 1


class TestGenerateRetriesTransientFailures:
    def test_retries_then_succeeds_and_reports_the_real_retry_count(
        self, compiled_prompt: CompiledPrompt, config: LLMProviderConfig, no_sleep: RecordingSleep
    ) -> None:
        provider = ScriptedProvider(
            [
                LLMTransientError("rate limited"),
                LLMTransientError("rate limited"),
                _response(retry_count=0),
            ]
        )
        adapter = LLMAdapter(provider, config, retry_policy=RetryPolicy(3, sleep=no_sleep))
        response = adapter.generate(compiled_prompt)
        assert response.metrics.retry_count == 2
        assert len(provider.requests) == 3

    def test_retry_count_is_stamped_onto_the_recorded_metrics(
        self, compiled_prompt: CompiledPrompt, config: LLMProviderConfig, no_sleep: RecordingSleep
    ) -> None:
        collector = InMemoryMetricsCollector()
        provider = ScriptedProvider([LLMTransientError("rate limited"), _response(retry_count=0)])
        adapter = LLMAdapter(
            provider,
            config,
            retry_policy=RetryPolicy(3, sleep=no_sleep),
            metrics_collector=collector,
        )
        adapter.generate(compiled_prompt)
        assert collector.all()[0].retry_count == 1

    def test_raises_retry_exhausted_when_every_attempt_fails(
        self, compiled_prompt: CompiledPrompt, config: LLMProviderConfig, no_sleep: RecordingSleep
    ) -> None:
        provider = ScriptedProvider([LLMTransientError("down")] * 4)
        adapter = LLMAdapter(provider, config, retry_policy=RetryPolicy(3, sleep=no_sleep))
        with pytest.raises(RetryExhaustedError):
            adapter.generate(compiled_prompt)

    def test_uses_config_retry_count_when_no_retry_policy_given(
        self, compiled_prompt: CompiledPrompt, config: LLMProviderConfig
    ) -> None:
        limited_config = config.model_copy(update={"retry_count": 0})
        provider = ScriptedProvider([LLMTransientError("down")])
        adapter = LLMAdapter(provider, limited_config)
        with pytest.raises(RetryExhaustedError) as exc_info:
            adapter.generate(compiled_prompt)
        assert exc_info.value.attempts == 1


class TestGeneratePermanentFailuresAreNotRetried:
    def test_permanent_errors_propagate_immediately(
        self, compiled_prompt: CompiledPrompt, config: LLMProviderConfig
    ) -> None:
        provider = ScriptedProvider([LLMPermanentError("bad request")])
        adapter = LLMAdapter(provider, config)
        with pytest.raises(LLMPermanentError):
            adapter.generate(compiled_prompt)
        assert len(provider.requests) == 1


class TestDependencyInjection:
    def test_default_metrics_collector_is_used_when_none_given(
        self, compiled_prompt: CompiledPrompt, config: LLMProviderConfig
    ) -> None:
        provider = ScriptedProvider([_response()])
        adapter = LLMAdapter(provider, config)
        adapter.generate(compiled_prompt)
        assert len(adapter._metrics_collector.all()) == 1

    def test_accepts_any_provider_client_protocol_implementation(
        self, compiled_prompt: CompiledPrompt, config: LLMProviderConfig
    ) -> None:
        provider: ProviderClient = ScriptedProvider([_response()])
        adapter = LLMAdapter(provider, config)
        response = adapter.generate(compiled_prompt)
        assert response.content == "SELECT 1;"
