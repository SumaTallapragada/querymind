"""Limit extraction.

Recognizes an explicit row-count cap ("top 5", "first 10", "limit 20")
in a normalized question. Never guesses a default: if the question
doesn't state a number, `extract` returns `None` rather than inventing
one — whether an intent like `TOP_N` needs a fallback default is a
policy decision for a later stage (schema linking / SQL generation),
not a parsing fact.
"""

from __future__ import annotations

import re
from typing import Protocol

from querymind.nlu.models import LimitExpression

_LIMIT_PATTERN = re.compile(r"\b(?:top|first|bottom|last|limit)\s+(\d+)\b")


class LimitExtractor(Protocol):
    """Recognizes an explicit row-count cap in a normalized question."""

    def extract(self, normalized_question: str) -> LimitExpression | None:
        """Return the `LimitExpression` found in `normalized_question`, or `None`."""
        ...


class DefaultLimitExtractor:
    """Rule-based `LimitExtractor` matching an explicit row-count phrase."""

    def extract(self, normalized_question: str) -> LimitExpression | None:
        match = _LIMIT_PATTERN.search(normalized_question)
        if match is None:
            return None
        return LimitExpression(value=int(match.group(1)), raw_text=match.group(0))
