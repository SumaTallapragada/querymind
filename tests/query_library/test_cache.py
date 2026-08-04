from __future__ import annotations

from querymind.query_library.cache import InMemoryLibraryCache
from querymind.query_library.models import QueryExampleLibrary


def test_starts_empty() -> None:
    cache: InMemoryLibraryCache[QueryExampleLibrary] = InMemoryLibraryCache()
    assert cache.get() is None
    assert cache.is_populated is False


def test_set_then_get_returns_the_stored_value(sample_library: QueryExampleLibrary) -> None:
    cache: InMemoryLibraryCache[QueryExampleLibrary] = InMemoryLibraryCache()
    cache.set(sample_library)
    assert cache.get() is sample_library
    assert cache.is_populated is True


def test_set_replaces_the_previous_value(sample_library: QueryExampleLibrary) -> None:
    from querymind.query_library.catalog import build_library

    cache: InMemoryLibraryCache[QueryExampleLibrary] = InMemoryLibraryCache()
    cache.set(sample_library)
    other = build_library(())
    cache.set(other)
    assert cache.get() is other


def test_clear_discards_the_cached_value(sample_library: QueryExampleLibrary) -> None:
    cache: InMemoryLibraryCache[QueryExampleLibrary] = InMemoryLibraryCache()
    cache.set(sample_library)
    cache.clear()
    assert cache.get() is None
    assert cache.is_populated is False
