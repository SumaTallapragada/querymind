"""Tests for `querymind.llm.providers.claude.ClaudeResponseParser`.

`querymind.llm.parser.ResponseParser` is a bare `Protocol` with no
behavior of its own to test directly; `ClaudeResponseParser` is its one
concrete implementation in this phase.
"""

from __future__ import annotations

import pytest

from querymind.llm.exceptions import LLMResponseParsingError
from querymind.llm.models import FinishReason, LLMProvider
from querymind.llm.providers.claude import ClaudeResponseParser

from .conftest import make_claude_success_body


class TestParseSuccess:
    def test_extracts_text_content(self) -> None:
        parser = ClaudeResponseParser()
        response = parser.parse(make_claude_success_body(text="SELECT 1;"), latency_ms=42.0)
        assert response.content == "SELECT 1;"

    def test_joins_multiple_text_blocks(self) -> None:
        body = make_claude_success_body()
        body["content"] = [{"type": "text", "text": "SELECT "}, {"type": "text", "text": "1;"}]
        response = ClaudeResponseParser().parse(body, latency_ms=1.0)
        assert response.content == "SELECT 1;"

    def test_extracts_token_usage(self) -> None:
        body = make_claude_success_body(input_tokens=20, output_tokens=8)
        response = ClaudeResponseParser().parse(body, latency_ms=1.0)
        assert response.metrics.token_usage.prompt_tokens == 20
        assert response.metrics.token_usage.completion_tokens == 8

    def test_sets_provider_and_model(self) -> None:
        body = make_claude_success_body(model="claude-opus-5")
        response = ClaudeResponseParser().parse(body, latency_ms=1.0)
        assert response.metrics.provider is LLMProvider.CLAUDE
        assert response.metrics.model == "claude-opus-5"

    def test_records_latency_and_zero_retry_count(self) -> None:
        response = ClaudeResponseParser().parse(make_claude_success_body(), latency_ms=250.0)
        assert response.metrics.latency_ms == 250.0
        assert response.metrics.retry_count == 0

    @pytest.mark.parametrize(
        ("stop_reason", "expected"),
        [
            ("end_turn", FinishReason.COMPLETE),
            ("stop_sequence", FinishReason.COMPLETE),
            ("max_tokens", FinishReason.MAX_TOKENS),
            ("refusal", FinishReason.CONTENT_FILTER),
            ("something_unrecognized", FinishReason.ERROR),
        ],
    )
    def test_maps_stop_reason(self, stop_reason: str, expected: FinishReason) -> None:
        body = make_claude_success_body(stop_reason=stop_reason)
        response = ClaudeResponseParser().parse(body, latency_ms=1.0)
        assert response.metrics.finish_reason is expected

    def test_ignores_non_text_content_blocks(self) -> None:
        body = make_claude_success_body()
        body["content"] = [
            {"type": "tool_use", "id": "x", "name": "y", "input": {}},
            {"type": "text", "text": "final answer"},
        ]
        response = ClaudeResponseParser().parse(body, latency_ms=1.0)
        assert response.content == "final answer"


class TestParseMalformedResponses:
    def test_missing_content_raises_parsing_error(self) -> None:
        body = make_claude_success_body()
        del body["content"]
        with pytest.raises(LLMResponseParsingError):
            ClaudeResponseParser().parse(body, latency_ms=1.0)

    def test_missing_usage_raises_parsing_error(self) -> None:
        body = make_claude_success_body()
        del body["usage"]
        with pytest.raises(LLMResponseParsingError):
            ClaudeResponseParser().parse(body, latency_ms=1.0)

    def test_missing_model_raises_parsing_error(self) -> None:
        body = make_claude_success_body()
        del body["model"]
        with pytest.raises(LLMResponseParsingError):
            ClaudeResponseParser().parse(body, latency_ms=1.0)

    def test_malformed_usage_shape_raises_parsing_error(self) -> None:
        body = make_claude_success_body()
        body["usage"] = {"input_tokens": 5}  # missing output_tokens
        with pytest.raises(LLMResponseParsingError):
            ClaudeResponseParser().parse(body, latency_ms=1.0)
