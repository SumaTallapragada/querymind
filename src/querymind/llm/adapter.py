"""The LLM Adapter: turns a `CompiledPrompt` into an `LLMResponse`.

`LLMAdapter` is the single public entry point for `querymind.llm`. It
knows nothing about SQL, does not build prompts (that's already done by
the time a `CompiledPrompt` reaches it — see `querymind.prompt_compiler`),
and does not validate anything a provider returns. Its only
responsibilities: turn the compiled prompt into a provider-agnostic
`LLMRequest`, call the injected `ProviderClient` (retrying transient
failures via `RetryPolicy`), and record `GenerationMetrics` for the call.
"""

from __future__ import annotations

from querymind.llm.config import LLMProviderConfig
from querymind.llm.metrics import InMemoryMetricsCollector, MetricsCollector
from querymind.llm.models import LLMRequest, LLMResponse
from querymind.llm.providers.base import ProviderClient
from querymind.llm.retry import RetryPolicy
from querymind.prompt_compiler.models import CompiledPrompt


class LLMAdapter:
    """Compiles an `LLMRequest` from a `CompiledPrompt`, calls a provider, and records metrics.

    Every collaborator — the provider client, the retry policy, the
    metrics collector — is constructor-injected with a sensible default,
    so a caller can swap in a different provider, a stricter retry
    policy, or a different metrics sink without touching this class.
    """

    def __init__(
        self,
        provider_client: ProviderClient,
        config: LLMProviderConfig,
        retry_policy: RetryPolicy | None = None,
        metrics_collector: MetricsCollector | None = None,
    ) -> None:
        self._provider_client = provider_client
        self._config = config
        self._retry_policy = retry_policy or RetryPolicy(max_retries=config.retry_count)
        self._metrics_collector = metrics_collector or InMemoryMetricsCollector()

    def generate(self, prompt: CompiledPrompt) -> LLMResponse:
        """Generate a response for `prompt`.

        Raises `querymind.llm.exceptions.RetryExhaustedError` if every
        attempt fails with a transient error, or
        `LLMPermanentError`/`LLMResponseParsingError` immediately for a
        non-retryable failure.
        """
        request = LLMRequest(
            prompt=prompt.as_text(),
            model=self._config.model,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
        )

        response, retry_count = self._retry_policy.execute(
            lambda: self._provider_client.generate(request)
        )

        if response.metrics.retry_count != retry_count:
            response = response.model_copy(
                update={"metrics": response.metrics.model_copy(update={"retry_count": retry_count})}
            )

        self._metrics_collector.record(response.metrics)
        return response
