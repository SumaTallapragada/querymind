"""Response-parsing abstraction.

`ResponseParser` is the provider-agnostic interface for turning a
provider's raw JSON response body into an `LLMResponse` — the actual
field mapping is entirely provider-specific (Claude's response shape has
nothing in common with any other provider's), so each concrete
implementation lives alongside its provider, e.g.
`querymind.llm.providers.claude.ClaudeResponseParser`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from querymind.llm.models import LLMResponse


class ResponseParser(Protocol):
    """Parses one provider's raw JSON response body into an `LLMResponse`."""

    def parse(self, raw_response: Mapping[str, Any], *, latency_ms: float) -> LLMResponse:
        """Parse `raw_response` into an `LLMResponse`.

        `retry_count` on the returned response's metrics is always `0` —
        a parser only ever sees the response from one successful call;
        `querymind.llm.adapter.LLMAdapter` is what stamps the real,
        adapter-observed retry count onto the final response. Raises
        `querymind.llm.exceptions.LLMResponseParsingError` if
        `raw_response` doesn't have the shape this parser expects.
        """
        ...
