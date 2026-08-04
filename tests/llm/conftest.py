"""Shared fixtures and builders for LLM Adapter tests.

Never makes a real network call — `providers.claude.ClaudeProvider` is
always exercised against a fake `HTTPTransport` (or, for
`test_client.py` specifically, an `httpx.MockTransport`), never against
the real Anthropic API.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import SecretStr

from querymind.llm.client import HTTPTransport
from querymind.llm.config import LLMProviderConfig
from querymind.llm.models import LLMProvider
from querymind.prompt_compiler.models import (
    BusinessSection,
    CompiledPrompt,
    ConstraintSection,
    ExampleSection,
    OutputSection,
    PromptStatistics,
    RelationshipSection,
    SchemaSection,
    SystemSection,
)
from querymind.query_library.models import SQLDialect


def make_compiled_prompt(**overrides: object) -> CompiledPrompt:
    defaults: dict[str, object] = {
        "system": SystemSection(content="You are a careful SQL assistant.", estimated_tokens=6),
        "business_context": BusinessSection(
            content="Concerns customer revenue.", estimated_tokens=4
        ),
        "schema_context": SchemaSection(
            content="Table `customers`.", estimated_tokens=3, schema_objects=("customers",)
        ),
        "relationships": RelationshipSection(content="No joins required.", estimated_tokens=3),
        "examples": ExampleSection(content="No examples.", estimated_tokens=2),
        "constraints": ConstraintSection(
            content="Return exactly one statement.", estimated_tokens=4
        ),
        "output_format": OutputSection(content="Write valid postgresql SQL.", estimated_tokens=4),
        "statistics": PromptStatistics(
            estimated_total_tokens=26,
            section_token_usage=(),
            retrieved_example_count=0,
            schema_object_count=1,
            compilation_latency_ms=0.2,
        ),
        "template_version": "1.0.0",
        "dialect": SQLDialect.POSTGRESQL,
    }
    defaults.update(overrides)
    return CompiledPrompt(**defaults)  # type: ignore[arg-type]


def make_config(**overrides: object) -> LLMProviderConfig:
    defaults: dict[str, object] = {
        "provider": LLMProvider.CLAUDE,
        "model": "claude-sonnet-5",
        "api_key": SecretStr("test-api-key"),
    }
    defaults.update(overrides)
    return LLMProviderConfig(**defaults)  # type: ignore[arg-type]


def make_claude_success_body(
    *,
    text: str = "SELECT 1;",
    model: str = "claude-sonnet-5",
    stop_reason: str = "end_turn",
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> dict[str, Any]:
    return {
        "id": "msg_01",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def make_claude_error_body(
    *, message: str = "something went wrong", error_type: str = "api_error"
) -> dict[str, Any]:
    return {"type": "error", "error": {"type": error_type, "message": message}}


class FakeTransport:
    """An `HTTPTransport` that returns a scripted sequence of `(status_code, body)` responses."""

    def __init__(self, responses: list[tuple[int, dict[str, Any]]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post_json(
        self, *, url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout: float
    ) -> tuple[int, dict[str, Any]]:
        self.calls.append(
            {"url": url, "headers": dict(headers), "body": dict(body), "timeout": timeout}
        )
        if not self._responses:
            raise AssertionError("FakeTransport ran out of scripted responses.")
        return self._responses.pop(0)


class RaisingTransport:
    """An `HTTPTransport` that always raises a scripted exception (simulates a network failure)."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def post_json(
        self, *, url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout: float
    ) -> tuple[int, dict[str, Any]]:
        raise self._exc


@pytest.fixture
def compiled_prompt() -> CompiledPrompt:
    return make_compiled_prompt()


@pytest.fixture
def config() -> LLMProviderConfig:
    return make_config()


class RecordingSleep:
    """A `SleepFn` that records requested delays instead of actually sleeping."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.fixture
def no_sleep() -> RecordingSleep:
    return RecordingSleep()


__all__ = [
    "FakeTransport",
    "HTTPTransport",
    "RaisingTransport",
    "RecordingSleep",
    "make_claude_error_body",
    "make_claude_success_body",
    "make_compiled_prompt",
    "make_config",
]
