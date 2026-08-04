from __future__ import annotations

from querymind.retrieval.cache import ExampleFeatures, InMemoryRetrievalCache


def _features() -> ExampleFeatures:
    return ExampleFeatures(
        concept_set=frozenset({"revenue"}),
        schema_object_set=frozenset({"orders.total_amount"}),
        table_set=frozenset({"orders"}),
        column_set=frozenset({"orders.total_amount"}),
        keyword_set=frozenset({"revenue"}),
    )


def test_get_returns_none_before_anything_is_cached() -> None:
    cache = InMemoryRetrievalCache()
    assert cache.get_example_features("x") is None


def test_set_then_get_returns_the_stored_value() -> None:
    cache = InMemoryRetrievalCache()
    features = _features()
    cache.set_example_features("x", features)
    assert cache.get_example_features("x") is features


def test_different_example_ids_are_independent() -> None:
    cache = InMemoryRetrievalCache()
    cache.set_example_features("a", _features())
    assert cache.get_example_features("b") is None


def test_clear_discards_every_entry() -> None:
    cache = InMemoryRetrievalCache()
    cache.set_example_features("x", _features())
    cache.clear()
    assert cache.get_example_features("x") is None
