"""Configuration for the LLM Adapter.

`LLMProviderConfig` is a plain, immutable value object — never a
`pydantic_settings.BaseSettings` reading `os.environ` itself. Consistent
with every other Phase's constructor-injected configuration (e.g.
`querymind.prompt_compiler.budget.PromptBudgetManager`), the caller
builds it (from `querymind.core.config.Settings`, from a test fixture,
from anywhere) and passes it in — nothing in this package ever reads the
environment directly. `api_key` and `model` have no default: they must
always come from real configuration, never a hardcoded fallback.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from querymind.llm.models import LLMProvider

#: Default sampling temperature — 0.0 favors precise, deterministic output.
DEFAULT_TEMPERATURE = 0.0

#: Default maximum tokens a single generation may produce.
DEFAULT_MAX_TOKENS = 4096

#: Default per-request timeout, in seconds.
DEFAULT_TIMEOUT_SECONDS = 30.0

#: Default number of retry attempts for transient failures.
DEFAULT_RETRY_COUNT = 3

#: Default Anthropic API base URL.
DEFAULT_CLAUDE_BASE_URL = "https://api.anthropic.com"


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class LLMProviderConfig(_FrozenModel):
    """Everything needed to construct a provider and shape each `LLMRequest` it sends."""

    provider: LLMProvider = LLMProvider.CLAUDE
    model: str = Field(description="Provider-specific model identifier, e.g. 'claude-sonnet-5'.")
    api_key: SecretStr = Field(
        description="Provider API key. Never logged or serialized in plain text."
    )
    temperature: float = Field(default=DEFAULT_TEMPERATURE, ge=0.0, le=1.0)
    max_tokens: int = Field(default=DEFAULT_MAX_TOKENS, gt=0)
    timeout: float = Field(
        default=DEFAULT_TIMEOUT_SECONDS, gt=0.0, description="Per-request timeout, in seconds."
    )
    retry_count: int = Field(
        default=DEFAULT_RETRY_COUNT, ge=0, description="Max retry attempts for transient failures."
    )
    base_url: str = Field(default=DEFAULT_CLAUDE_BASE_URL, description="Provider API base URL.")
