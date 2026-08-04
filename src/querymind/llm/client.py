"""Generic HTTP transport for LLM providers.

`HTTPTransport` knows how to make one JSON POST request and hand back a
status code and a parsed body — nothing about what any specific
provider's API looks like. That belongs entirely to
`querymind.llm.providers`, which build the URL/headers/body and interpret
the (status_code, body) pair `HTTPTransport` returns. `HttpxTransport` is
the default implementation, backed by `httpx`; tests inject a fake
`HTTPTransport` (or an `httpx.MockTransport`-backed client) instead of
ever making a real network call.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from querymind.llm.exceptions import LLMTransientError


class HTTPTransport(Protocol):
    """Makes one JSON-in, JSON-out HTTP POST request."""

    def post_json(
        self, *, url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout: float
    ) -> tuple[int, dict[str, Any]]:
        """POST `body` as JSON to `url`; return `(status_code, parsed response body)`.

        Raises `LLMTransientError` for network-level failures (timeout,
        connection error, an unparsable body) — never for HTTP error
        status codes, which are returned as ordinary data so the caller
        (a specific provider) can classify retryability itself.
        """
        ...


class HttpxTransport:
    """The default `HTTPTransport`, backed by `httpx.Client`."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client()

    def post_json(
        self, *, url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout: float
    ) -> tuple[int, dict[str, Any]]:
        try:
            response = self._client.post(
                url, headers=dict(headers), json=dict(body), timeout=timeout
            )
        except httpx.TimeoutException as exc:
            raise LLMTransientError(f"Request to {url} timed out after {timeout}s.") from exc
        except httpx.HTTPError as exc:
            raise LLMTransientError(f"Network error calling {url}: {exc}") from exc

        try:
            parsed_body: dict[str, Any] = response.json()
        except ValueError as exc:
            # A non-JSON body (an HTML gateway error page, ...) most often means the
            # upstream infrastructure — not the request itself — is the problem.
            raise LLMTransientError(
                f"Response from {url} (HTTP {response.status_code}) was not valid JSON."
            ) from exc

        return response.status_code, parsed_body
