"""Composition-root test: `ApplicationContainer.build` selects the concrete `ProviderClient`
from `Settings.llm_provider` alone, via `querymind.llm.providers.build_llm_provider` -- and the
resulting provider, whichever it is, is consumed through the exact same `LLMAdapter.generate`
call every other engine already uses (`SQLGenerationEngine`, `SQLRepairEngine`). Proven
behaviorally (which real HTTP endpoint gets hit for a real `generate()` call), not by reaching
into `LLMAdapter`'s private `_provider_client` -- the same "prove it end to end through the real
contract" style `tests/llm/test_integration.py` already uses for Claude alone.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
from pydantic import SecretStr

from querymind.api.container import ApplicationContainer
from querymind.core.config import Settings
from querymind.llm.client import HttpxTransport
from querymind.llm.models import LLMProvider
from tests.llm.conftest import (
    make_claude_success_body,
    make_compiled_prompt,
    make_groq_success_body,
)

_MockHandler = Callable[[httpx.Request], httpx.Response]


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "postgres_user": "test",
        "postgres_password": "test",
        "postgres_db": "test",
        "postgres_host": "localhost",
        "log_format": "console",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _mock_transport(handler: _MockHandler) -> HttpxTransport:
    return HttpxTransport(httpx.Client(transport=httpx.MockTransport(handler)))


class TestProviderSelection:
    def test_llm_provider_claude_wires_up_a_container_that_calls_the_claude_endpoint(self) -> None:
        requested_urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_urls.append(str(request.url))
            return httpx.Response(200, json=make_claude_success_body(text="SELECT 1;"))

        settings = _settings(
            llm_provider=LLMProvider.CLAUDE,
            llm_model="claude-sonnet-5",
            llm_api_key=SecretStr("test-key"),
        )
        container = ApplicationContainer.build(settings, llm_transport=_mock_transport(handler))

        response = container.llm_adapter.generate(make_compiled_prompt())

        assert response.content == "SELECT 1;"
        assert requested_urls == ["https://api.anthropic.com/v1/messages"]

    def test_llm_provider_groq_wires_up_a_container_that_calls_the_groq_endpoint(self) -> None:
        requested_urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_urls.append(str(request.url))
            return httpx.Response(200, json=make_groq_success_body(text="SELECT 1;"))

        settings = _settings(
            llm_provider=LLMProvider.GROQ,
            llm_model="llama-3.3-70b-versatile",
            llm_api_key=SecretStr("test-key"),
        )
        container = ApplicationContainer.build(settings, llm_transport=_mock_transport(handler))

        response = container.llm_adapter.generate(make_compiled_prompt())

        assert response.content == "SELECT 1;"
        assert requested_urls == ["https://api.groq.com/openai/v1/chat/completions"]

    def test_switching_providers_requires_no_change_to_how_the_adapter_is_called(self) -> None:
        # The same call site (`container.llm_adapter.generate(prompt)`), the same
        # LLMAdapter/ProviderClient contract, for either provider -- only `Settings.llm_provider`
        # differs between the two tests above. This test just makes that invariant explicit.
        claude_container = ApplicationContainer.build(
            _settings(llm_provider=LLMProvider.CLAUDE, llm_api_key=SecretStr("k")),
            llm_transport=_mock_transport(
                lambda r: httpx.Response(200, json=make_claude_success_body())
            ),
        )
        groq_container = ApplicationContainer.build(
            _settings(llm_provider=LLMProvider.GROQ, llm_api_key=SecretStr("k")),
            llm_transport=_mock_transport(
                lambda r: httpx.Response(200, json=make_groq_success_body())
            ),
        )

        assert callable(claude_container.llm_adapter.generate)
        assert callable(groq_container.llm_adapter.generate)
        claude_response = claude_container.llm_adapter.generate(make_compiled_prompt())
        groq_response = groq_container.llm_adapter.generate(make_compiled_prompt())
        assert claude_response.metrics.provider is LLMProvider.CLAUDE
        assert groq_response.metrics.provider is LLMProvider.GROQ
