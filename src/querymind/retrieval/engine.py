"""The Knowledge Retrieval Engine: turns a `LinkedQueryContext` into a `RetrievedKnowledgeBundle`.

`RetrievalEngine` is the single public entry point for this package. It
scores every example in the `QueryLibraryRegistry` against one
`LinkedQueryContext` (`RetrievalScorer`), ranks and truncates to the
top-K (`ExampleRanker`), attaches match explanations
(`ExplanationBuilder`), and records run statistics
(`RetrievalStatisticsCollector`). Nothing here generates SQL, builds a
prompt, or calls an LLM — see the `querymind.retrieval` package
docstring for that boundary.
"""

from __future__ import annotations

import time

from querymind.business_knowledge.registry import BusinessKnowledgeRegistry
from querymind.query_library.registry import QueryLibraryRegistry
from querymind.retrieval.cache import InMemoryRetrievalCache, RetrievalCache
from querymind.retrieval.exceptions import InvalidTopKError
from querymind.retrieval.explanations import ExplanationBuilder
from querymind.retrieval.matcher import ConceptSchemaKeywordMatcher
from querymind.retrieval.models import RetrievedKnowledgeBundle
from querymind.retrieval.ranker import ExampleRanker
from querymind.retrieval.scorer import RetrievalScorer
from querymind.retrieval.statistics import RetrievalStatisticsCollector
from querymind.schema_linker.models import LinkedQueryContext

#: Used when a caller doesn't pass `top_k` to `retrieve()`.
DEFAULT_TOP_K = 5


class RetrievalEngine:
    """Retrieves the top-K most relevant `QueryExample`s for one `LinkedQueryContext`.

    Depends on `QueryLibraryRegistry` (the candidate pool — required)
    and, optionally, `BusinessKnowledgeRegistry` (for canonicalizing
    business-concept terms before comparing them — the business concept
    overlap signal falls back to plain string comparison without one).
    Every other collaborator (`RetrievalScorer`, `ExampleRanker`,
    `ExplanationBuilder`, `RetrievalStatisticsCollector`, `RetrievalCache`)
    is constructor-injected with a sensible default, so a caller can
    swap in custom signal weights, a different cache, etc. without
    touching this class.

    The Metadata Engine is consumed indirectly: every `LinkedQueryContext`
    this engine receives already carries the real `TableMetadata`/
    `ColumnMetadata` objects the Schema Linker resolved (via the Metadata
    Engine) — this class never queries a `MetadataRegistry` itself, and
    never imports `querymind.models`.
    """

    def __init__(
        self,
        query_library: QueryLibraryRegistry,
        business_knowledge: BusinessKnowledgeRegistry | None = None,
        cache: RetrievalCache | None = None,
        scorer: RetrievalScorer | None = None,
        ranker: ExampleRanker | None = None,
        explanation_builder: ExplanationBuilder | None = None,
        statistics_collector: RetrievalStatisticsCollector | None = None,
        default_top_k: int = DEFAULT_TOP_K,
    ) -> None:
        self._query_library = query_library
        self._business_knowledge = business_knowledge
        self._cache = cache or InMemoryRetrievalCache()
        self._scorer = scorer or RetrievalScorer(
            business_knowledge=business_knowledge, cache=self._cache
        )
        self._ranker = ranker or ExampleRanker()
        matcher = ConceptSchemaKeywordMatcher(
            business_knowledge=business_knowledge, cache=self._cache
        )
        self._explanation_builder = explanation_builder or ExplanationBuilder(matcher)
        self._statistics_collector = statistics_collector or RetrievalStatisticsCollector()
        self._default_top_k = default_top_k

    def retrieve(
        self, linked_query_context: LinkedQueryContext, top_k: int | None = None
    ) -> RetrievedKnowledgeBundle:
        """Retrieve the `top_k` (default `DEFAULT_TOP_K`) examples most relevant to `linked_query_context`.

        Raises `querymind.retrieval.exceptions.InvalidTopKError` if
        `top_k` isn't a positive integer.
        """
        resolved_top_k = top_k if top_k is not None else self._default_top_k
        if resolved_top_k <= 0:
            raise InvalidTopKError(resolved_top_k)
        started = time.perf_counter()

        self._query_library.load()
        if self._business_knowledge is not None:
            self._business_knowledge.load()
        candidates = self._query_library.find_examples(lambda _example: True)

        scored = [
            (example, self._scorer.score(linked_query_context, example)) for example in candidates
        ]
        top_ranked = self._ranker.rank(scored, resolved_top_k)
        retrieved = tuple(
            self._explanation_builder.build(linked_query_context, example, score)
            for example, score in top_ranked
        )

        latency_ms = (time.perf_counter() - started) * 1000
        statistics = self._statistics_collector.collect(
            latency_ms=latency_ms,
            top_k=resolved_top_k,
            candidate_count=len(candidates),
            retrieved=retrieved,
        )

        return RetrievedKnowledgeBundle(
            linked_query_context=linked_query_context,
            retrieved_examples=retrieved,
            statistics=statistics,
        )
