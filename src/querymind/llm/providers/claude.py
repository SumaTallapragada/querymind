"""The Claude provider: `ProviderClient` and `ResponseParser` for Anthropic's Messages API.

Owns everything specific to Claude's HTTP API — the request body shape,
the auth headers, the response JSON shape, and which HTTP status codes
are worth retrying — behind the provider-agnostic `ProviderClient`
interface. Nothing outside this module knows any of these details.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from querymind.llm.client import HTTPTransport, HttpxTransport
from querymind.llm.config import LLMProviderConfig
from querymind.llm.exceptions import (
    LLMConfigurationError,
    LLMPermanentError,
    LLMResponseParsingError,
    LLMTransientError,
)
from querymind.llm.models import (
    FinishReason,
    GenerationMetrics,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)

#: The Anthropic Messages API version this provider was written against.
_ANTHROPIC_VERSION = "2023-06-01"

#: The Messages API endpoint path, appended to `LLMProviderConfig.base_url`.
_MESSAGES_ENDPOINT = "/v1/messages"

#: HTTP status codes worth retrying — rate limits and transient server-side failures.
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})

#: Maps Claude's `stop_reason` values onto the provider-agnostic `FinishReason`.
_FINISH_REASON_MAP: dict[str, FinishReason] = {
    "end_turn": FinishReason.COMPLETE,
    "stop_sequence": FinishReason.COMPLETE,
    "max_tokens": FinishReason.MAX_TOKENS,
    "refusal": FinishReason.CONTENT_FILTER,
}


class ClaudeResponseParser:
    """Parses an Anthropic Messages API JSON response body into an `LLMResponse`."""

    def parse(self, raw_response: Mapping[str, Any], *, latency_ms: float) -> LLMResponse:
        try:
            content_blocks = raw_response["content"]
            text = "".join(
                block.get("text", "") for block in content_blocks if block.get("type") == "text"
            )
            usage = raw_response["usage"]
            token_usage = TokenUsage(
                prompt_tokens=usage["input_tokens"], completion_tokens=usage["output_tokens"]
            )
            model = raw_response["model"]
        except (KeyError, TypeError) as exc:
            raise LLMResponseParsingError(f"Malformed Claude response: missing {exc}.") from exc

        stop_reason: str = raw_response.get("stop_reason") or ""
        finish_reason = _FINISH_REASON_MAP.get(stop_reason, FinishReason.ERROR)

        return LLMResponse(
            content=text,
            metrics=GenerationMetrics(
                provider=LLMProvider.CLAUDE,
                model=model,
                latency_ms=latency_ms,
                token_usage=token_usage,
                retry_count=0,
                finish_reason=finish_reason,
            ),
        )


class ClaudeProvider:
    """`ProviderClient` for Anthropic's Claude Messages API."""

    def __init__(
        self,
        config: LLMProviderConfig,
        transport: HTTPTransport | None = None,
        parser: ClaudeResponseParser | None = None,
    ) -> None:
        if config.provider is not LLMProvider.CLAUDE:
            raise LLMConfigurationError(
                f"ClaudeProvider requires provider=LLMProvider.CLAUDE, got {config.provider!r}."
            )
        self._config = config
        self._transport = transport or HttpxTransport()
        self._parser = parser or ClaudeResponseParser()

    def generate(self, request: LLMRequest) -> LLMResponse:
        url = f"{self._config.resolved_base_url.rstrip('/')}{_MESSAGES_ENDPOINT}"
        headers = {
            "x-api-key": self._config.api_key.get_secret_value(),
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        body = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": "user", "content": request.prompt}],
        }

        started = time.perf_counter()
        status_code, raw_response = self._transport.post_json(
            url=url, headers=headers, body=body, timeout=self._config.timeout
        )
        latency_ms = (time.perf_counter() - started) * 1000

        if status_code >= 400:
            message = self._error_message(raw_response, status_code)
            if status_code in _RETRYABLE_STATUS_CODES:
                raise LLMTransientError(message)
            raise LLMPermanentError(message)

        return self._parser.parse(raw_response, latency_ms=latency_ms)

    @staticmethod
    def _error_message(raw_response: Mapping[str, Any], status_code: int) -> str:
        error = raw_response.get("error", {})
        detail = (
            error.get("message", "unknown error") if isinstance(error, Mapping) else "unknown error"
        )
        return f"Claude API returned HTTP {status_code}: {detail}"
