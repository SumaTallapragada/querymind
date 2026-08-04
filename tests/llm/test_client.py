"""Tests for `querymind.llm.client.HttpxTransport`.

Uses `httpx.MockTransport` throughout -- never makes a real network call.
"""

from __future__ import annotations

import httpx
import pytest

from querymind.llm.client import HttpxTransport
from querymind.llm.exceptions import LLMTransientError


def _client_returning(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


class TestPostJsonSuccess:
    def test_returns_status_code_and_parsed_body(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"hello": "world"})

        transport = HttpxTransport(_client_returning(httpx.MockTransport(handler)))
        status_code, body = transport.post_json(
            url="https://example.test/v1/messages", headers={}, body={"a": 1}, timeout=5.0
        )
        assert status_code == 200
        assert body == {"hello": "world"}

    def test_sends_the_given_headers_and_body(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["headers"] = dict(request.headers)
            captured["body"] = request.content
            return httpx.Response(200, json={"ok": True})

        transport = HttpxTransport(_client_returning(httpx.MockTransport(handler)))
        transport.post_json(
            url="https://example.test/v1/messages",
            headers={"x-api-key": "secret"},
            body={"model": "claude-sonnet-5"},
            timeout=5.0,
        )
        assert captured["headers"]["x-api-key"] == "secret"  # type: ignore[index]
        assert b"claude-sonnet-5" in captured["body"]  # type: ignore[operator]

    def test_error_status_codes_are_returned_not_raised(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})

        transport = HttpxTransport(_client_returning(httpx.MockTransport(handler)))
        status_code, body = transport.post_json(
            url="https://example.test/v1/messages", headers={}, body={}, timeout=5.0
        )
        assert status_code == 429
        assert body["error"]["message"] == "rate limited"


class TestPostJsonNetworkFailures:
    def test_timeout_raises_llm_transient_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timed out", request=request)

        transport = HttpxTransport(_client_returning(httpx.MockTransport(handler)))
        with pytest.raises(LLMTransientError):
            transport.post_json(
                url="https://example.test/v1/messages", headers={}, body={}, timeout=1.0
            )

    def test_connection_error_raises_llm_transient_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        transport = HttpxTransport(_client_returning(httpx.MockTransport(handler)))
        with pytest.raises(LLMTransientError):
            transport.post_json(
                url="https://example.test/v1/messages", headers={}, body={}, timeout=1.0
            )

    def test_non_json_body_raises_llm_transient_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(502, content=b"<html>Bad Gateway</html>")

        transport = HttpxTransport(_client_returning(httpx.MockTransport(handler)))
        with pytest.raises(LLMTransientError):
            transport.post_json(
                url="https://example.test/v1/messages", headers={}, body={}, timeout=1.0
            )


class TestDefaultConstruction:
    def test_constructs_its_own_client_when_none_given(self) -> None:
        transport = HttpxTransport()
        assert transport is not None
