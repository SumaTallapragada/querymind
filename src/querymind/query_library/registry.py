"""The single point of access to the query example library.

Every future consumer — a Retrieval Engine, an admin UI, an evaluation
harness — is expected to depend on `QueryLibraryRegistry`, never read
`examples.yaml` directly. Coordinates three independent pieces this
package builds: a library source (`querymind.query_library.catalog.
load_library` by default), `QueryExampleSearch` (rebuilt from whatever's
currently loaded), and `LibraryCache` (avoiding re-reading the YAML file
on every call) — without being any of them itself. Mirrors
`querymind.business_knowledge.registry.BusinessKnowledgeRegistry`'s
design exactly.
"""

from __future__ import annotations

from collections.abc import Callable

from querymind.query_library.cache import InMemoryLibraryCache, LibraryCache
from querymind.query_library.catalog import load_library
from querymind.query_library.exceptions import ExampleNotFoundError, LibraryNotLoadedError
from querymind.query_library.models import Difficulty, QueryExample, QueryExampleLibrary
from querymind.query_library.search import QueryExampleSearch


class QueryLibraryRegistry:
    """Loads, caches, and answers questions about the query example library.

    Constructed with its dependencies (a library source callable,
    optional cache) rather than building them itself — there is no
    module-level singleton anywhere in this package. Callers that want a
    process-wide shared instance are expected to construct one
    `QueryLibraryRegistry` themselves and pass it around, the same way
    `MetadataRegistry`/`BusinessKnowledgeRegistry` work.
    """

    def __init__(
        self,
        library_source: Callable[[], QueryExampleLibrary] = load_library,
        cache: LibraryCache[QueryExampleLibrary] | None = None,
    ) -> None:
        self._library_source = library_source
        self._cache: LibraryCache[QueryExampleLibrary] = cache or InMemoryLibraryCache()

    def load(self) -> QueryExampleLibrary:
        """Return the loaded library, reading it once and reusing the cache thereafter."""
        cached = self._cache.get()
        if cached is not None:
            return cached
        return self.refresh()

    def refresh(self) -> QueryExampleLibrary:
        """Force re-reading the library source, bypassing whatever is cached."""
        library = self._library_source()
        self._cache.set(library)
        return library

    def get_example(self, example_id: str) -> QueryExample:
        """Return one example by id. Raises `ExampleNotFoundError` if it doesn't exist."""
        library = self._require_loaded()
        for example in library.examples:
            if example.id == example_id:
                return example
        raise ExampleNotFoundError(example_id)

    def list_examples(self) -> tuple[str, ...]:
        """Return every example id, in catalog order."""
        library = self._require_loaded()
        return tuple(example.id for example in library.examples)

    def find_examples(self, predicate: Callable[[QueryExample], bool]) -> tuple[QueryExample, ...]:
        """Return every example for which `predicate` is true."""
        library = self._require_loaded()
        return tuple(example for example in library.examples if predicate(example))

    def search_by_tags(self, tag: str) -> tuple[QueryExample, ...]:
        """Return every example tagged with `tag` (case-insensitive). See `QueryExampleSearch.by_tag`."""
        return self._search().by_tag(tag)

    def search_by_difficulty(self, difficulty: Difficulty) -> tuple[QueryExample, ...]:
        """Return every example at exactly `difficulty`."""
        return self._search().by_difficulty(difficulty)

    def search_by_business_concept(self, concept: str) -> tuple[QueryExample, ...]:
        """Return every example touching `concept` (case-insensitive)."""
        return self._search().by_business_concept(concept)

    def search_by_title(self, text: str) -> tuple[QueryExample, ...]:
        """Return every example whose title contains `text` (case-insensitive substring match)."""
        return self._search().by_title(text)

    def search_by_keywords(self, keywords: tuple[str, ...]) -> tuple[QueryExample, ...]:
        """Return every example whose question contains every keyword in `keywords`."""
        return self._search().by_keywords(keywords)

    def _search(self) -> QueryExampleSearch:
        return QueryExampleSearch(self._require_loaded().examples)

    def _require_loaded(self) -> QueryExampleLibrary:
        loaded = self._cache.get()
        if loaded is None:
            raise LibraryNotLoadedError()
        return loaded
