"""Immutable data models for the LLM Adapter.

`LLMAdapter.generate` (see `querymind.llm.adapter`) is the single public
entry point: it takes a `querymind.prompt_compiler.CompiledPrompt` and
returns an `LLMResponse`. Everything in this module is provider-agnostic —
`LLMRequest` is what gets sent to *any* provider, `LLMResponse` is what
comes back from *any* provider; provider-specific request/response shapes
are translated to and from these models entirely inside
`querymind.llm.providers`. Nothing here knows anything about SQL —
`LLMResponse.content` is opaque generated text, never parsed or validated.

Every model is frozen (`model_config = ConfigDict(frozen=True)`) and uses
`tuple`, never `list`, for collections — matching every other Phase's
models package: a Pydantic `frozen=True` model still allows in-place
mutation of a `list` field, a `tuple` field does not.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class LLMProvider(str, Enum):
    """The LLM providers `querymind.llm.providers` implements. Currently just Claude."""

    CLAUDE = "claude"


class FinishReason(str, Enum):
    """Why generation stopped, normalized across providers.

    Each concrete provider maps its own native reason (e.g. Claude's
    `stop_reason` of `"end_turn"`, `"stop_sequence"`, `"max_tokens"`,
    `"refusal"`) onto one of these four values — callers never need to
    know a specific provider's vocabulary.
    """

    COMPLETE = "complete"
    MAX_TOKENS = "max_tokens"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"


class LLMRequest(_FrozenModel):
    """A provider-agnostic generation request: prompt text plus generation parameters."""

    prompt: str = Field(
        min_length=1, description="The full compiled prompt text, sent to the provider verbatim."
    )
    model: str = Field(description="Provider-specific model identifier, e.g. 'claude-sonnet-5'.")
    temperature: float = Field(ge=0.0, le=1.0)
    max_tokens: int = Field(gt=0)


class TokenUsage(_FrozenModel):
    """Token counts for one generation call."""

    prompt_tokens: int = Field(ge=0, description="Tokens consumed by the input prompt.")
    completion_tokens: int = Field(ge=0, description="Tokens generated in the response.")

    @property
    def total_tokens(self) -> int:
        """`prompt_tokens + completion_tokens` — derived, never stored, so it can't drift."""
        return self.prompt_tokens + self.completion_tokens


class GenerationMetrics(_FrozenModel):
    """Observability data about one `LLMAdapter.generate` call."""

    provider: LLMProvider
    model: str = Field(description="The model that actually served the request.")
    latency_ms: float = Field(ge=0.0, description="Wall-clock time the successful call took.")
    token_usage: TokenUsage
    retry_count: int = Field(
        ge=0, description="How many retries were needed before this response succeeded."
    )
    finish_reason: FinishReason


class LLMResponse(_FrozenModel):
    """The complete output of one `LLMAdapter.generate` call: text plus metrics.

    `content` is the model's raw generated text — this package never
    parses, validates, or otherwise interprets it as SQL; that is a later
    phase's responsibility.
    """

    content: str
    metrics: GenerationMetrics
