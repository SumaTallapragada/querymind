"""End-to-end tests against the real, fully wired SQL Generation stack.

Wires `SQLGenerationEngine` -> `LLMAdapter` -> `ClaudeProvider` ->
`HttpxTransport` together exactly as production would, down to real
JSON-over-HTTP request/response handling -- `httpx.MockTransport` stands
in for a live network socket, since there is no live Anthropic API
available (or appropriate) to call from a test suite. Mirrors
`tests/llm/test_integration.py`'s approach for the layer below this one.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from querymind.llm.adapter import LLMAdapter
from querymind.llm.client import HttpxTransport
from querymind.llm.exceptions import LLMPermanentError
from querymind.llm.providers.claude import ClaudeProvider
from querymind.prompt_compiler.models import CompiledPrompt
from querymind.sql_generation.engine import SQLGenerationEngine
from querymind.sql_generation.exceptions import SQLExtractionError
from querymind.sql_generation.models import ExtractionMethod, SQLStatementType

from .conftest import make_config

_MockHandler = Callable[[httpx.Request], httpx.Response]


def _claude_success_body(text: str) -> dict[str, object]:
    return {
        "id": "msg_01",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 187, "output_tokens": 42},
    }


def _engine_for(handler: _MockHandler) -> SQLGenerationEngine:
    transport = HttpxTransport(httpx.Client(transport=httpx.MockTransport(handler)))
    config = make_config()
    provider = ClaudeProvider(config, transport=transport)
    adapter = LLMAdapter(provider, config)
    return SQLGenerationEngine(adapter)


def test_fenced_sql_response_end_to_end(compiled_prompt: CompiledPrompt) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        text = (
            "Here's the query you asked for:\n"
            "```sql\n"
            "SELECT c.customer_id, SUM(o.total_amount) AS total_revenue\n"
            "FROM customers c\n"
            "JOIN orders o ON o.customer_id = c.customer_id\n"
            "GROUP BY c.customer_id\n"
            "ORDER BY total_revenue DESC\n"
            "LIMIT 10\n"
            "```"
        )
        return httpx.Response(200, json=_claude_success_body(text))

    engine = _engine_for(handler)
    generated = engine.generate(compiled_prompt)

    assert generated.sql.startswith("SELECT c.customer_id")
    assert generated.sql.endswith(";")
    assert generated.statement_type is SQLStatementType.SELECT
    assert generated.statistics.extraction_method is ExtractionMethod.FENCED_SQL_BLOCK
    assert generated.llm_metrics.token_usage.prompt_tokens == 187


def test_plain_unfenced_sql_response_end_to_end(compiled_prompt: CompiledPrompt) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_claude_success_body("SELECT * FROM customers"))

    engine = _engine_for(handler)
    generated = engine.generate(compiled_prompt)

    assert generated.sql == "SELECT * FROM customers;"
    assert generated.statistics.extraction_method is ExtractionMethod.RAW_TEXT


def test_extraction_failure_end_to_end(compiled_prompt: CompiledPrompt) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_claude_success_body("   "))

    engine = _engine_for(handler)
    with pytest.raises(SQLExtractionError):
        engine.generate(compiled_prompt)


def test_llm_permanent_failure_propagates_end_to_end(compiled_prompt: CompiledPrompt) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"type": "error", "error": {"message": "invalid API key"}})

    engine = _engine_for(handler)
    with pytest.raises(LLMPermanentError):
        engine.generate(compiled_prompt)
