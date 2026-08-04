"""Assembles a validated `QueryExampleLibrary` from loaded examples.

The composition step between `loader.py` (pure YAML I/O, no cross-entry
validation) and `registry.py` (load/cache/query orchestration): checks
every example id is unique, then wraps the examples into one immutable
`QueryExampleLibrary` snapshot. Mirrors
`querymind.business_knowledge.catalog` exactly.

This is a *hard* invariant (raises `DuplicateExampleError`), distinct
from `querymind.query_library.validator.QueryLibraryValidator`'s "unique
ids" rule, which reports the same problem as data instead of raising —
that module is for comprehensive content-quality diagnostics; this
function is what protects `QueryLibraryRegistry.get_example`'s "exactly
one answer" guarantee at runtime.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from querymind.query_library.exceptions import DuplicateExampleError
from querymind.query_library.loader import DEFAULT_LIBRARY_PATH, load_examples_file
from querymind.query_library.models import QueryExample, QueryExampleLibrary


def build_library(examples: Iterable[QueryExample]) -> QueryExampleLibrary:
    """Assemble `examples` into a `QueryExampleLibrary`.

    Raises `DuplicateExampleError` if two examples declare the same
    `id` — every id must be unique for `QueryLibraryRegistry.get_example`
    to have exactly one answer.
    """
    examples = tuple(examples)
    seen: set[str] = set()
    for example in examples:
        if example.id in seen:
            raise DuplicateExampleError(example.id)
        seen.add(example.id)
    return QueryExampleLibrary(examples=examples, loaded_at=datetime.now(UTC))


def load_library(path: Path = DEFAULT_LIBRARY_PATH) -> QueryExampleLibrary:
    """Load and assemble the library at `path` in one step (the common case).

    Composes `loader.load_examples_file` + `build_library` — the default
    `library_source` a `QueryLibraryRegistry` is constructed with when no
    other source is injected.
    """
    return build_library(load_examples_file(path))
