"""The Semantic Schema Linker — QueryMind Phase 6.

Maps a `querymind.nlu.QueryContext` (a parsed question's business
concept *names* — `"customer"`, `"revenue"`, `"region"`, ...) onto the
real database schema, using only `querymind.metadata.MetadataRegistry`
(the Metadata Engine's structural + business-dictionary view of the
schema) and `RelationshipGraph` — never `querymind.models` (SQLAlchemy)
directly.

Matching is entirely deterministic: exact identifier match, business
dictionary (display name / search keywords), declared synonyms, a small
rule-based alias/abbreviation expansion, `difflib`-based fuzzy string
similarity, and substring containment — in that priority order. No
embeddings, no vector search, no LLM.

**Never silently guesses.** When several schema objects plausibly match
a concept with no clear winner, or nothing matches at all, that concept
is recorded as an `Ambiguity` on the output `LinkedQueryContext` instead
of an automatic pick — see `models.py` for exactly what "resolved" means
here.

Explicitly out of scope for this package (later phases):

- Generating SQL from a `LinkedQueryContext`.
- Building an LLM prompt, retrieving few-shot examples, or calling a
  model.

The single public entry point is `SchemaLinker.link`.
"""

from __future__ import annotations

from querymind.schema_linker.exceptions import EmptyRegistryError, SchemaLinkerError
from querymind.schema_linker.linker import SchemaLinker
from querymind.schema_linker.models import (
    Ambiguity,
    ConceptKind,
    LinkCandidate,
    LinkedQueryContext,
    MatchTier,
    ResolvedColumn,
    ResolvedFilter,
    ResolvedMetric,
    ResolvedRelationship,
    ResolvedSort,
    ResolvedTable,
)

__all__ = [
    "Ambiguity",
    "ConceptKind",
    "EmptyRegistryError",
    "LinkCandidate",
    "LinkedQueryContext",
    "MatchTier",
    "ResolvedColumn",
    "ResolvedFilter",
    "ResolvedMetric",
    "ResolvedRelationship",
    "ResolvedSort",
    "ResolvedTable",
    "SchemaLinker",
    "SchemaLinkerError",
]
