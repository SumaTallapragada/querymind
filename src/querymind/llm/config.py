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

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

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

#: Default Groq API base URL — the OpenAI-compatible root; `GroqProvider` appends
#: `/chat/completions` itself, mirroring how `ClaudeProvider` appends `/v1/messages`.
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

#: Every provider's own default base URL, keyed by `LLMProvider` — the one place a new
#: provider's default lives, so `LLMProviderConfig`'s own after-validator (below) can pick the
#: right one without `Settings`/callers needing to know provider-specific URLs at all.
_DEFAULT_BASE_URL_BY_PROVIDER: dict[LLMProvider, str] = {
    LLMProvider.CLAUDE: DEFAULT_CLAUDE_BASE_URL,
    LLMProvider.GROQ: DEFAULT_GROQ_BASE_URL,
}


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
    temperature: float = Field(default=DEFAULT_TEMPERATURE, ge=0.0, le=2.0)
    max_tokens: int = Field(default=DEFAULT_MAX_TOKENS, gt=0)
    timeout: float = Field(
        default=DEFAULT_TIMEOUT_SECONDS, gt=0.0, description="Per-request timeout, in seconds."
    )
    retry_count: int = Field(
        default=DEFAULT_RETRY_COUNT, ge=0, description="Max retry attempts for transient failures."
    )
    base_url: str | None = Field(
        default=None,
        description=(
            "Provider API base URL. Left unset, resolves to that provider's own default "
            "(see DEFAULT_CLAUDE_BASE_URL/DEFAULT_GROQ_BASE_URL) -- an explicit value always "
            "takes precedence and is never overwritten."
        ),
    )

    @model_validator(mode="after")
    def _resolve_default_base_url(self) -> LLMProviderConfig:
        """Fill in `base_url` from `_DEFAULT_BASE_URL_BY_PROVIDER` when the caller didn't supply
        one -- the single place a per-provider default is chosen, so `Settings.llm_base_url`
        (or any other caller) can simply leave `base_url` unset rather than duplicating each
        provider's URL itself. `object.__setattr__` is the standard escape hatch for setting a
        field on an already-frozen model from inside its own validator.
        """
        if self.base_url is None:
            object.__setattr__(self, "base_url", _DEFAULT_BASE_URL_BY_PROVIDER[self.provider])
        return self

    @property
    def resolved_base_url(self) -> str:
        """`base_url`, guaranteed non-`None` -- the after-validator above always resolves it
        before any caller can observe `None`. Provider code (`ClaudeProvider`/`GroqProvider`)
        reads this instead of `base_url` directly so it never needs its own `None` check for a
        value that, by construction, can never actually be `None` by the time a provider sees it.
        """
        assert self.base_url is not None
        return self.base_url
