"""The eight deterministic retrieval signals.

Each signal is its own small class implementing `RetrievalSignal`,
independently testable in isolation — `querymind.retrieval.scorer.
RetrievalScorer` is what combines them with weights into one overall
score. No embeddings, no machine learning: every signal here is a set
overlap (via `querymind.retrieval.matcher`), a keyword-detection rule
over `gold_sql` text, or a small deterministic distance/lookup table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar, Protocol

from querymind.query_library.models import Difficulty, QueryExample
from querymind.retrieval.matcher import ConceptSchemaKeywordMatcher, jaccard
from querymind.retrieval.models import SignalName
from querymind.schema_linker.models import LinkedQueryContext


@dataclass(frozen=True, slots=True)
class SignalResult:
    """The outcome of one `RetrievalSignal.compute` call."""

    score: float
    detail: str


def _implies_aggregation(context: LinkedQueryContext) -> bool:
    """Whether *any* aggregation is implied — the overall query-level one, or a per-metric one.

    `QueryContext.aggregation` is the single *overall* reducer NLU
    resolved (see `querymind.nlu.parser.QueryParser._resolve_aggregation`)
    and can be `None` even when individual `ResolvedMetric`s each carry
    their own `.aggregation` (from the source `MetricExpression`) — both
    must be checked, or a metric like "total revenue" with no
    query-level aggregation would be treated as implying no GROUP BY/
    aggregate function at all.
    """
    if context.query_context.aggregation is not None:
        return True
    return any(metric.aggregation is not None for metric in context.metrics)


class RetrievalSignal(Protocol):
    """One deterministic, independently computable retrieval signal."""

    name: ClassVar[SignalName]

    def compute(self, context: LinkedQueryContext, example: QueryExample) -> SignalResult:
        """Score how well `example` matches `context` along this one dimension, in `[0.0, 1.0]`."""
        ...


class IntentSimilaritySignal:
    """Whether the question's NLU intent matches the example's expected intent.

    Binary: intent is a categorical label (`top_n`, `count`, `trend`,
    ...) with no natural notion of "close but not quite," unlike
    `DifficultySimilaritySignal`'s ordered scale.
    """

    name: ClassVar[SignalName] = SignalName.INTENT_SIMILARITY

    def compute(self, context: LinkedQueryContext, example: QueryExample) -> SignalResult:
        query_intent = context.query_context.intent.value
        example_intent = example.query_context.intent.strip().lower()
        if query_intent == example_intent:
            return SignalResult(1.0, f"Intent matches: {query_intent!r}.")
        return SignalResult(
            0.0, f"Intent differs: query is {query_intent!r}, example is {example_intent!r}."
        )


class BusinessConceptOverlapSignal:
    """Jaccard overlap between the question's business concepts and the example's."""

    name: ClassVar[SignalName] = SignalName.BUSINESS_CONCEPT_OVERLAP

    def __init__(self, matcher: ConceptSchemaKeywordMatcher) -> None:
        self._matcher = matcher

    def compute(self, context: LinkedQueryContext, example: QueryExample) -> SignalResult:
        query_concepts = self._matcher.context_business_concepts(context)
        example_concepts = self._matcher.example_features(example).concept_set
        score = jaccard(query_concepts, example_concepts)
        matched = sorted(query_concepts & example_concepts)
        detail = (
            f"{len(matched)} shared business concept(s): {', '.join(matched)}."
            if matched
            else "No shared business concepts."
        )
        return SignalResult(score, detail)


class SchemaOverlapSignal:
    """Jaccard overlap between every 'table'/'table.column' the question touches and the example's."""

    name: ClassVar[SignalName] = SignalName.SCHEMA_OVERLAP

    def __init__(self, matcher: ConceptSchemaKeywordMatcher) -> None:
        self._matcher = matcher

    def compute(self, context: LinkedQueryContext, example: QueryExample) -> SignalResult:
        query_objects = self._matcher.context_schema_objects(context)
        example_objects = self._matcher.example_features(example).schema_object_set
        score = jaccard(query_objects, example_objects)
        matched = sorted(query_objects & example_objects)
        detail = (
            f"{len(matched)} shared schema object(s): {', '.join(matched)}."
            if matched
            else "No shared schema objects."
        )
        return SignalResult(score, detail)


class TableOverlapSignal:
    """Jaccard overlap restricted to table names only (a coarser cut of `SchemaOverlapSignal`)."""

    name: ClassVar[SignalName] = SignalName.TABLE_OVERLAP

    def __init__(self, matcher: ConceptSchemaKeywordMatcher) -> None:
        self._matcher = matcher

    def compute(self, context: LinkedQueryContext, example: QueryExample) -> SignalResult:
        query_tables = self._matcher.context_tables(context)
        example_tables = self._matcher.example_features(example).table_set
        score = jaccard(query_tables, example_tables)
        matched = sorted(query_tables & example_tables)
        detail = (
            f"{len(matched)} shared table(s): {', '.join(matched)}."
            if matched
            else "No shared tables."
        )
        return SignalResult(score, detail)


class ColumnOverlapSignal:
    """Jaccard overlap restricted to qualified column references only."""

    name: ClassVar[SignalName] = SignalName.COLUMN_OVERLAP

    def __init__(self, matcher: ConceptSchemaKeywordMatcher) -> None:
        self._matcher = matcher

    def compute(self, context: LinkedQueryContext, example: QueryExample) -> SignalResult:
        query_columns = self._matcher.context_columns(context)
        example_columns = self._matcher.example_features(example).column_set
        score = jaccard(query_columns, example_columns)
        matched = sorted(query_columns & example_columns)
        detail = (
            f"{len(matched)} shared column(s): {', '.join(matched)}."
            if matched
            else "No shared columns."
        )
        return SignalResult(score, detail)


class KeywordOverlapSignal:
    """Jaccard overlap between the question's content keywords and the example's."""

    name: ClassVar[SignalName] = SignalName.KEYWORD_OVERLAP

    def __init__(self, matcher: ConceptSchemaKeywordMatcher) -> None:
        self._matcher = matcher

    def compute(self, context: LinkedQueryContext, example: QueryExample) -> SignalResult:
        query_keywords = self._matcher.context_keywords(context)
        example_keywords = self._matcher.example_features(example).keyword_set
        score = jaccard(query_keywords, example_keywords)
        matched = sorted(query_keywords & example_keywords)
        detail = (
            f"{len(matched)} shared keyword(s): {', '.join(matched)}."
            if matched
            else "No shared keywords."
        )
        return SignalResult(score, detail)


#: (predicate over a LinkedQueryContext, SQL-text regex, human label) —
#: what structural SQL feature this predicate implies, and how to detect
#: it deterministically in `gold_sql` via keyword/regex matching.
_SQL_FEATURE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("JOIN", re.compile(r"\bjoin\b", re.IGNORECASE)),
    ("GROUP BY", re.compile(r"\bgroup\s+by\b", re.IGNORECASE)),
    ("ORDER BY", re.compile(r"\border\s+by\b", re.IGNORECASE)),
    ("LIMIT", re.compile(r"\blimit\b", re.IGNORECASE)),
    ("WHERE", re.compile(r"\bwhere\b", re.IGNORECASE)),
    ("aggregate function", re.compile(r"\b(sum|count|avg|min|max)\s*\(", re.IGNORECASE)),
    ("HAVING", re.compile(r"\bhaving\b", re.IGNORECASE)),
)


class SQLFeatureOverlapSignal:
    """Whether the SQL structure `gold_sql` uses matches what the question structurally implies.

    Expected features are derived from `LinkedQueryContext`'s own shape
    (multiple resolved tables imply a JOIN, an aggregation implies GROUP
    BY and an aggregate function, ...), then detected in `gold_sql` via
    deterministic keyword/regex matching — never by parsing or executing
    the SQL. Unlike the overlap signals, this is a requirement-satisfaction
    check, not a similarity: a question with no structural requirements
    at all scores 1.0 (vacuously satisfied), not 0.0.
    """

    name: ClassVar[SignalName] = SignalName.SQL_FEATURE_OVERLAP

    def compute(self, context: LinkedQueryContext, example: QueryExample) -> SignalResult:
        expected = self._expected_features(context)
        if not expected:
            return SignalResult(1.0, "Question implies no particular SQL structure.")

        present = {
            label for label, pattern in _SQL_FEATURE_RULES if pattern.search(example.gold_sql)
        }
        matched = expected & present
        score = len(matched) / len(expected)
        detail = (
            f"{len(matched)}/{len(expected)} expected SQL feature(s) present: {', '.join(sorted(matched))}."
            if matched
            else f"None of the {len(expected)} expected SQL feature(s) were found in gold_sql."
        )
        return SignalResult(score, detail)

    @staticmethod
    def _expected_features(context: LinkedQueryContext) -> set[str]:
        expected: set[str] = set()
        if len(context.resolved_table_names) > 1 or context.relationship_paths:
            expected.add("JOIN")
        if context.dimensions or _implies_aggregation(context):
            expected.add("GROUP BY")
        if _implies_aggregation(context):
            expected.add("aggregate function")
        if context.sort is not None:
            expected.add("ORDER BY")
        if context.query_context.limit is not None:
            expected.add("LIMIT")
        if context.filters:
            expected.add("WHERE")
        return expected


#: Ordered scale `DifficultySimilaritySignal` measures distance over.
_DIFFICULTY_ORDER: tuple[Difficulty, ...] = (
    Difficulty.BEGINNER,
    Difficulty.INTERMEDIATE,
    Difficulty.ADVANCED,
    Difficulty.EXPERT,
)
#: Structural complexity points -> implied difficulty, coarser bucket per row.
_COMPLEXITY_THRESHOLDS: tuple[tuple[int, Difficulty], ...] = (
    (2, Difficulty.BEGINNER),
    (4, Difficulty.INTERMEDIATE),
    (6, Difficulty.ADVANCED),
)


class DifficultySimilaritySignal:
    """How close the example's stated difficulty is to the question's implied structural complexity.

    Difficulty is an ordered scale (unlike `IntentSimilaritySignal`'s
    categorical one), so this gives graduated partial credit for
    "close enough" rather than an all-or-nothing match.
    """

    name: ClassVar[SignalName] = SignalName.DIFFICULTY_SIMILARITY

    def compute(self, context: LinkedQueryContext, example: QueryExample) -> SignalResult:
        implied = self._implied_difficulty(context)
        implied_index = _DIFFICULTY_ORDER.index(implied)
        example_index = _DIFFICULTY_ORDER.index(example.difficulty)
        distance = abs(implied_index - example_index)
        score = max(0.0, 1.0 - distance / (len(_DIFFICULTY_ORDER) - 1))
        detail = (
            f"Question implies {implied.value!r} difficulty; example is {example.difficulty.value!r} "
            f"({distance} step(s) apart)."
        )
        return SignalResult(score, detail)

    @staticmethod
    def _implied_difficulty(context: LinkedQueryContext) -> Difficulty:
        points = 0
        points += max(0, len(context.resolved_table_names) - 1)
        if _implies_aggregation(context):
            points += 1
        if context.dimensions:
            points += 1
        if context.sort is not None:
            points += 1
        if len(context.filters) > 1:
            points += 1
        if context.query_context.time_expression is not None:
            points += 1
        if context.ambiguities:
            points += 1

        for threshold, difficulty in _COMPLEXITY_THRESHOLDS:
            if points < threshold:
                return difficulty
        return Difficulty.EXPERT
