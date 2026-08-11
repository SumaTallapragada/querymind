"""Tests for `querymind.llm.providers.groq.GroqProvider`. Mirrors
`test_providers_claude.py`'s structure and coverage exactly -- the same shape of tests, against
Groq's own (OpenAI-compatible) request/response contract instead of Claude's.
"""

from __future__ import annotations

import pytest

from querymind.llm.config import LLMProviderConfig
from querymind.llm.exceptions import LLMConfigurationError, LLMPermanentError, LLMTransientError
from querymind.llm.models import FinishReason, LLMProvider, LLMRequest
from querymind.llm.providers.groq import GroqProvider

from .conftest import (
    FakeTransport,
    RaisingTransport,
    make_groq_error_body,
    make_groq_success_body,
)


def _request(**overrides: object) -> LLMRequest:
    defaults: dict[str, object] = {
        "prompt": "Write SQL for the top 10 customers.",
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.0,
        "max_tokens": 512,
    }
    defaults.update(overrides)
    return LLMRequest(**defaults)  # type: ignore[arg-type]


class TestConstruction:
    def test_accepts_a_valid_groq_config(self, groq_config: LLMProviderConfig) -> None:
        provider = GroqProvider(groq_config)
        assert provider is not None

    def test_rejects_a_config_for_a_different_provider(self, config: LLMProviderConfig) -> None:
        # `config` (from conftest) is a Claude config -- constructing a GroqProvider from it
        # must fail loudly, not silently send Claude credentials to Groq's API or vice versa.
        with pytest.raises(LLMConfigurationError):
            GroqProvider(config)


class TestGenerateSuccess:
    def test_returns_a_parsed_response(self, groq_config: LLMProviderConfig) -> None:
        transport = FakeTransport([(200, make_groq_success_body(text="SELECT 1;"))])
        provider = GroqProvider(groq_config, transport=transport)
        response = provider.generate(_request())
        assert response.content == "SELECT 1;"
        assert response.metrics.provider is LLMProvider.GROQ

    def test_sends_the_correct_url(self, groq_config: LLMProviderConfig) -> None:
        transport = FakeTransport([(200, make_groq_success_body())])
        provider = GroqProvider(groq_config, transport=transport)
        provider.generate(_request())
        assert transport.calls[0]["url"] == f"{groq_config.base_url}/chat/completions"

    def test_sends_the_authorization_header(self, groq_config: LLMProviderConfig) -> None:
        transport = FakeTransport([(200, make_groq_success_body())])
        provider = GroqProvider(groq_config, transport=transport)
        provider.generate(_request())
        assert transport.calls[0]["headers"]["authorization"] == "Bearer test-groq-api-key"

    def test_sends_the_request_parameters_in_the_body(self, groq_config: LLMProviderConfig) -> None:
        transport = FakeTransport([(200, make_groq_success_body())])
        provider = GroqProvider(groq_config, transport=transport)
        provider.generate(_request(model="llama-3.1-8b-instant", temperature=0.7, max_tokens=256))
        body = transport.calls[0]["body"]
        assert body["model"] == "llama-3.1-8b-instant"
        assert body["temperature"] == 0.7
        # Groq (OpenAI-compatible) uses max_completion_tokens, not max_tokens -- the whole
        # point of this test: the field name is a Groq-specific implementation detail this
        # provider must translate, not something LLMRequest itself knows about.
        assert body["max_completion_tokens"] == 256
        assert "max_tokens" not in body
        assert body["messages"] == [
            {"role": "user", "content": "Write SQL for the top 10 customers."}
        ]

    def test_parses_token_usage(self, groq_config: LLMProviderConfig) -> None:
        transport = FakeTransport(
            [(200, make_groq_success_body(prompt_tokens=42, completion_tokens=17))]
        )
        provider = GroqProvider(groq_config, transport=transport)
        response = provider.generate(_request())
        assert response.metrics.token_usage.prompt_tokens == 42
        assert response.metrics.token_usage.completion_tokens == 17

    @pytest.mark.parametrize(
        ("groq_finish_reason", "expected"),
        [
            ("stop", FinishReason.COMPLETE),
            ("length", FinishReason.MAX_TOKENS),
            ("content_filter", FinishReason.CONTENT_FILTER),
            ("tool_calls", FinishReason.ERROR),
            ("something_unrecognized", FinishReason.ERROR),
        ],
    )
    def test_maps_finish_reason(
        self, groq_config: LLMProviderConfig, groq_finish_reason: str, expected: FinishReason
    ) -> None:
        transport = FakeTransport([(200, make_groq_success_body(finish_reason=groq_finish_reason))])
        provider = GroqProvider(groq_config, transport=transport)
        response = provider.generate(_request())
        assert response.metrics.finish_reason is expected

    def test_measures_latency(self, groq_config: LLMProviderConfig) -> None:
        transport = FakeTransport([(200, make_groq_success_body())])
        provider = GroqProvider(groq_config, transport=transport)
        response = provider.generate(_request())
        assert response.metrics.latency_ms >= 0.0

    def test_uses_a_custom_parser_when_given(self, groq_config: LLMProviderConfig) -> None:
        from collections.abc import Mapping
        from typing import Any

        from querymind.llm.models import LLMResponse
        from querymind.llm.providers.groq import GroqResponseParser

        class _UppercasingParser(GroqResponseParser):
            def parse(self, raw_response: Mapping[str, Any], *, latency_ms: float) -> LLMResponse:
                response = super().parse(raw_response, latency_ms=latency_ms)
                return response.model_copy(update={"content": response.content.upper()})

        transport = FakeTransport([(200, make_groq_success_body(text="select 1;"))])
        provider = GroqProvider(groq_config, transport=transport, parser=_UppercasingParser())
        response = provider.generate(_request())
        assert response.content == "SELECT 1;"


class TestGenerateErrors:
    @pytest.mark.parametrize("status_code", [408, 409, 429, 500, 502, 503, 504])
    def test_retryable_status_codes_raise_llm_transient_error(
        self, groq_config: LLMProviderConfig, status_code: int
    ) -> None:
        transport = FakeTransport([(status_code, make_groq_error_body())])
        provider = GroqProvider(groq_config, transport=transport)
        with pytest.raises(LLMTransientError):
            provider.generate(_request())

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
    def test_non_retryable_status_codes_raise_llm_permanent_error(
        self, groq_config: LLMProviderConfig, status_code: int
    ) -> None:
        transport = FakeTransport([(status_code, make_groq_error_body())])
        provider = GroqProvider(groq_config, transport=transport)
        with pytest.raises(LLMPermanentError):
            provider.generate(_request())

    def test_network_level_failures_from_the_transport_propagate_untouched(
        self, groq_config: LLMProviderConfig
    ) -> None:
        transport = RaisingTransport(LLMTransientError("connection reset"))
        provider = GroqProvider(groq_config, transport=transport)
        with pytest.raises(LLMTransientError, match="connection reset"):
            provider.generate(_request())

    def test_error_message_includes_the_provider_detail(
        self, groq_config: LLMProviderConfig
    ) -> None:
        transport = FakeTransport(
            [
                (
                    401,
                    make_groq_error_body(
                        message="Invalid API Key", error_type="invalid_request_error"
                    ),
                )
            ]
        )
        provider = GroqProvider(groq_config, transport=transport)
        with pytest.raises(LLMPermanentError, match="Invalid API Key"):
            provider.generate(_request())

    def test_malformed_response_raises_parsing_error(self, groq_config: LLMProviderConfig) -> None:
        from querymind.llm.exceptions import LLMResponseParsingError

        transport = FakeTransport([(200, {"unexpected": "shape"})])
        provider = GroqProvider(groq_config, transport=transport)
        with pytest.raises(LLMResponseParsingError):
            provider.generate(_request())

    def test_api_key_never_appears_in_a_raised_error_message(
        self, groq_config: LLMProviderConfig
    ) -> None:
        transport = FakeTransport([(401, make_groq_error_body(message="authentication failed"))])
        provider = GroqProvider(groq_config, transport=transport)
        with pytest.raises(LLMPermanentError) as exc_info:
            provider.generate(_request())
        assert "test-groq-api-key" not in str(exc_info.value)


class TestDefaultConstruction:
    def test_constructs_its_own_transport_and_parser_when_none_given(
        self, groq_config: LLMProviderConfig
    ) -> None:
        provider = GroqProvider(groq_config)
        assert provider is not None


class TestApiKeySecrecy:
    def test_api_key_is_never_in_the_config_repr(self, groq_config: LLMProviderConfig) -> None:
        assert "test-groq-api-key" not in repr(groq_config)

    def test_api_key_is_never_in_the_provider_repr(self, groq_config: LLMProviderConfig) -> None:
        provider = GroqProvider(groq_config)
        assert "test-groq-api-key" not in repr(provider)
