"""The single point of access to the database's semantic metadata.

Every future Text-to-SQL component — prompt builder, schema linker,
evaluation harness, admin UI — is expected to depend on
`MetadataRegistry`, never on `querymind.models` directly. It coordinates
the three independent pieces this package builds:
`MetadataExtractor` (SQLAlchemy structure), `ColumnDictionary` (business
meaning), and `MetadataCache` (avoiding re-extracting on every call) —
without being any of them itself.
"""

from __future__ import annotations

from collections.abc import Callable

from querymind.metadata.cache import InMemoryMetadataCache, MetadataCache
from querymind.metadata.dictionary import ColumnDictionary
from querymind.metadata.exceptions import (
    ColumnNotFoundError,
    MetadataNotLoadedError,
    TableNotFoundError,
)
from querymind.metadata.extractor import MetadataExtractor
from querymind.metadata.models import (
    ColumnMetadata,
    DatabaseMetadata,
    RelationshipMetadata,
    TableMetadata,
)
from querymind.metadata.relationships import RelationshipGraph


class MetadataRegistry:
    """Loads, caches, and answers questions about the database's metadata.

    Constructed with its dependencies (extractor, optional dictionary,
    optional cache) rather than building them itself — there is no
    module-level singleton anywhere in this package. Callers that want a
    process-wide shared instance are expected to construct one
    `MetadataRegistry` themselves and pass it around (e.g. via a FastAPI
    dependency in a later phase); this class does not provide one itself.
    """

    def __init__(
        self,
        extractor: MetadataExtractor,
        dictionary: ColumnDictionary | None = None,
        cache: MetadataCache[DatabaseMetadata] | None = None,
    ) -> None:
        self._extractor = extractor
        self._dictionary = dictionary
        self._cache: MetadataCache[DatabaseMetadata] = cache or InMemoryMetadataCache()

    def load(self) -> DatabaseMetadata:
        """Return the loaded metadata, extracting it once and reusing the cache thereafter."""
        cached = self._cache.get()
        if cached is not None:
            return cached
        return self.refresh()

    def refresh(self) -> DatabaseMetadata:
        """Force re-extraction (and re-enrichment), bypassing whatever is cached."""
        database = self._extractor.extract()
        if self._dictionary is not None:
            database = self._dictionary.enrich(database)
        self._cache.set(database)
        return database

    def get_table(self, table_name: str) -> TableMetadata:
        """Return one table's metadata. Raises `TableNotFoundError` if it doesn't exist."""
        database = self._require_loaded()
        for table in database.tables:
            if table.name == table_name:
                return table
        raise TableNotFoundError(table_name)

    def get_column(self, table_name: str, column_name: str) -> ColumnMetadata:
        """Return one column's metadata. Raises `TableNotFoundError`/`ColumnNotFoundError`."""
        table = self.get_table(table_name)
        for column in table.columns:
            if column.name == column_name:
                return column
        raise ColumnNotFoundError(table_name, column_name)

    def find_columns(
        self, predicate: Callable[[ColumnMetadata], bool]
    ) -> tuple[ColumnMetadata, ...]:
        """Return every column across every table for which `predicate` is true."""
        database = self._require_loaded()
        return tuple(
            column for table in database.tables for column in table.columns if predicate(column)
        )

    def find_tables(self, predicate: Callable[[TableMetadata], bool]) -> tuple[TableMetadata, ...]:
        """Return every table for which `predicate` is true."""
        database = self._require_loaded()
        return tuple(table for table in database.tables if predicate(table))

    def list_tables(self) -> tuple[str, ...]:
        """Return every table name, in extraction order (alphabetical)."""
        database = self._require_loaded()
        return tuple(table.name for table in database.tables)

    def list_relationships(self) -> tuple[RelationshipMetadata, ...]:
        """Return every relationship across the whole schema."""
        database = self._require_loaded()
        return database.relationships

    def build_graph(self) -> RelationshipGraph:
        """Build a `RelationshipGraph` over the currently loaded metadata."""
        database = self._require_loaded()
        return RelationshipGraph(
            tables=(table.name for table in database.tables),
            relationships=database.relationships,
        )

    def _require_loaded(self) -> DatabaseMetadata:
        loaded = self._cache.get()
        if loaded is None:
            raise MetadataNotLoadedError()
        return loaded
