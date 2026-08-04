"""Natural Language Understanding (NLU) engine for QueryMind — Phase 5.

Turns a natural language business question into a structured, immutable
`QueryContext` using only deterministic techniques (regex, keyword
matching, rule-based parsing, a fixed business vocabulary) — no
embeddings, no vector search, no LLM call.

Explicitly out of scope for this package (later phases):

- Resolving `QueryContext`'s business concept names against the real
  database schema or the `querymind.metadata` registry (schema linking).
- Generating SQL from a `QueryContext`.
- Building an LLM prompt or calling a model.

The single public entry point is `QueryParser.parse` (or the
module-level `parse_question` convenience function).
"""

from __future__ import annotations

from querymind.nlu.exceptions import EmptyQuestionError, NLUError
from querymind.nlu.models import (
    AggregationType,
    ComparisonOperator,
    FilterExpression,
    Intent,
    LimitExpression,
    MetricExpression,
    QueryContext,
    SortDirection,
    SortExpression,
    TimeExpression,
    TimePeriod,
)
from querymind.nlu.parser import QueryParser, parse_question

__all__ = [
    "AggregationType",
    "ComparisonOperator",
    "EmptyQuestionError",
    "FilterExpression",
    "Intent",
    "LimitExpression",
    "MetricExpression",
    "NLUError",
    "QueryContext",
    "QueryParser",
    "SortDirection",
    "SortExpression",
    "TimeExpression",
    "TimePeriod",
    "parse_question",
]
