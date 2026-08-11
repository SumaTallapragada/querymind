"""Concrete `ProviderClient` implementations, one per LLM provider, plus `build_llm_provider` --
the single place that turns an `LLMProviderConfig` into the right one.

`build_llm_provider` is the one and only provider-selection dispatch point in the whole
application: `querymind.api.container.ApplicationContainer.build` (and any other composition
root -- a script, a test) calls it instead of constructing a specific provider class directly.
Nothing else -- not `LLMAdapter`, not `QueryMindEngine`, not the prompt compiler, not SQL
generation, not a router -- ever branches on `LLMProviderConfig.provider`; adding a new provider
here never requires touching any of those.
"""

from __future__ import annotations

from querymind.llm.client import HTTPTransport
from querymind.llm.config import LLMProviderConfig
from querymind.llm.exceptions import LLMConfigurationError
from querymind.llm.models import LLMProvider
from querymind.llm.providers.base import ProviderClient
from querymind.llm.providers.claude import ClaudeProvider, ClaudeResponseParser
from querymind.llm.providers.groq import GroqProvider, GroqResponseParser

#: Every registered provider's concrete `ProviderClient` class, keyed by `LLMProvider`. The one
#: place a new provider gets wired in -- `build_llm_provider` below does nothing but look this
#: up and construct it.
_PROVIDER_CLASSES: dict[LLMProvider, type[ClaudeProvider] | type[GroqProvider]] = {
    LLMProvider.CLAUDE: ClaudeProvider,
    LLMProvider.GROQ: GroqProvider,
}


def build_llm_provider(
    config: LLMProviderConfig, *, transport: HTTPTransport | None = None
) -> ProviderClient:
    """Construct the concrete `ProviderClient` for `config.provider`.

    Raises `LLMConfigurationError` for a provider with no registered implementation --
    deliberately never falls back to any particular provider (e.g. Claude) for an unknown one,
    since that would silently send a request to the wrong API with the wrong credentials.
    """
    try:
        provider_class = _PROVIDER_CLASSES[config.provider]
    except KeyError:
        raise LLMConfigurationError(
            f"No ProviderClient implementation is registered for provider={config.provider!r}."
        ) from None
    return provider_class(config, transport=transport)


__all__ = [
    "ClaudeProvider",
    "ClaudeResponseParser",
    "GroqProvider",
    "GroqResponseParser",
    "ProviderClient",
    "build_llm_provider",
]
