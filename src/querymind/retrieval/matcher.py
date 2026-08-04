"""Raw overlap computation between a `LinkedQueryContext` and a `QueryExample`.

Pure set-overlap logic, no scoring policy — `querymind.retrieval.signals`
turns these overlaps into normalized 0-1 signal scores, and
`querymind.retrieval.explanations` uses the same overlaps to populate a
`RetrievedExample`'s `matched_*` fields. Keeping this one module means
"what counts as a match" is decided exactly once, not once per consumer.

Business concept matching optionally consumes a `BusinessKnowledgeRegistry`
(constructor-injected) to canonicalize terms — e.g. resolving "AOV" and
"average order value" to the same concept id — before comparing; without
one, comparison falls back to plain lowercase string equality.
"""

from __future__ import annotations

import re

from querymind.business_knowledge.registry import BusinessKnowledgeRegistry
from querymind.query_library.models import QueryExample
from querymind.retrieval.cache import ExampleFeatures, RetrievalCache
from querymind.schema_linker.models import LinkedQueryContext

#: Generic function words stripped before keyword overlap — the goal is
#: comparing *content* words ("revenue", "customers"), not boilerplate
#: question phrasing shared by nearly every question.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "of",
        "in",
        "on",
        "by",
        "to",
        "for",
        "and",
        "or",
        "with",
        "we",
        "our",
        "us",
        "do",
        "does",
        "did",
        "what",
        "how",
        "many",
        "much",
        "show",
        "me",
        "list",
        "get",
        "find",
        "which",
        "who",
        "that",
        "this",
        "these",
        "those",
        "at",
        "from",
        "as",
        "all",
    }
)


def _tokenize(text: str) -> frozenset[str]:
    """Lowercase, split on non-alphanumerics, and drop stopwords/1-character tokens."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(word for word in words if word not in _STOPWORDS and len(word) > 1)


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """Intersection-over-union of two sets, or 0.0 if both are empty (no signal, not a perfect match)."""
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


class ConceptSchemaKeywordMatcher:
    """Computes the raw overlap between a `LinkedQueryContext` and a `QueryExample`.

    `cache` (optional) memoizes each `QueryExample`'s derived feature sets
    (they never change across retrieval calls, since the library is
    static) — see `querymind.retrieval.cache.ExampleFeatures`.
    """

    def __init__(
        self,
        business_knowledge: BusinessKnowledgeRegistry | None = None,
        cache: RetrievalCache | None = None,
    ) -> None:
        self._business_knowledge = business_knowledge
        self._cache = cache

    def context_business_concepts(self, context: LinkedQueryContext) -> frozenset[str]:
        """Every business concept the NLU engine found in the question, canonicalized if possible."""
        return self._canonicalize(context.query_context.business_concepts)

    def context_tables(self, context: LinkedQueryContext) -> frozenset[str]:
        return frozenset(context.resolved_table_names)

    def context_columns(self, context: LinkedQueryContext) -> frozenset[str]:
        columns: set[str] = set()
        for metric in context.metrics:
            columns.add(f"{metric.column.table_name}.{metric.column.name}")
        for dimension in context.dimensions:
            columns.add(f"{dimension.column.table_name}.{dimension.column.name}")
        for filter_ in context.filters:
            columns.add(f"{filter_.column.table_name}.{filter_.column.name}")
        if context.sort is not None:
            columns.add(f"{context.sort.column.table_name}.{context.sort.column.name}")
        return frozenset(columns)

    def context_schema_objects(self, context: LinkedQueryContext) -> frozenset[str]:
        return self.context_tables(context) | self.context_columns(context)

    def context_keywords(self, context: LinkedQueryContext) -> frozenset[str]:
        return _tokenize(context.query_context.normalized_question)

    def example_features(self, example: QueryExample) -> ExampleFeatures:
        """The example's derived feature sets, computed once and cached (if a cache was injected)."""
        if self._cache is not None:
            cached = self._cache.get_example_features(example.id)
            if cached is not None:
                return cached

        table_set = frozenset(ref.split(".", 1)[0] for ref in example.linked_schema_objects)
        column_set = frozenset(ref for ref in example.linked_schema_objects if "." in ref)
        features = ExampleFeatures(
            concept_set=self._canonicalize(example.business_concepts),
            # Union in the derived bare table names too, not just the raw
            # entries — `context_schema_objects` does the same on the
            # context side (tables | columns), so without this, a
            # context's bare "customers" could never match an example
            # whose linked_schema_objects are all "customers.customer_id"
            # style qualified columns, even though they're clearly about
            # the same table.
            schema_object_set=frozenset(example.linked_schema_objects) | table_set,
            table_set=table_set,
            column_set=column_set,
            keyword_set=_tokenize(
                f"{example.title} {example.natural_language_question} {example.normalized_question}"
            ),
        )

        if self._cache is not None:
            self._cache.set_example_features(example.id, features)
        return features

    def matched_business_concepts(
        self, context: LinkedQueryContext, example: QueryExample
    ) -> tuple[str, ...]:
        matched = (
            self.context_business_concepts(context) & self.example_features(example).concept_set
        )
        return tuple(sorted(matched))

    def matched_schema_objects(
        self, context: LinkedQueryContext, example: QueryExample
    ) -> tuple[str, ...]:
        matched = (
            self.context_schema_objects(context) & self.example_features(example).schema_object_set
        )
        return tuple(sorted(matched))

    def matched_tables(self, context: LinkedQueryContext, example: QueryExample) -> tuple[str, ...]:
        matched = self.context_tables(context) & self.example_features(example).table_set
        return tuple(sorted(matched))

    def matched_columns(
        self, context: LinkedQueryContext, example: QueryExample
    ) -> tuple[str, ...]:
        matched = self.context_columns(context) & self.example_features(example).column_set
        return tuple(sorted(matched))

    def matched_keywords(
        self, context: LinkedQueryContext, example: QueryExample
    ) -> tuple[str, ...]:
        matched = self.context_keywords(context) & self.example_features(example).keyword_set
        return tuple(sorted(matched))

    def _canonicalize(self, terms: tuple[str, ...]) -> frozenset[str]:
        if self._business_knowledge is None:
            return frozenset(term.strip().lower() for term in terms)
        canonical: set[str] = set()
        for term in terms:
            resolved = self._business_knowledge.resolve(term)
            canonical.add(resolved.id if resolved is not None else term.strip().lower())
        return frozenset(canonical)
