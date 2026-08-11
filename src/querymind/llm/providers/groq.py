"""The Groq provider: `ProviderClient` and `ResponseParser` for Groq's chat completions API.

Owns everything specific to Groq's HTTP API — the request body shape, the
auth headers, the response JSON shape, and which HTTP status codes are
worth retrying — behind the provider-agnostic `ProviderClient` interface,
exactly mirroring `querymind.llm.providers.claude`'s own structure.
Nothing outside this module knows any of these details.

Groq's API is OpenAI-compatible on the wire (verified against Groq's own
docs, `console.groq.com/docs/api-reference` and `.../docs/text-chat`, at
the time this was written: `POST {base_url}/chat/completions`,
`Authorization: Bearer <key>`, a `choices[0].message.content` response
shape, `max_completion_tokens` rather than `max_tokens`). That
compatibility is an implementation detail of *this file only* — nothing
about "OpenAI" or "chat completions" leaks into `LLMRequest`/
`LLMResponse`/`ProviderClient`, which stay exactly as provider-agnostic
as they were before this provider existed.
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

#: The chat completions endpoint path, appended to `LLMProviderConfig.resolved_base_url`
#: (default `https://api.groq.com/openai/v1`, i.e. this resolves to the documented
#: `https://api.groq.com/openai/v1/chat/completions`).
_CHAT_COMPLETIONS_ENDPOINT = "/chat/completions"

#: HTTP status codes worth retrying — rate limits and transient server-side failures.
#: Mirrors `querymind.llm.providers.claude`'s own set: Groq's API documents no different
#: retry guidance, and this project's retry classification is deliberately one shared
#: convention, not a per-provider policy.
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})

#: Maps Groq's `finish_reason` values onto the provider-agnostic `FinishReason`.
#: `tool_calls`/`function_call` have no equivalent in this app (which never requests tool
#: use), so — like Claude's own unmapped values — they fall through to `FinishReason.ERROR`
#: via `.get(..., FinishReason.ERROR)` below, the same fallback `ClaudeResponseParser` uses.
_FINISH_REASON_MAP: dict[str, FinishReason] = {
    "stop": FinishReason.COMPLETE,
    "length": FinishReason.MAX_TOKENS,
    "content_filter": FinishReason.CONTENT_FILTER,
}


class GroqResponseParser:
    """Parses a Groq chat-completions JSON response body into an `LLMResponse`."""

    def parse(self, raw_response: Mapping[str, Any], *, latency_ms: float) -> LLMResponse:
        try:
            choice = raw_response["choices"][0]
            text = choice["message"]["content"] or ""
            usage = raw_response["usage"]
            token_usage = TokenUsage(
                prompt_tokens=usage["prompt_tokens"], completion_tokens=usage["completion_tokens"]
            )
            model = raw_response["model"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseParsingError(f"Malformed Groq response: missing {exc}.") from exc

        finish_reason_raw: str = choice.get("finish_reason") or ""
        finish_reason = _FINISH_REASON_MAP.get(finish_reason_raw, FinishReason.ERROR)

        return LLMResponse(
            content=text,
            metrics=GenerationMetrics(
                provider=LLMProvider.GROQ,
                model=model,
                latency_ms=latency_ms,
                token_usage=token_usage,
                retry_count=0,
                finish_reason=finish_reason,
            ),
        )


class GroqProvider:
    """`ProviderClient` for Groq's (OpenAI-compatible) chat completions API."""

    def __init__(
        self,
        config: LLMProviderConfig,
        transport: HTTPTransport | None = None,
        parser: GroqResponseParser | None = None,
    ) -> None:
        if config.provider is not LLMProvider.GROQ:
            raise LLMConfigurationError(
                f"GroqProvider requires provider=LLMProvider.GROQ, got {config.provider!r}."
            )
        self._config = config
        self._transport = transport or HttpxTransport()
        self._parser = parser or GroqResponseParser()

    def generate(self, request: LLMRequest) -> LLMResponse:
        url = f"{self._config.resolved_base_url.rstrip('/')}{_CHAT_COMPLETIONS_ENDPOINT}"
        headers = {
            "authorization": f"Bearer {self._config.api_key.get_secret_value()}",
            "content-type": "application/json",
        }
        body = {
            "model": request.model,
            "max_completion_tokens": request.max_tokens,
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
        return f"Groq API returned HTTP {status_code}: {detail}"
