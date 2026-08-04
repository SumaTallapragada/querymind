"""Tests for `querymind.llm.config`."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from querymind.llm.config import (
    DEFAULT_CLAUDE_BASE_URL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_RETRY_COUNT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    LLMProviderConfig,
)
from querymind.llm.models import LLMProvider

from .conftest import make_config


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
    @pytest.mark.parametrize("temperature", [-0.1, 1.1])
    def test_rejects_temperature_out_of_range(self, temperature: float) -> None:
        with pytest.raises(ValidationError):
            make_config(temperature=temperature)

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
