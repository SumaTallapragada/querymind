"""Domain-specific exceptions for the Metadata Engine.

Every failure mode a caller of `querymind.metadata` can hit is one of
these — never a bare `KeyError`/`ValueError` leaking out of internal
dict/list lookups. That is what lets a future consumer (prompt builder,
schema linker, admin UI) catch a specific, documented exception type
instead of guessing at what an engine-internal lookup miss looks like.
"""

from __future__ import annotations


class MetadataError(Exception):
    """Base class for every exception raised by the Metadata Engine."""


class MetadataNotLoadedError(MetadataError):
    """Raised when metadata is read before `MetadataRegistry.load()` runs."""

    def __init__(self) -> None:
        super().__init__("Metadata has not been loaded yet. Call MetadataRegistry.load() first.")


class TableNotFoundError(MetadataError):
    """Raised when a requested table name does not exist in loaded metadata."""

    def __init__(self, table_name: str) -> None:
        self.table_name = table_name
        super().__init__(f"No table named {table_name!r} exists in the loaded metadata.")


class ColumnNotFoundError(MetadataError):
    """Raised when a requested column does not exist on a table."""

    def __init__(self, table_name: str, column_name: str) -> None:
        self.table_name = table_name
        self.column_name = column_name
        super().__init__(f"No column named {column_name!r} exists on table {table_name!r}.")


class RelationshipNotFoundError(MetadataError):
    """Raised when a requested relationship does not exist between two tables."""

    def __init__(self, source_table: str, target_table: str) -> None:
        self.source_table = source_table
        self.target_table = target_table
        super().__init__(f"No relationship found between {source_table!r} and {target_table!r}.")


class DictionaryLoadError(MetadataError):
    """Raised when the business dictionary data source fails to load or validate."""

    def __init__(self, source: str, reason: str) -> None:
        self.source = source
        self.reason = reason
        super().__init__(f"Failed to load column dictionary from {source!r}: {reason}")
