"""Domain-specific exceptions for the Query Intelligence Library.

Every failure mode a caller of `querymind.query_library` can hit is one
of these — never a bare `KeyError`/`ValueError` leaking out of an
internal dict/list lookup. Mirrors `querymind.metadata.exceptions` and
`querymind.business_knowledge.exceptions` exactly.

Content-quality problems (a duplicate question, an empty
`business_concepts` tuple, ...) are deliberately *not* exceptions — see
`querymind.query_library.validator` — those are reported as data
(`ValidationIssue`), not raised, since a caller validating a catalog file
wants every problem at once, not a crash on the first one.
"""

from __future__ import annotations


class QueryLibraryError(Exception):
    """Base class for every exception raised by `querymind.query_library`."""


class LibraryNotLoadedError(QueryLibraryError):
    """Raised when the library is read before `QueryLibraryRegistry.load()` runs."""

    def __init__(self) -> None:
        super().__init__(
            "Query example library has not been loaded yet. Call QueryLibraryRegistry.load() first."
        )


class ExampleNotFoundError(QueryLibraryError):
    """Raised when a requested example id does not exist in the loaded library."""

    def __init__(self, example_id: str) -> None:
        self.example_id = example_id
        super().__init__(f"No query example with id {example_id!r} exists in the loaded library.")


class DuplicateExampleError(QueryLibraryError):
    """Raised when two catalog entries declare the same example id."""

    def __init__(self, example_id: str) -> None:
        self.example_id = example_id
        super().__init__(f"Example id {example_id!r} is declared more than once in the library.")


class LibraryLoadError(QueryLibraryError):
    """Raised when the examples data source fails to load or validate."""

    def __init__(self, source: str, reason: str) -> None:
        self.source = source
        self.reason = reason
        super().__init__(f"Failed to load query example library from {source!r}: {reason}")
