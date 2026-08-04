"""Tests for `querymind.llm.providers.claude.ClaudeProvider`."""

from __future__ import annotations

import pytest

from querymind.llm.config import LLMProviderConfig
from querymind.llm.exceptions import LLMConfigurationError, LLMPermanentError, LLMTransientError
from querymind.llm.models import LLMProvider, LLMRequest
from querymind.llm.providers.claude import ClaudeProvider

from .conftest import (
    FakeTransport,
    RaisingTransport,
    make_claude_error_body,
    make_claude_success_body,
    make_config,
)


def _request(**overrides: object) -> LLMRequest:
    defaults: dict[str, object] = {
        "prompt": "Write SQL for the top 10 customers.",
        "model": "claude-sonnet-5",
        "temperature": 0.0,
        "max_tokens": 512,
    }
    defaults.update(overrides)
    return LLMRequest(**defaults)  # type: ignore[arg-type]


class TestConstruction:
    def test_rejects_a_config_for_a_different_provider(self) -> None:
        # `LLMProvider` only has one member today, so a real, validated
        # `LLMProviderConfig` can never carry a non-Claude value -- this
        # guard exists for when a second provider is added. `model_construct`
        # bypasses validation, letting the test reach it anyway.
        config = make_config()
        mismatched = LLMProviderConfig.model_construct(
            **{**config.model_dump(), "provider": "not-claude"}
        )
        with pytest.raises(LLMConfigurationError):
            ClaudeProvider(mismatched)


class TestGenerateSuccess:
    def test_returns_a_parsed_response(self, config: LLMProviderConfig) -> None:
        transport = FakeTransport([(200, make_claude_success_body(text="SELECT 1;"))])
        provider = ClaudeProvider(config, transport=transport)
        response = provider.generate(_request())
        assert response.content == "SELECT 1;"
        assert response.metrics.provider is LLMProvider.CLAUDE

    def test_sends_the_correct_url(self, config: LLMProviderConfig) -> None:
        transport = FakeTransport([(200, make_claude_success_body())])
        provider = ClaudeProvider(config, transport=transport)
        provider.generate(_request())
        assert transport.calls[0]["url"] == f"{config.base_url}/v1/messages"

    def test_sends_the_api_key_header(self, config: LLMProviderConfig) -> None:
        transport = FakeTransport([(200, make_claude_success_body())])
        provider = ClaudeProvider(config, transport=transport)
        provider.generate(_request())
        assert transport.calls[0]["headers"]["x-api-key"] == "test-api-key"

    def test_sends_the_request_parameters_in_the_body(self, config: LLMProviderConfig) -> None:
        transport = FakeTransport([(200, make_claude_success_body())])
        provider = ClaudeProvider(config, transport=transport)
        provider.generate(_request(model="claude-opus-5", temperature=0.7, max_tokens=256))
        body = transport.calls[0]["body"]
        assert body["model"] == "claude-opus-5"
        assert body["temperature"] == 0.7
        assert body["max_tokens"] == 256
        assert body["messages"] == [
            {"role": "user", "content": "Write SQL for the top 10 customers."}
        ]

    def test_measures_latency(self, config: LLMProviderConfig) -> None:
        transport = FakeTransport([(200, make_claude_success_body())])
        provider = ClaudeProvider(config, transport=transport)
        response = provider.generate(_request())
        assert response.metrics.latency_ms >= 0.0

    def test_uses_a_custom_parser_when_given(self, config: LLMProviderConfig) -> None:
        from collections.abc import Mapping
        from typing import Any

        from querymind.llm.models import LLMResponse
        from querymind.llm.providers.claude import ClaudeResponseParser

        class _UppercasingParser(ClaudeResponseParser):
            def parse(self, raw_response: Mapping[str, Any], *, latency_ms: float) -> LLMResponse:
                response = super().parse(raw_response, latency_ms=latency_ms)
                return response.model_copy(update={"content": response.content.upper()})

        transport = FakeTransport([(200, make_claude_success_body(text="select 1;"))])
        provider = ClaudeProvider(config, transport=transport, parser=_UppercasingParser())
        response = provider.generate(_request())
        assert response.content == "SELECT 1;"


class TestGenerateErrors:
    @pytest.mark.parametrize("status_code", [408, 409, 429, 500, 502, 503, 504])
    def test_retryable_status_codes_raise_llm_transient_error(
        self, config: LLMProviderConfig, status_code: int
    ) -> None:
        transport = FakeTransport([(status_code, make_claude_error_body())])
        provider = ClaudeProvider(config, transport=transport)
        with pytest.raises(LLMTransientError):
            provider.generate(_request())

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
    def test_non_retryable_status_codes_raise_llm_permanent_error(
        self, config: LLMProviderConfig, status_code: int
    ) -> None:
        transport = FakeTransport([(status_code, make_claude_error_body())])
        provider = ClaudeProvider(config, transport=transport)
        with pytest.raises(LLMPermanentError):
            provider.generate(_request())

    def test_network_level_failures_from_the_transport_propagate_untouched(
        self, config: LLMProviderConfig
    ) -> None:
        # A real network failure (timeout, DNS, connection reset) is raised by
        # HTTPTransport.post_json as LLMTransientError before any status code
        # exists at all -- ClaudeProvider must let it through as-is, not wrap it.
        transport = RaisingTransport(LLMTransientError("connection reset"))
        provider = ClaudeProvider(config, transport=transport)
        with pytest.raises(LLMTransientError, match="connection reset"):
            provider.generate(_request())

    def test_error_message_includes_the_provider_detail(self, config: LLMProviderConfig) -> None:
        transport = FakeTransport(
            [
                (
                    401,
                    make_claude_error_body(
                        message="invalid x-api-key", error_type="authentication_error"
                    ),
                )
            ]
        )
        provider = ClaudeProvider(config, transport=transport)
        with pytest.raises(LLMPermanentError, match="invalid x-api-key"):
            provider.generate(_request())


class TestDefaultConstruction:
    def test_constructs_its_own_transport_and_parser_when_none_given(
        self, config: LLMProviderConfig
    ) -> None:
        provider = ClaudeProvider(config)
        assert provider is not None
