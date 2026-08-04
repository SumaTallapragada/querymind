"""The LLM Adapter — QueryMind Phase 10B.

A provider-agnostic bridge from a
`querymind.prompt_compiler.CompiledPrompt` to an `LLMResponse`. It does
**not** know anything about SQL — it never generates, parses, or
validates SQL — and it does not build prompts; that is entirely
`querymind.prompt_compiler`'s job, already done by the time a
`CompiledPrompt` reaches `LLMAdapter.generate`.

The public surface is `LLMAdapter.generate`.
"""

from __future__ import annotations

from querymind.llm.adapter import LLMAdapter
from querymind.llm.cache import LLMResponseCache, NoOpLLMResponseCache
from querymind.llm.client import HTTPTransport, HttpxTransport
from querymind.llm.config import (
    DEFAULT_CLAUDE_BASE_URL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_RETRY_COUNT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    LLMProviderConfig,
)
from querymind.llm.exceptions import (
    LLMConfigurationError,
    LLMError,
    LLMPermanentError,
    LLMResponseParsingError,
    LLMTransientError,
    RetryExhaustedError,
)
from querymind.llm.metrics import InMemoryMetricsCollector, MetricsCollector
from querymind.llm.models import (
    FinishReason,
    GenerationMetrics,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
from querymind.llm.parser import ResponseParser
from querymind.llm.providers import ClaudeProvider, ClaudeResponseParser, ProviderClient
from querymind.llm.retry import RetryPolicy

__all__ = [
    "DEFAULT_CLAUDE_BASE_URL",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_RETRY_COUNT",
    "DEFAULT_TEMPERATURE",
    "DEFAULT_TIMEOUT_SECONDS",
    "ClaudeProvider",
    "ClaudeResponseParser",
    "FinishReason",
    "GenerationMetrics",
    "HTTPTransport",
    "HttpxTransport",
    "InMemoryMetricsCollector",
    "LLMAdapter",
    "LLMConfigurationError",
    "LLMError",
    "LLMPermanentError",
    "LLMProvider",
    "LLMProviderConfig",
    "LLMRequest",
    "LLMResponse",
    "LLMResponseCache",
    "LLMResponseParsingError",
    "LLMTransientError",
    "MetricsCollector",
    "NoOpLLMResponseCache",
    "ProviderClient",
    "ResponseParser",
    "RetryExhaustedError",
    "RetryPolicy",
    "TokenUsage",
]
