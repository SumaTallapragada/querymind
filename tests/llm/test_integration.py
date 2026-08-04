"""End-to-end tests against the real, fully wired LLM Adapter stack.

Wires `LLMAdapter` -> `ClaudeProvider` -> `HttpxTransport` together exactly
as production would, down to real JSON-over-HTTP request/response
handling -- the only substitution is `httpx.MockTransport` in place of a
live network socket, since there is no live Anthropic API available (or
appropriate) to call from a test suite. This is the closest equivalent to
`tests/prompt_compiler/test_integration.py`'s "real pipeline" tests that
this phase allows without a live, billed, third-party API call.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from querymind.llm.adapter import LLMAdapter
from querymind.llm.client import HttpxTransport
from querymind.llm.exceptions import LLMPermanentError, RetryExhaustedError
from querymind.llm.providers.claude import ClaudeProvider
from querymind.llm.retry import RetryPolicy
from querymind.prompt_compiler.models import CompiledPrompt

from .conftest import RecordingSleep, make_claude_error_body, make_claude_success_body, make_config

_MockHandler = Callable[[httpx.Request], httpx.Response]


def _adapter_for(
    handler: _MockHandler, *, no_sleep: RecordingSleep, retry_count: int = 3
) -> LLMAdapter:
    transport = HttpxTransport(httpx.Client(transport=httpx.MockTransport(handler)))
    config = make_config(retry_count=retry_count)
    provider = ClaudeProvider(config, transport=transport)
    return LLMAdapter(provider, config, retry_policy=RetryPolicy(retry_count, sleep=no_sleep))


def test_successful_generation_end_to_end(
    compiled_prompt: CompiledPrompt, no_sleep: RecordingSleep
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=make_claude_success_body(text="SELECT * FROM customers;"))

    adapter = _adapter_for(handler, no_sleep=no_sleep)
    response = adapter.generate(compiled_prompt)

    assert response.content == "SELECT * FROM customers;"
    assert response.metrics.retry_count == 0
    assert response.metrics.token_usage.total_tokens > 0


def test_transient_failure_then_success_end_to_end(
    compiled_prompt: CompiledPrompt, no_sleep: RecordingSleep
) -> None:
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 3:
            return httpx.Response(503, json=make_claude_error_body(message="overloaded"))
        return httpx.Response(200, json=make_claude_success_body(text="SELECT 1;"))

    adapter = _adapter_for(handler, no_sleep=no_sleep)
    response = adapter.generate(compiled_prompt)

    assert response.content == "SELECT 1;"
    assert response.metrics.retry_count == 2
    assert call_count["n"] == 3


def test_permanent_failure_is_not_retried_end_to_end(
    compiled_prompt: CompiledPrompt, no_sleep: RecordingSleep
) -> None:
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(401, json=make_claude_error_body(message="invalid API key"))

    adapter = _adapter_for(handler, no_sleep=no_sleep)
    with pytest.raises(LLMPermanentError):
        adapter.generate(compiled_prompt)
    assert call_count["n"] == 1


def test_exhausting_all_retries_raises_end_to_end(
    compiled_prompt: CompiledPrompt, no_sleep: RecordingSleep
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json=make_claude_error_body(message="rate limited"))

    adapter = _adapter_for(handler, no_sleep=no_sleep, retry_count=2)
    with pytest.raises(RetryExhaustedError) as exc_info:
        adapter.generate(compiled_prompt)
    assert exc_info.value.attempts == 3
