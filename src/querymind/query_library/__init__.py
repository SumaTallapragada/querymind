"""The Query Intelligence Library — QueryMind Phase 8.

The curated knowledge base that will power future retrieval: a
YAML-sourced catalog of hand-verified, gold-standard
natural-language-question-to-SQL examples, covering every major area of
the QueryMind schema (customers, orders, payments, products, suppliers,
inventory, warehouses, shipments, promotions, reviews, returns) and
every major analytical pattern (financial metrics, time-based analysis,
Top-N, trend analysis, filtering, grouping, joins, aggregations).

This is **not** a vector database, an embedding store, or an LLM prompt
library — it is plain, deterministic, YAML-backed data plus deterministic
keyword search over it. No embeddings, no vector search, no LLM, no SQL
execution, and no retrieval/ranking logic: that is a later phase this
package deliberately stops short of.

The public surface is `QueryLibraryRegistry`: construct one (its default
`library_source` reads the catalog shipped with this package), call
`load()`, then `get_example()`/`find_examples()`/`search_by_*()`.
"""

from __future__ import annotations

from querymind.query_library.exceptions import (
    DuplicateExampleError,
    ExampleNotFoundError,
    LibraryLoadError,
    LibraryNotLoadedError,
    QueryLibraryError,
)
from querymind.query_library.models import (
    Difficulty,
    QueryContextSummary,
    QueryExample,
    QueryExampleLibrary,
    ResultShape,
    SQLDialect,
)
from querymind.query_library.registry import QueryLibraryRegistry
from querymind.query_library.search import QueryExampleSearch
from querymind.query_library.serializer import QueryLibrarySerializer
from querymind.query_library.validator import (
    QueryLibraryValidator,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)

__all__ = [
    "Difficulty",
    "DuplicateExampleError",
    "ExampleNotFoundError",
    "LibraryLoadError",
    "LibraryNotLoadedError",
    "QueryContextSummary",
    "QueryExample",
    "QueryExampleLibrary",
    "QueryExampleSearch",
    "QueryLibraryError",
    "QueryLibraryRegistry",
    "QueryLibrarySerializer",
    "QueryLibraryValidator",
    "ResultShape",
    "SQLDialect",
    "ValidationIssue",
    "ValidationReport",
    "ValidationSeverity",
]
