"""The Metadata Engine — the single source of truth for the database schema.

This package is infrastructure, not an AI component: it contains no LLM
calls, no prompt engineering, no retrieval, no SQL generation, and no
schema-linking logic. It answers exactly one question — "what does the
database look like, structurally and in business terms?" — and every
future Text-to-SQL component is expected to ask that question here,
never by importing `querymind.models` or connecting to PostgreSQL
directly.

The public surface is `MetadataRegistry`: construct one with a
`MetadataExtractor` (pointed at `querymind.models.base.Base.registry`)
and, optionally, a `ColumnDictionary` (`ColumnDictionary.default()` loads
the business dictionary shipped with this package), then call `load()`.
"""

from querymind.metadata.cache import InMemoryMetadataCache, MetadataCache
from querymind.metadata.dictionary import ColumnDictionary
from querymind.metadata.exceptions import (
    ColumnNotFoundError,
    DictionaryLoadError,
    MetadataError,
    MetadataNotLoadedError,
    RelationshipNotFoundError,
    TableNotFoundError,
)
from querymind.metadata.extractor import MetadataExtractor
from querymind.metadata.models import (
    ColumnDictionaryEntry,
    ColumnMetadata,
    ConstraintKind,
    ConstraintMetadata,
    DatabaseMetadata,
    EnumMetadata,
    ForeignKeyMetadata,
    IndexMetadata,
    PrimaryKeyMetadata,
    RelationshipDirection,
    RelationshipMetadata,
    TableDictionaryEntry,
    TableMetadata,
)
from querymind.metadata.registry import MetadataRegistry
from querymind.metadata.relationships import GraphEdge, RelationshipGraph
from querymind.metadata.serializer import MetadataSerializer

__all__ = [
    "ColumnDictionary",
    "ColumnDictionaryEntry",
    "ColumnMetadata",
    "ColumnNotFoundError",
    "ConstraintKind",
    "ConstraintMetadata",
    "DatabaseMetadata",
    "DictionaryLoadError",
    "EnumMetadata",
    "ForeignKeyMetadata",
    "GraphEdge",
    "InMemoryMetadataCache",
    "IndexMetadata",
    "MetadataCache",
    "MetadataError",
    "MetadataExtractor",
    "MetadataNotLoadedError",
    "MetadataRegistry",
    "MetadataSerializer",
    "PrimaryKeyMetadata",
    "RelationshipDirection",
    "RelationshipGraph",
    "RelationshipMetadata",
    "RelationshipNotFoundError",
    "TableDictionaryEntry",
    "TableMetadata",
    "TableNotFoundError",
]
