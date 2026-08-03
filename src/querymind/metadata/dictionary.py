"""The independent business-metadata layer.

`ColumnDictionary` holds table/column descriptions, synonyms, example
values, display names, search keywords, and sensitivity flags — sourced
from `querymind/metadata/data/dictionary.yaml`, never hardcoded into the
ORM models in `querymind.models`. `MetadataExtractor` only ever knows
about SQLAlchemy structure; this class is the only thing that knows about
business meaning, and `enrich()` is the one place the two get merged.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from querymind.metadata.loader import DEFAULT_DICTIONARY_PATH, load_dictionary_file
from querymind.metadata.models import (
    ColumnDictionaryEntry,
    ColumnMetadata,
    DatabaseMetadata,
    TableDictionaryEntry,
    TableMetadata,
)


class ColumnDictionary:
    """Business-metadata lookup, independent of both the ORM and the extractor.

    Construct via `ColumnDictionary.from_file(path)` (or `.default()` for
    the dictionary shipped with this package); the plain constructor
    accepts already-loaded entries, which is what makes this class easy
    to unit test with a handful of in-memory entries instead of a real
    YAML file.
    """

    def __init__(
        self,
        tables: Mapping[str, TableDictionaryEntry],
        columns: Mapping[tuple[str, str], ColumnDictionaryEntry],
    ) -> None:
        self._tables = dict(tables)
        self._columns = dict(columns)

    @classmethod
    def from_file(cls, path: Path) -> ColumnDictionary:
        """Build a `ColumnDictionary` from a dictionary YAML file at `path`."""
        tables, columns = load_dictionary_file(path)
        return cls(tables=tables, columns=columns)

    @classmethod
    def default(cls) -> ColumnDictionary:
        """Build a `ColumnDictionary` from the dictionary shipped with this package."""
        return cls.from_file(DEFAULT_DICTIONARY_PATH)

    def get_table_entry(self, table_name: str) -> TableDictionaryEntry | None:
        """Return the business entry for `table_name`, if one exists."""
        return self._tables.get(table_name)

    def get_column_entry(self, table_name: str, column_name: str) -> ColumnDictionaryEntry | None:
        """Return the business entry for `table_name.column_name`, if one exists."""
        return self._columns.get((table_name, column_name))

    def enrich(self, database: DatabaseMetadata) -> DatabaseMetadata:
        """Return a new `DatabaseMetadata` with business fields merged in.

        Every `TableMetadata`/`ColumnMetadata` is frozen, so this builds
        new instances via `model_copy(update=...)` rather than mutating —
        `database` itself is left untouched. Tables/columns with no
        matching dictionary entry pass through unchanged.
        """
        enriched_tables = tuple(self._enrich_table(table) for table in database.tables)
        return database.model_copy(update={"tables": enriched_tables})

    def _enrich_table(self, table: TableMetadata) -> TableMetadata:
        entry = self.get_table_entry(table.name)
        enriched_columns = tuple(
            self._enrich_column(table.name, column) for column in table.columns
        )
        if entry is None:
            return table.model_copy(update={"columns": enriched_columns})
        return table.model_copy(
            update={
                "columns": enriched_columns,
                "description": entry.description,
                "synonyms": entry.synonyms,
            }
        )

    def _enrich_column(self, table_name: str, column: ColumnMetadata) -> ColumnMetadata:
        entry = self.get_column_entry(table_name, column.name)
        if entry is None:
            return column
        return column.model_copy(
            update={
                "description": entry.description,
                "synonyms": entry.synonyms,
                "example_value": entry.example_value,
                "display_name": entry.display_name,
                "search_keywords": entry.search_keywords,
                "is_sensitive": entry.is_sensitive,
            }
        )
