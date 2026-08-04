"""The Business Knowledge Engine — QueryMind Phase 7.

Understands business terminology (`"Revenue"`, `"Top Customer"`,
`"AOV"`, ...) and maps it to business *semantics* — a `BusinessConcept`
with a description, a computation, and example questions — using a
deterministic, YAML-sourced catalog. It does not resolve those concepts
against the real database schema (that is the Schema Linker's job, in a
future integration phase this package deliberately stops short of), does
not generate SQL, and does not call an LLM.

Sits between the NLU Engine and the Schema Linker: given the business
terms a `QueryContext` extracted, this package tells you what those
terms *mean* in the business's own vocabulary before anything tries to
map them onto tables and columns.

Matching is entirely deterministic: exact name match, alias match,
synonym match (checked against `related_terms`), then substring
containment — in that priority order. No embeddings, no vector search,
no LLM.

The public surface is `BusinessKnowledgeRegistry`: construct one (its
default `catalog_source` reads the catalog shipped with this package),
call `load()`, then `get_concept()`/`find_concepts()`/`resolve()`.
"""

from __future__ import annotations

from querymind.business_knowledge.exceptions import (
    BusinessKnowledgeError,
    CatalogLoadError,
    ConceptNotFoundError,
    DuplicateConceptError,
    KnowledgeNotLoadedError,
)
from querymind.business_knowledge.models import (
    BusinessAlias,
    BusinessConcept,
    BusinessConceptType,
    BusinessDefinition,
    BusinessFormula,
    BusinessKnowledgeCatalog,
    BusinessMatchType,
    BusinessMetric,
)
from querymind.business_knowledge.registry import BusinessKnowledgeRegistry
from querymind.business_knowledge.serializer import BusinessKnowledgeSerializer

__all__ = [
    "BusinessAlias",
    "BusinessConcept",
    "BusinessConceptType",
    "BusinessDefinition",
    "BusinessFormula",
    "BusinessKnowledgeCatalog",
    "BusinessKnowledgeError",
    "BusinessKnowledgeRegistry",
    "BusinessKnowledgeSerializer",
    "BusinessMatchType",
    "BusinessMetric",
    "CatalogLoadError",
    "ConceptNotFoundError",
    "DuplicateConceptError",
    "KnowledgeNotLoadedError",
]
