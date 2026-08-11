"""Tests for `querymind.llm.providers.build_llm_provider` -- the single, centralized
provider-selection dispatch point every composition root uses instead of constructing a
concrete provider class directly (see that module's own docstring).
"""

from __future__ import annotations

import pytest

from querymind.llm.exceptions import LLMConfigurationError
from querymind.llm.providers import ClaudeProvider, GroqProvider, build_llm_provider

from .conftest import make_config, make_groq_config


class TestDispatch:
    def test_claude_provider_selects_claude_provider(self) -> None:
        provider = build_llm_provider(make_config())
        assert isinstance(provider, ClaudeProvider)

    def test_groq_provider_selects_groq_provider(self) -> None:
        provider = build_llm_provider(make_groq_config())
        assert isinstance(provider, GroqProvider)

    def test_passes_the_given_transport_through(self) -> None:
        from .conftest import FakeTransport

        transport = FakeTransport([])
        provider = build_llm_provider(make_config(), transport=transport)
        # White-box on purpose: the only way to confirm the *same* transport instance was
        # actually forwarded, not silently dropped in favor of a fresh default one.
        assert provider._transport is transport  # type: ignore[attr-defined]


class TestUnknownProvider:
    def test_raises_llm_configuration_error_rather_than_defaulting_to_any_provider(self) -> None:
        # `LLMProvider` is a real, closed enum -- a genuinely unknown value can only reach
        # this dispatch by bypassing Settings/LLMProviderConfig's own validation, exactly
        # mirroring test_providers_claude.py's own precedent for the same reason.
        config = make_config()
        bogus = config.model_copy(update={"provider": "not-a-real-provider"})
        with pytest.raises(LLMConfigurationError, match="not-a-real-provider"):
            build_llm_provider(bogus)
