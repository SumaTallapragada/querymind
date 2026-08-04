"""The provider abstraction every concrete LLM provider implements."""

from __future__ import annotations

from typing import Protocol

from querymind.llm.models import LLMRequest, LLMResponse


class ProviderClient(Protocol):
    """Sends one `LLMRequest` to a specific LLM provider and returns its `LLMResponse`.

    Makes exactly one call — it never retries; that is
    `querymind.llm.retry.RetryPolicy`'s job, applied by
    `querymind.llm.adapter.LLMAdapter` around this method.
    """

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Send `request` and return the provider's response.

        Raises `querymind.llm.exceptions.LLMTransientError` for a
        retryable failure, `LLMPermanentError` for a non-retryable one,
        or `LLMResponseParsingError` if the provider's response can't be
        understood.
        """
        ...
