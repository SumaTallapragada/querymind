"""Shared fixtures and builders for SQL Generation Engine tests.

`SQLGenerationEngine` is constructed with a real `LLMAdapter` (per the
spec: "using the existing LLM Adapter"), wired with a scripted
`ProviderClient` that returns canned `LLMResponse`s — mirroring exactly
how `tests/llm/test_adapter.py` exercises `LLMAdapter` itself. Never
makes a real network call.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from querymind.llm.adapter import LLMAdapter
from querymind.llm.config import LLMProviderConfig
from querymind.llm.models import (
    FinishReason,
    GenerationMetrics,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
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


def make_llm_response(*, content: str = "SELECT 1;", **overrides: object) -> LLMResponse:
    defaults: dict[str, object] = {
        "content": content,
        "metrics": GenerationMetrics(
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-5",
            latency_ms=120.0,
            token_usage=TokenUsage(prompt_tokens=100, completion_tokens=20),
            retry_count=0,
            finish_reason=FinishReason.COMPLETE,
        ),
    }
    defaults.update(overrides)
    return LLMResponse(**defaults)  # type: ignore[arg-type]


def make_config(**overrides: object) -> LLMProviderConfig:
    defaults: dict[str, object] = {
        "provider": LLMProvider.CLAUDE,
        "model": "claude-sonnet-5",
        "api_key": SecretStr("test-api-key"),
    }
    defaults.update(overrides)
    return LLMProviderConfig(**defaults)  # type: ignore[arg-type]


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


def make_llm_adapter(outcomes: list[LLMResponse | Exception]) -> LLMAdapter:
    """Build a real `LLMAdapter` wired with a `ScriptedProvider` returning `outcomes` in order."""
    return LLMAdapter(ScriptedProvider(outcomes), make_config())


@pytest.fixture
def compiled_prompt() -> CompiledPrompt:
    return make_compiled_prompt()
