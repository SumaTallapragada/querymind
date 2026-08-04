"""Extracts SQL text from an LLM's raw response content.

Handles the response shapes a SQL-generation call commonly produces, in
priority order: a ```sql fenced block, a fenced block with no (or a
different) language tag, and finally plain unfenced text. Never
inspects *what* the extracted text says — `SQLExtractor` extracts, it
never validates, parses, or repairs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from querymind.sql_generation.exceptions import SQLExtractionError
from querymind.sql_generation.models import ExtractionMethod

#: A fenced block explicitly tagged ```sql (case-insensitive) — checked first.
_SQL_FENCE_PATTERN = re.compile(r"```sql\s*(.*?)```", re.IGNORECASE | re.DOTALL)

#: Any fenced block at all, tagged or not — checked if no ```sql block was found.
_GENERIC_FENCE_PATTERN = re.compile(r"```\w*\s*(.*?)```", re.DOTALL)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """The SQL text `SQLExtractor` found, plus which strategy found it."""

    sql: str
    method: ExtractionMethod


class SQLExtractor:
    """Pulls SQL text out of an LLM response's raw content.

    Tries, in order: a ```sql fenced block, any other fenced block, then
    the entire response verbatim. The first strategy that matches at all
    decides the outcome — if its content turns out to be empty once
    trimmed, that's treated as a failure rather than falling through to
    a weaker strategy, since a weaker strategy re-matching the same
    (empty) fenced block would not do any better.
    """

    def extract(self, raw_content: str) -> ExtractionResult:
        """Extract SQL from `raw_content`. Raises `SQLExtractionError` if nothing usable is found."""
        sql_fence_match = _SQL_FENCE_PATTERN.search(raw_content)
        if sql_fence_match:
            return self._result(sql_fence_match.group(1), ExtractionMethod.FENCED_SQL_BLOCK)

        generic_fence_match = _GENERIC_FENCE_PATTERN.search(raw_content)
        if generic_fence_match:
            return self._result(generic_fence_match.group(1), ExtractionMethod.FENCED_GENERIC_BLOCK)

        return self._result(raw_content, ExtractionMethod.RAW_TEXT)

    @staticmethod
    def _result(candidate: str, method: ExtractionMethod) -> ExtractionResult:
        sql = candidate.strip()
        if not sql:
            raise SQLExtractionError(
                f"Extraction via {method.value!r} produced no usable SQL text."
            )
        return ExtractionResult(sql=sql, method=method)
