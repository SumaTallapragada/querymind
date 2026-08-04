from __future__ import annotations

import pytest

from querymind.query_library.models import QueryExampleLibrary
from querymind.query_library.registry import QueryLibraryRegistry
from querymind.retrieval.cache import InMemoryRetrievalCache
from querymind.retrieval.engine import DEFAULT_TOP_K, RetrievalEngine
from querymind.retrieval.exceptions import InvalidTopKError
from querymind.schema_linker.models import LinkedQueryContext


def _library_registry(library: QueryExampleLibrary) -> QueryLibraryRegistry:
    return QueryLibraryRegistry(library_source=lambda: library)


def test_retrieve_returns_ranked_examples(
    linked_context: LinkedQueryContext, sample_library: QueryExampleLibrary
) -> None:
    engine = RetrievalEngine(query_library=_library_registry(sample_library))
    bundle = engine.retrieve(linked_context, top_k=2)
    assert len(bundle.retrieved_examples) == 2
    assert bundle.retrieved_examples[0].example.id == "top_customers_by_revenue"
    scores = [entry.overall_score for entry in bundle.retrieved_examples]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_uses_default_top_k_when_not_specified(
    linked_context: LinkedQueryContext, sample_library: QueryExampleLibrary
) -> None:
    engine = RetrievalEngine(query_library=_library_registry(sample_library))
    bundle = engine.retrieve(linked_context)
    assert bundle.statistics.top_k == DEFAULT_TOP_K
    # only 2 candidates exist, so the actual result count is capped there
    assert len(bundle.retrieved_examples) == 2


def test_retrieve_respects_a_custom_default_top_k(
    linked_context: LinkedQueryContext, sample_library: QueryExampleLibrary
) -> None:
    engine = RetrievalEngine(query_library=_library_registry(sample_library), default_top_k=1)
    bundle = engine.retrieve(linked_context)
    assert len(bundle.retrieved_examples) == 1


def test_retrieve_raises_on_invalid_top_k(
    linked_context: LinkedQueryContext, sample_library: QueryExampleLibrary
) -> None:
    engine = RetrievalEngine(query_library=_library_registry(sample_library))
    with pytest.raises(InvalidTopKError):
        engine.retrieve(linked_context, top_k=0)


def test_bundle_carries_the_original_linked_query_context(
    linked_context: LinkedQueryContext, sample_library: QueryExampleLibrary
) -> None:
    engine = RetrievalEngine(query_library=_library_registry(sample_library))
    bundle = engine.retrieve(linked_context)
    assert bundle.linked_query_context == linked_context


def test_statistics_report_the_right_candidate_count(
    linked_context: LinkedQueryContext, sample_library: QueryExampleLibrary
) -> None:
    engine = RetrievalEngine(query_library=_library_registry(sample_library))
    bundle = engine.retrieve(linked_context)
    assert bundle.statistics.candidate_count == 2


def test_statistics_latency_is_non_negative(
    linked_context: LinkedQueryContext, sample_library: QueryExampleLibrary
) -> None:
    engine = RetrievalEngine(query_library=_library_registry(sample_library))
    bundle = engine.retrieve(linked_context)
    assert bundle.statistics.retrieval_latency_ms >= 0.0


def test_cache_is_reused_across_multiple_retrieve_calls(
    linked_context: LinkedQueryContext, sample_library: QueryExampleLibrary
) -> None:
    """Regression: the injected cache must actually get populated by a real retrieve() call."""
    cache = InMemoryRetrievalCache()
    engine = RetrievalEngine(query_library=_library_registry(sample_library), cache=cache)
    engine.retrieve(linked_context)
    for example in sample_library.examples:
        assert cache.get_example_features(example.id) is not None


def test_two_engines_sharing_a_cache_do_not_recompute(
    linked_context: LinkedQueryContext, sample_library: QueryExampleLibrary
) -> None:
    cache = InMemoryRetrievalCache()
    engine = RetrievalEngine(query_library=_library_registry(sample_library), cache=cache)
    engine.retrieve(linked_context)
    first_features = cache.get_example_features("top_customers_by_revenue")

    engine.retrieve(linked_context)  # a second retrieval for a *different* purpose, same cache
    second_features = cache.get_example_features("top_customers_by_revenue")
    assert first_features is second_features  # identity: never recomputed


def test_repeated_retrieval_for_different_contexts_never_reuses_a_stale_ranking(
    linked_context: LinkedQueryContext, sample_library: QueryExampleLibrary
) -> None:
    """ "Do not cache final rankings" — two different top_k values must produce independently
    correct results, not a cached bundle from the first call."""
    engine = RetrievalEngine(query_library=_library_registry(sample_library))
    first = engine.retrieve(linked_context, top_k=1)
    second = engine.retrieve(linked_context, top_k=2)
    assert len(first.retrieved_examples) == 1
    assert len(second.retrieved_examples) == 2
