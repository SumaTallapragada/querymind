"""Sort direction and field extraction.

Recognizes explicit sort phrases ("sorted by X descending") and
superlative language ("highest X", "cheapest X") in a normalized
question. When no field is stated explicitly, falls back to the first
already-extracted metric — this stage runs after metric extraction in
the pipeline (see `querymind.nlu.parser.QueryParser`), so that is always
available to fall back on.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from querymind.nlu.entities import DIMENSION_SYNONYMS, ENTITY_SYNONYMS
from querymind.nlu.metrics import METRIC_SYNONYMS
from querymind.nlu.models import MetricExpression, SortDirection, SortExpression

_KNOWN_FIELDS: dict[str, str] = {**ENTITY_SYNONYMS, **DIMENSION_SYNONYMS, **METRIC_SYNONYMS}

_EXPLICIT_PATTERN = re.compile(
    r"(?:sort(?:ed)?|order(?:ed)?)\s+by\s+(?P<field>[a-z]+(?:\s[a-z]+){0,3}?)"
    r"(?:\s+(?P<direction>ascending|asc|descending|desc))?\b"
)

#: Superlative phrase -> direction. "highest"/"most"/"top"/"largest"
#: imply descending order (biggest value first); "lowest"/"least"/
#: "cheapest"/"bottom"/"smallest" imply ascending.
_SUPERLATIVE_PHRASES: dict[str, SortDirection] = {
    "highest": SortDirection.DESCENDING,
    "most": SortDirection.DESCENDING,
    "largest": SortDirection.DESCENDING,
    "greatest": SortDirection.DESCENDING,
    "top": SortDirection.DESCENDING,
    "best": SortDirection.DESCENDING,
    "lowest": SortDirection.ASCENDING,
    "least": SortDirection.ASCENDING,
    "smallest": SortDirection.ASCENDING,
    "cheapest": SortDirection.ASCENDING,
    "bottom": SortDirection.ASCENDING,
    "worst": SortDirection.ASCENDING,
}


class SortExtractor(Protocol):
    """Recognizes the requested sort field and direction in a normalized question."""

    def extract(
        self, normalized_question: str, metrics: Sequence[MetricExpression]
    ) -> SortExpression | None:
        """Return the `SortExpression` found in `normalized_question`, or `None`.

        `metrics` is that question's already-extracted metrics, used as a
        fallback field when a sort is implied but no field is named.
        """
        ...


def _resolve_field(candidate: str) -> str | None:
    words = candidate.strip().split()
    for start in range(len(words)):
        phrase = " ".join(words[start:])
        if phrase in _KNOWN_FIELDS:
            return _KNOWN_FIELDS[phrase]
    return None


class DefaultSortExtractor:
    """Rule-based `SortExtractor` matching explicit "sort by" phrases and superlative language."""

    def extract(
        self, normalized_question: str, metrics: Sequence[MetricExpression]
    ) -> SortExpression | None:
        explicit = _EXPLICIT_PATTERN.search(normalized_question)
        if explicit:
            direction = (
                SortDirection.ASCENDING
                if explicit.group("direction") in ("asc", "ascending")
                else SortDirection.DESCENDING
            )
            field = _resolve_field(explicit.group("field"))
            if field is None and metrics:
                field = metrics[0].name
            if field is not None:
                return SortExpression(field=field, direction=direction, raw_text=explicit.group(0))

        if not metrics:
            return None

        for phrase in sorted(_SUPERLATIVE_PHRASES, key=len, reverse=True):
            pattern = rf"\b{re.escape(phrase)}\b"
            if phrase in ("most", "least"):
                # Exclude "at most"/"at least" — those are filter
                # thresholds (see `querymind.nlu.filters`), not a sort.
                pattern = rf"(?<!at ){pattern}"
            match = re.search(pattern, normalized_question)
            if match:
                direction = _SUPERLATIVE_PHRASES[phrase]
                return SortExpression(
                    field=metrics[0].name, direction=direction, raw_text=match.group(0)
                )

        return None
