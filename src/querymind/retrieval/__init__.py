"""The Knowledge Retrieval Engine (KRE) — QueryMind Phase 9.

Retrieves the most relevant knowledge required for SQL generation: given
one `querymind.schema_linker.LinkedQueryContext`, ranks the
`querymind.query_library.QueryExample`s most similar to it and returns
the top-K, each with a full, explainable score breakdown.

Consumes all four previously built engines — the Query Intelligence
Library (the candidate pool), the Business Knowledge Engine
(canonicalizing business-concept terms before comparing them), the
Schema Linker (via its `LinkedQueryContext` output, this package's
input), and the Metadata Engine (indirectly, through the real
`TableMetadata`/`ColumnMetadata` objects already embedded in a
`LinkedQueryContext`) — without inspecting a SQLAlchemy model anywhere.

Scoring is entirely deterministic: eight independent signals (intent
similarity, business concept overlap, schema/table/column overlap, SQL
feature overlap, keyword overlap, difficulty similarity), each a set
overlap or a small rule-based check, combined by configurable weights.
No embeddings, no vector search, no BM25, no LLM.

This is **not** a Prompt Builder and does not generate SQL — that is a
later phase this package deliberately stops short of.

The public surface is `RetrievalEngine.retrieve`.
"""

from __future__ import annotations

from querymind.retrieval.engine import DEFAULT_TOP_K, RetrievalEngine
from querymind.retrieval.exceptions import InvalidTopKError, RetrievalError
from querymind.retrieval.models import (
    RetrievalScore,
    RetrievalStatistics,
    RetrievedExample,
    RetrievedKnowledgeBundle,
    SignalBreakdown,
    SignalContribution,
    SignalName,
)

__all__ = [
    "DEFAULT_TOP_K",
    "InvalidTopKError",
    "RetrievalEngine",
    "RetrievalError",
    "RetrievalScore",
    "RetrievalStatistics",
    "RetrievedExample",
    "RetrievedKnowledgeBundle",
    "SignalBreakdown",
    "SignalContribution",
    "SignalName",
]
