"""Filter extraction.

Recognizes `field <operator> value` constraints in a normalized question
using deterministic regex patterns for comparative language ("greater
than", "at least", ...), resolving the field against the same business
vocabulary used by `entities.py` and `metrics.py`.
"""

from __future__ import annotations

import re
from typing import Protocol

from querymind.nlu.entities import DIMENSION_SYNONYMS, ENTITY_SYNONYMS
from querymind.nlu.metrics import METRIC_SYNONYMS
from querymind.nlu.models import ComparisonOperator, FilterExpression

#: A field phrase is at most three words immediately preceding a
#: comparator, e.g. "average order value" — bounded so the regex can't
#: backtrack across an entire sentence; `_resolve_field` trims leading
#: filler words (like "the" or "with") from whatever this captures.
_FIELD = r"(?:[a-z]+\s+){0,2}[a-z]+"
#: A numeric value, with optional leading currency symbol, thousands
#: separators, and a decimal part: "50", "$50", "1,200.50".
_NUMBER = r"\$?\d[\d,]*(?:\.\d+)?"
#: A short categorical value: up to four words.
_WORDS = r"[a-z]+(?:\s[a-z]+){0,3}"

#: (regex with named `field`/`value` groups, operator). Checked in
#: order — a longer overlapping phrase ("greater than or equal to") is
#: listed before the shorter phrase it contains ("greater than"), so it
#: gets the chance to match first.
_COMPARATOR_PATTERNS: tuple[tuple[str, ComparisonOperator], ...] = (
    (
        rf"(?P<field>{_FIELD})\s+at least\s+(?P<value>{_NUMBER})",
        ComparisonOperator.GREATER_THAN_OR_EQUAL,
    ),
    (
        rf"(?P<field>{_FIELD})\s+at most\s+(?P<value>{_NUMBER})",
        ComparisonOperator.LESS_THAN_OR_EQUAL,
    ),
    (
        rf"(?P<field>{_FIELD})\s+greater than or equal to\s+(?P<value>{_NUMBER})",
        ComparisonOperator.GREATER_THAN_OR_EQUAL,
    ),
    (
        rf"(?P<field>{_FIELD})\s+less than or equal to\s+(?P<value>{_NUMBER})",
        ComparisonOperator.LESS_THAN_OR_EQUAL,
    ),
    (
        rf"(?P<field>{_FIELD})\s+(?:greater than|more than|above|over)\s+(?P<value>{_NUMBER})",
        ComparisonOperator.GREATER_THAN,
    ),
    (
        rf"(?P<field>{_FIELD})\s+(?:less than|fewer than|under|below)\s+(?P<value>{_NUMBER})",
        ComparisonOperator.LESS_THAN,
    ),
    (
        rf"(?P<field>{_FIELD})\s+(?:not equal to|not equals|excluding|except)\s+(?P<value>{_WORDS}|{_NUMBER})",
        ComparisonOperator.NOT_EQUALS,
    ),
    (
        rf"(?P<field>{_FIELD})\s+(?:equal to|equals)\s+(?P<value>{_WORDS}|{_NUMBER})",
        ComparisonOperator.EQUALS,
    ),
    (
        rf"(?P<field>{_FIELD})\s+(?:containing|contains|like|named)\s+(?P<value>{_WORDS})",
        ComparisonOperator.CONTAINS,
    ),
    (
        rf"(?P<field>{_FIELD})\s+in\s+(?P<value>{_WORDS})",
        ComparisonOperator.IN,
    ),
)

_KNOWN_FIELDS: dict[str, str] = {**ENTITY_SYNONYMS, **DIMENSION_SYNONYMS, **METRIC_SYNONYMS}


class FilterExtractor(Protocol):
    """Recognizes `field <operator> value` constraints in a normalized question."""

    def extract(self, normalized_question: str) -> tuple[FilterExpression, ...]:
        """Return every filter found in `normalized_question`, in first-mention order."""
        ...


def _resolve_field(candidate: str) -> str | None:
    """Resolve a captured field phrase against the known business vocabulary.

    Tries the full captured phrase first, then progressively shorter
    trailing word sequences, so filler words captured ahead of the real
    field name (e.g. "the average order value" -> "average order value")
    don't prevent a match.
    """
    words = candidate.strip().split()
    for start in range(len(words)):
        phrase = " ".join(words[start:])
        if phrase in _KNOWN_FIELDS:
            return _KNOWN_FIELDS[phrase]
    return None


class DefaultFilterExtractor:
    """Rule-based `FilterExtractor` matching comparative language against known fields."""

    def extract(self, normalized_question: str) -> tuple[FilterExpression, ...]:
        claimed: list[tuple[int, int]] = []
        found: list[tuple[int, FilterExpression]] = []

        for pattern, operator in _COMPARATOR_PATTERNS:
            for match in re.finditer(pattern, normalized_question):
                span = match.span()
                if any(span[0] < end and start < span[1] for start, end in claimed):
                    continue
                field = _resolve_field(match.group("field"))
                if field is None:
                    continue
                value = match.group("value").strip().rstrip(".,?!")
                if not value:
                    continue
                claimed.append(span)
                found.append(
                    (
                        span[0],
                        FilterExpression(
                            field=field,
                            operator=operator,
                            value=value,
                            raw_text=match.group(0).strip(),
                        ),
                    )
                )

        found.sort(key=lambda pair: pair[0])
        return tuple(expression for _position, expression in found)
