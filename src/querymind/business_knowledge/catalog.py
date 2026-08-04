"""Assembles a validated `BusinessKnowledgeCatalog` from loaded concepts.

The composition step between `loader.py` (pure YAML I/O, no cross-entry
validation) and `registry.py` (load/cache/query orchestration): checks
every concept id is unique, then wraps the concepts into one immutable
`BusinessKnowledgeCatalog` snapshot. Mirrors the role
`querymind.metadata.dictionary.ColumnDictionary` plays for the Metadata
Engine, scoped down to what this simpler, single-collection catalog
needs.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from querymind.business_knowledge.exceptions import DuplicateConceptError
from querymind.business_knowledge.loader import DEFAULT_CATALOG_PATH, load_concepts_file
from querymind.business_knowledge.models import BusinessConcept, BusinessKnowledgeCatalog


def build_catalog(concepts: Iterable[BusinessConcept]) -> BusinessKnowledgeCatalog:
    """Assemble `concepts` into a `BusinessKnowledgeCatalog`.

    Raises `DuplicateConceptError` if two concepts declare the same
    `id` — every id must be unique for `BusinessKnowledgeRegistry.get_concept`
    to have exactly one answer.
    """
    concepts = tuple(concepts)
    seen: set[str] = set()
    for concept in concepts:
        if concept.id in seen:
            raise DuplicateConceptError(concept.id)
        seen.add(concept.id)
    return BusinessKnowledgeCatalog(concepts=concepts, loaded_at=datetime.now(UTC))


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> BusinessKnowledgeCatalog:
    """Load and assemble the catalog at `path` in one step (the common case).

    Composes `loader.load_concepts_file` + `build_catalog` — the default
    `catalog_source` a `BusinessKnowledgeRegistry` is constructed with
    when no other source is injected.
    """
    return build_catalog(load_concepts_file(path))
