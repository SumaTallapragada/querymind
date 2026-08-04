"""Domain-specific exceptions for the LLM Adapter."""

from __future__ import annotations


class LLMError(Exception):
    """Base class for every exception raised by `querymind.llm`."""


class LLMConfigurationError(LLMError):
    """Raised when an `llm` component is constructed with invalid settings.

    Reserved for checks Pydantic's own field validation can't express —
    e.g. a plain constructor argument (`RetryPolicy.max_retries`) or a
    cross-object consistency check (`ClaudeProvider` requiring
    `LLMProviderConfig.provider is LLMProvider.CLAUDE`). Ordinary field
    constraints on `LLMProviderConfig` itself (temperature out of range,
    negative token counts, ...) raise Pydantic's own `ValidationError`.
    """


class LLMTransientError(LLMError):
    """A retryable provider failure: a timeout, a rate limit, a transient 5xx.

    The only exception type `querymind.llm.retry.RetryPolicy` retries —
    everything else propagates immediately, unretried.
    """


class LLMPermanentError(LLMError):
    """A non-retryable provider failure: a bad request, an auth failure, an invalid model."""


class LLMResponseParsingError(LLMError):
    """Raised when a provider's raw response cannot be parsed into an `LLMResponse`.

    Never retried — retrying an already-received, malformed response
    cannot change its content.
    """


class RetryExhaustedError(LLMError):
    """Raised when every retry attempt failed with a transient error."""

    def __init__(self, *, attempts: int, last_error: Exception) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Exhausted {attempts} attempt(s); last error: {last_error!r}")
