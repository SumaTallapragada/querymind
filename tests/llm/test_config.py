"""Tests for `querymind.llm.config`."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from querymind.core.config import Settings
from querymind.llm.config import (
    DEFAULT_CLAUDE_BASE_URL,
    DEFAULT_GROQ_BASE_URL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_RETRY_COUNT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    LLMProviderConfig,
)
from querymind.llm.models import LLMProvider

from .conftest import make_config, make_groq_config


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "postgres_user": "test",
        "postgres_password": "test",
        "postgres_db": "test",
        "postgres_host": "localhost",
        "log_format": "console",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class TestDefaults:
    def test_defaults_are_applied_when_not_given(self) -> None:
        config = make_config()
        assert config.temperature == DEFAULT_TEMPERATURE
        assert config.max_tokens == DEFAULT_MAX_TOKENS
        assert config.timeout == DEFAULT_TIMEOUT_SECONDS
        assert config.retry_count == DEFAULT_RETRY_COUNT
        assert config.base_url == DEFAULT_CLAUDE_BASE_URL
        assert config.provider is LLMProvider.CLAUDE

    def test_every_field_is_overridable(self) -> None:
        config = make_config(
            temperature=0.5,
            max_tokens=2048,
            timeout=10.0,
            retry_count=1,
            base_url="https://proxy.example",
        )
        assert config.temperature == 0.5
        assert config.max_tokens == 2048
        assert config.timeout == 10.0
        assert config.retry_count == 1
        assert config.base_url == "https://proxy.example"


class TestBaseUrlResolution:
    """`base_url` left unset resolves to the *configured provider's own* default -- never
    unconditionally Claude's, which was the actual bug this class regression-locks (Phase: LLM
    provider expansion). `LLMProviderConfig.resolved_base_url` is what provider code
    (`ClaudeProvider`/`GroqProvider`) actually reads.
    """

    def test_claude_with_no_base_url_resolves_to_the_claude_default(self) -> None:
        config = make_config()
        assert config.base_url == DEFAULT_CLAUDE_BASE_URL
        assert config.resolved_base_url == DEFAULT_CLAUDE_BASE_URL

    def test_groq_with_no_base_url_resolves_to_the_groq_default(self) -> None:
        config = make_groq_config()
        assert config.base_url == DEFAULT_GROQ_BASE_URL
        assert config.resolved_base_url == DEFAULT_GROQ_BASE_URL

    def test_claude_with_an_explicit_base_url_is_never_overwritten(self) -> None:
        config = make_config(base_url="https://claude-proxy.example")
        assert config.base_url == "https://claude-proxy.example"
        assert config.resolved_base_url == "https://claude-proxy.example"

    def test_groq_with_an_explicit_base_url_is_never_overwritten(self) -> None:
        config = make_groq_config(base_url="https://groq-proxy.example")
        assert config.base_url == "https://groq-proxy.example"
        assert config.resolved_base_url == "https://groq-proxy.example"

    def test_the_two_providers_default_to_genuinely_different_urls(self) -> None:
        # The actual bug being regression-locked: before this fix, both providers'
        # base_url defaulted to the same (Claude's) URL regardless of `provider`.
        assert DEFAULT_CLAUDE_BASE_URL != DEFAULT_GROQ_BASE_URL
        assert make_config().resolved_base_url != make_groq_config().resolved_base_url


class TestRequiredFields:
    def test_model_is_required(self) -> None:
        with pytest.raises(ValidationError):
            LLMProviderConfig(api_key=SecretStr("k"))  # type: ignore[call-arg]

    def test_api_key_is_required(self) -> None:
        with pytest.raises(ValidationError):
            LLMProviderConfig(model="claude-sonnet-5")  # type: ignore[call-arg]


class TestApiKeyIsSecret:
    def test_api_key_never_appears_in_repr(self) -> None:
        config = make_config()
        assert "test-api-key" not in repr(config)

    def test_get_secret_value_returns_the_real_key(self) -> None:
        config = make_config()
        assert config.api_key.get_secret_value() == "test-api-key"


class TestFieldConstraints:
    @pytest.mark.parametrize("temperature", [-0.1, 2.1])
    def test_rejects_temperature_out_of_range(self, temperature: float) -> None:
        with pytest.raises(ValidationError):
            make_config(temperature=temperature)

    @pytest.mark.parametrize("temperature", [0.0, 1.0, 1.5, 2.0])
    def test_accepts_temperature_across_the_full_widened_range(self, temperature: float) -> None:
        # Regression lock for the generic (provider-agnostic) temperature range fix: the range
        # was widened from `le=1.0` to `le=2.0` because it's not Claude-specific -- Groq and other
        # OpenAI-compatible APIs legitimately accept temperatures above 1.0.
        config = make_config(temperature=temperature)
        assert config.temperature == temperature

    def test_groq_accepts_temperature_above_one(self) -> None:
        # The concrete case the widened range exists for: before this fix, `le=1.0` made it
        # impossible to configure a Groq provider (or any other non-Claude, OpenAI-compatible
        # provider) with a temperature Claude itself never supported in the first place.
        config = make_groq_config(temperature=1.5)
        assert config.temperature == 1.5

    def test_claude_configuration_behavior_is_unchanged(self) -> None:
        # Claude's own effective range (0.0-1.0, per Anthropic's API) still works exactly as
        # before -- widening the field's upper bound doesn't change what values Claude
        # configurations actually use; it only stops rejecting values that were never
        # Claude-specific to begin with.
        config = make_config(temperature=1.0)
        assert config.temperature == 1.0
        assert config.provider is LLMProvider.CLAUDE

    @pytest.mark.parametrize("max_tokens", [0, -1])
    def test_rejects_non_positive_max_tokens(self, max_tokens: int) -> None:
        with pytest.raises(ValidationError):
            make_config(max_tokens=max_tokens)

    @pytest.mark.parametrize("timeout", [0, -1.0])
    def test_rejects_non_positive_timeout(self, timeout: float) -> None:
        with pytest.raises(ValidationError):
            make_config(timeout=timeout)

    def test_rejects_negative_retry_count(self) -> None:
        with pytest.raises(ValidationError):
            make_config(retry_count=-1)

    def test_allows_zero_retry_count(self) -> None:
        config = make_config(retry_count=0)
        assert config.retry_count == 0


class TestImmutability:
    def test_is_frozen(self) -> None:
        config = make_config()
        with pytest.raises(ValidationError):
            config.model = "other-model"  # type: ignore[misc]

    def test_unknown_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_config(bogus_field="nope")


class TestSettingsTemperatureRange:
    """`Settings.llm_temperature` mirrors `LLMProviderConfig.temperature`'s own range -- same
    generic (provider-agnostic) fix, regression-locked separately here because `Settings` is the
    field actually read from the environment/`.env` in production.
    """

    @pytest.mark.parametrize("temperature", [0.0, 1.0, 1.5, 2.0])
    def test_accepts_temperature_across_the_full_widened_range(self, temperature: float) -> None:
        settings = _settings(llm_temperature=temperature)
        assert settings.llm_temperature == temperature
        assert settings.llm_provider_config.temperature == temperature

    @pytest.mark.parametrize("temperature", [-0.1, 2.1])
    def test_rejects_temperature_out_of_range(self, temperature: float) -> None:
        with pytest.raises(ValidationError):
            _settings(llm_temperature=temperature)

    def test_default_temperature_is_unchanged(self) -> None:
        settings = _settings()
        assert settings.llm_temperature == DEFAULT_TEMPERATURE

    def test_claude_settings_still_behave_exactly_as_before(self) -> None:
        settings = _settings(
            llm_provider=LLMProvider.CLAUDE,
            llm_model="claude-sonnet-5",
            llm_api_key=SecretStr("test-key"),
        )
        config = settings.llm_provider_config
        assert config.provider is LLMProvider.CLAUDE
        assert config.temperature == DEFAULT_TEMPERATURE
        assert config.base_url == DEFAULT_CLAUDE_BASE_URL

    def test_groq_settings_can_now_configure_temperature_above_one(self) -> None:
        settings = _settings(
            llm_provider=LLMProvider.GROQ,
            llm_model="llama-3.3-70b-versatile",
            llm_api_key=SecretStr("test-key"),
            llm_temperature=1.5,
        )
        config = settings.llm_provider_config
        assert config.provider is LLMProvider.GROQ
        assert config.temperature == 1.5
        assert config.base_url == DEFAULT_GROQ_BASE_URL
