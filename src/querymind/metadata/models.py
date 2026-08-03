"""Strongly typed, immutable metadata objects.

These are **not** ORM models — nothing here is mapped to a database
table, and nothing here can be used to run a query. They are the plain,
serializable description of the schema that every future Text-to-SQL
component (prompt builder, schema linker, evaluation harness, admin UI,
documentation generator) is expected to depend on instead of importing
`querymind.models` directly.

Every model is frozen (`model_config = ConfigDict(frozen=True)`) and uses
`tuple`, never `list`, for collections — a frozen Pydantic model still
allows in-place mutation of a `list` attribute (`.append(...)` bypasses
Pydantic's assignment validation entirely), so `tuple` is what actually
makes these objects immutable, not just their top-level attributes.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ConstraintKind(str, Enum):
    """The two constraint types `ConstraintMetadata` represents.

    Primary keys and foreign keys are modeled separately
    (`PrimaryKeyMetadata`, `ForeignKeyMetadata`) since callers almost
    always want to ask about them specifically, rather than filtering a
    generic constraint list by kind.
    """

    UNIQUE = "unique"
    CHECK = "check"


class RelationshipDirection(str, Enum):
    """Cardinality of a relationship, from the source table's point of view."""

    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


class PrimaryKeyMetadata(_FrozenModel):
    """A table's primary key constraint."""

    name: str
    columns: tuple[str, ...]


class ForeignKeyMetadata(_FrozenModel):
    """A single foreign key constraint from one table to another."""

    name: str
    columns: tuple[str, ...] = Field(description="Local column(s) that hold the reference.")
    referred_table: str
    referred_columns: tuple[str, ...]
    ondelete: str | None = Field(
        default=None, description="e.g. 'RESTRICT', 'CASCADE', 'SET NULL'."
    )


class ConstraintMetadata(_FrozenModel):
    """A unique or check constraint that isn't a primary/foreign key."""

    name: str
    kind: ConstraintKind
    columns: tuple[str, ...] = Field(
        default=(), description="Populated for UNIQUE constraints; usually empty for CHECK."
    )
    expression: str | None = Field(
        default=None, description="The SQL predicate text, populated for CHECK constraints."
    )


class IndexMetadata(_FrozenModel):
    """A database index."""

    name: str
    columns: tuple[str, ...]
    unique: bool
    where: str | None = Field(
        default=None, description="Partial-index predicate text, if any (Postgres-specific)."
    )


class EnumMetadata(_FrozenModel):
    """A Python `enum.Enum` backing one or more columns.

    Traces back to the concrete class so a consumer can, if it needs to,
    resolve the authoritative Python type — without importing
    `querymind.models` itself to get there.
    """

    name: str = Field(description="The constraint/type name, e.g. 'customer_segment_valid_values'.")
    values: tuple[str, ...]
    python_class: str = Field(
        description="Fully qualified class name, e.g. 'querymind.models.customer.CustomerSegment'."
    )
    table_name: str
    column_name: str


class ColumnMetadata(_FrozenModel):
    """Complete description of a single column: structure plus business meaning.

    Structural fields (`sql_type`, `nullable`, `primary_key`, ...) are
    populated by `MetadataExtractor` directly from SQLAlchemy. Business
    fields (`description`, `synonyms`, `example_value`, `display_name`,
    `search_keywords`, `is_sensitive`) start empty/`None` and are filled
    in by `ColumnDictionary.enrich()` from the independent dictionary data
    source — never hardcoded here or in the ORM model.
    """

    table_name: str
    name: str
    sql_type: str = Field(description="Rendered SQL type, e.g. 'VARCHAR(255)', 'NUMERIC(12, 2)'.")
    python_type: str = Field(description="Python type name, e.g. 'str', 'int', 'Decimal'.")
    nullable: bool
    primary_key: bool
    unique: bool
    autoincrement: bool
    default: str | None = None
    foreign_key: ForeignKeyMetadata | None = None
    enum: EnumMetadata | None = None

    # -- business layer (populated by ColumnDictionary.enrich) -----------
    description: str | None = None
    synonyms: tuple[str, ...] = ()
    example_value: str | None = None
    display_name: str | None = None
    search_keywords: tuple[str, ...] = ()
    is_sensitive: bool = False


class RelationshipMetadata(_FrozenModel):
    """An ORM-level relationship between two tables (a `relationship()` attribute)."""

    name: str = Field(description="The relationship attribute name, e.g. 'orders'.")
    source_table: str
    target_table: str
    source_columns: tuple[str, ...]
    target_columns: tuple[str, ...]
    direction: RelationshipDirection
    back_populates: str | None = None


class TableMetadata(_FrozenModel):
    """Complete description of a single table: structure plus business meaning."""

    name: str
    columns: tuple[ColumnMetadata, ...]
    primary_key: PrimaryKeyMetadata
    foreign_keys: tuple[ForeignKeyMetadata, ...] = ()
    unique_constraints: tuple[ConstraintMetadata, ...] = ()
    check_constraints: tuple[ConstraintMetadata, ...] = ()
    indexes: tuple[IndexMetadata, ...] = ()

    # -- business layer (populated by ColumnDictionary.enrich) -----------
    description: str | None = None
    synonyms: tuple[str, ...] = ()


class DatabaseMetadata(_FrozenModel):
    """The complete semantic description of the database — the engine's output.

    This is the single object every future consumer (prompt builder,
    schema linker, evaluation harness, admin UI, documentation generator)
    should hold onto: everything else in this package exists to produce,
    enrich, cache, or serialize one of these.
    """

    tables: tuple[TableMetadata, ...]
    relationships: tuple[RelationshipMetadata, ...] = ()
    enums: tuple[EnumMetadata, ...] = ()
    generated_at: datetime = Field(
        description="When this snapshot was extracted — informational only, "
        "not used by any equality/lookup logic."
    )


class TableDictionaryEntry(_FrozenModel):
    """One table's worth of business metadata, as loaded from the dictionary data source."""

    table: str
    description: str
    synonyms: tuple[str, ...] = ()


class ColumnDictionaryEntry(_FrozenModel):
    """One column's worth of business metadata, as loaded from the dictionary data source."""

    table: str
    column: str
    description: str
    example_value: str | None = None
    synonyms: tuple[str, ...] = ()
    display_name: str | None = None
    search_keywords: tuple[str, ...] = ()
    is_sensitive: bool = False
