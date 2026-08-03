"""Inspects a SQLAlchemy declarative registry and produces structural metadata.

`MetadataExtractor` never connects to PostgreSQL. Every fact it reports —
column types, nullability, constraints, indexes, enums, relationships —
is derived purely from the in-memory `sqlalchemy.orm.registry` object
(typically `Base.registry` from `querymind.models.base`), which already
knows everything SQLAlchemy knows once the model modules have been
imported. The registry is passed in rather than imported directly here,
so this extractor has no hard dependency on `querymind.models` and can be
pointed at any registry — including a small one built purely for a unit
test.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CheckConstraint, Identity, Table, UniqueConstraint
from sqlalchemy import Enum as SAEnumType
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapper
from sqlalchemy.orm import configure_mappers as sa_configure_mappers
from sqlalchemy.orm import registry as sa_registry
from sqlalchemy.sql.schema import Column

from querymind.metadata.models import (
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
    TableMetadata,
)

_DIALECT: Any = postgresql.dialect()  # type: ignore[no-untyped-call]


def _name_or(name: object, fallback: str) -> str:
    """SQLAlchemy represents "no name given" with an internal sentinel, not
    just `None` — this normalizes any of that (`str`, `None`, or the
    sentinel) down to a definite `str` for our Pydantic models."""
    return name if isinstance(name, str) else fallback


class MetadataExtractor:
    """Derives a `DatabaseMetadata` snapshot from a SQLAlchemy ORM registry.

    Produces *structural* metadata only — the business-facing fields on
    `ColumnMetadata`/`TableMetadata` (description, synonyms, ...) are left
    at their defaults here and filled in later by
    `querymind.metadata.dictionary.ColumnDictionary.enrich()`. Keeping
    those concerns separate is what lets this class stay a pure,
    dependency-free SQLAlchemy reader.
    """

    def __init__(self, registry: sa_registry) -> None:
        self._registry = registry

    def extract(self) -> DatabaseMetadata:
        """Extract the complete structural metadata for every mapped table."""
        sa_configure_mappers()
        return DatabaseMetadata(
            tables=self.extract_tables(),
            relationships=self.extract_relationships(),
            enums=self.extract_enums(),
            generated_at=datetime.now(UTC),
        )

    def extract_tables(self) -> tuple[TableMetadata, ...]:
        """Extract every table: columns, keys, constraints, and indexes."""
        tables = [self._extract_table(table) for table in self._tables()]
        return tuple(sorted(tables, key=lambda table: table.name))

    def extract_relationships(self) -> tuple[RelationshipMetadata, ...]:
        """Extract every ORM `relationship()` attribute across all mappers."""
        sa_configure_mappers()
        relationships = [
            self._extract_relationship(mapper, rel)
            for mapper in self._mappers()
            for rel in mapper.relationships
        ]
        return tuple(sorted(relationships, key=lambda rel: (rel.source_table, rel.name)))

    def extract_enums(self) -> tuple[EnumMetadata, ...]:
        """Extract every Python-`Enum`-backed column across all tables."""
        enums = [
            enum_meta
            for table in self._tables()
            for column in table.columns
            if (enum_meta := self._extract_enum(table, column)) is not None
        ]
        return tuple(sorted(enums, key=lambda enum: (enum.table_name, enum.column_name)))

    # -- internals -----------------------------------------------------

    def _mappers(self) -> tuple[Mapper[Any], ...]:
        return tuple(mapper for mapper in self._registry.mappers if mapper.local_table is not None)

    def _tables(self) -> tuple[Table, ...]:
        # `Mapper.local_table` is typed as the broader `FromClause | None`,
        # but every entry here is a real, mapped `Table` — never a join or
        # subquery — since it came from a plain declarative mapped class.
        return tuple(cast(Table, mapper.local_table) for mapper in self._mappers())

    def _extract_table(self, table: Table) -> TableMetadata:
        primary_key = PrimaryKeyMetadata(
            name=_name_or(table.primary_key.name, f"pk_{table.name}"),
            columns=tuple(column.name for column in table.primary_key.columns),
        )
        foreign_keys = self._extract_foreign_keys(table)
        fk_by_column = self._foreign_keys_by_column(foreign_keys)
        columns = tuple(
            self._extract_column(table, column, fk_by_column.get(column.name))
            for column in table.columns
        )
        return TableMetadata(
            name=table.name,
            columns=columns,
            primary_key=primary_key,
            foreign_keys=foreign_keys,
            unique_constraints=self._extract_unique_constraints(table),
            check_constraints=self._extract_check_constraints(table),
            indexes=self._extract_indexes(table),
        )

    @staticmethod
    def _foreign_keys_by_column(
        foreign_keys: tuple[ForeignKeyMetadata, ...],
    ) -> dict[str, ForeignKeyMetadata]:
        return {
            column_name: foreign_key
            for foreign_key in foreign_keys
            for column_name in foreign_key.columns
        }

    def _extract_column(
        self, table: Table, column: Column[Any], foreign_key: ForeignKeyMetadata | None
    ) -> ColumnMetadata:
        return ColumnMetadata(
            table_name=table.name,
            name=column.name,
            sql_type=str(column.type.compile(dialect=_DIALECT)),
            python_type=self._python_type_name(column),
            nullable=bool(column.nullable),
            primary_key=bool(column.primary_key),
            unique=bool(column.unique),
            autoincrement=bool(column.primary_key)
            and (column.identity is not None or column.autoincrement is True),
            default=self._default_repr(column),
            foreign_key=foreign_key,
            enum=self._extract_enum(table, column),
        )

    @staticmethod
    def _python_type_name(column: Column[Any]) -> str:
        try:
            python_type = column.type.python_type
        except NotImplementedError:
            return "Any"
        return python_type.__name__ if isinstance(python_type, type) else str(python_type)

    @staticmethod
    def _default_repr(column: Column[Any]) -> str | None:
        # An identity-generated column's `server_default` *is* its `Identity`
        # object, not a literal default value — that fact is already
        # captured via `ColumnMetadata.autoincrement`, so it isn't a
        # "default" worth reporting here.
        server_default = column.server_default
        if server_default is not None and not isinstance(server_default, Identity):
            arg = getattr(server_default, "arg", None)
            if arg is not None:
                return str(arg)
        default = column.default
        if default is not None and getattr(default, "is_scalar", False):
            arg = getattr(default, "arg", None)
            if arg is not None:
                return str(arg)
        return None

    @staticmethod
    def _extract_enum(table: Table, column: Column[Any]) -> EnumMetadata | None:
        if not isinstance(column.type, SAEnumType) or column.type.enum_class is None:
            return None
        enum_class = column.type.enum_class
        return EnumMetadata(
            name=_name_or(column.type.name, f"{table.name}_{column.name}_valid_values"),
            values=tuple(column.type.enums),
            python_class=f"{enum_class.__module__}.{enum_class.__qualname__}",
            table_name=table.name,
            column_name=column.name,
        )

    @staticmethod
    def _extract_foreign_keys(table: Table) -> tuple[ForeignKeyMetadata, ...]:
        foreign_keys = [
            ForeignKeyMetadata(
                name=_name_or(constraint.name, ""),
                columns=tuple(column.name for column in constraint.columns),
                referred_table=constraint.referred_table.name,
                referred_columns=tuple(element.column.name for element in constraint.elements),
                ondelete=constraint.ondelete,
            )
            for constraint in table.foreign_key_constraints
        ]
        return tuple(sorted(foreign_keys, key=lambda fk: fk.name))

    @staticmethod
    def _extract_unique_constraints(table: Table) -> tuple[ConstraintMetadata, ...]:
        constraints = [
            ConstraintMetadata(
                name=_name_or(constraint.name, ""),
                kind=ConstraintKind.UNIQUE,
                columns=tuple(column.name for column in constraint.columns),
            )
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        return tuple(sorted(constraints, key=lambda c: c.name))

    @staticmethod
    def _extract_check_constraints(table: Table) -> tuple[ConstraintMetadata, ...]:
        constraints = []
        for constraint in table.constraints:
            if not isinstance(constraint, CheckConstraint):
                continue
            compiled = constraint.sqltext.compile(
                dialect=_DIALECT, compile_kwargs={"literal_binds": True}
            )
            constraints.append(
                ConstraintMetadata(
                    name=_name_or(constraint.name, ""),
                    kind=ConstraintKind.CHECK,
                    expression=str(compiled),
                )
            )
        return tuple(sorted(constraints, key=lambda c: c.name))

    @staticmethod
    def _extract_indexes(table: Table) -> tuple[IndexMetadata, ...]:
        indexes = []
        for index in table.indexes:
            where = index.dialect_kwargs.get("postgresql_where")
            indexes.append(
                IndexMetadata(
                    name=_name_or(index.name, ""),
                    columns=tuple(column.name for column in index.columns),
                    unique=bool(index.unique),
                    where=str(where) if where is not None else None,
                )
            )
        return tuple(sorted(indexes, key=lambda i: i.name))

    @staticmethod
    def _extract_relationship(mapper: Mapper[Any], rel: Any) -> RelationshipMetadata:
        source_columns = tuple(local.name for local, _ in rel.local_remote_pairs)
        target_columns = tuple(remote.name for _, remote in rel.local_remote_pairs)
        source_table = cast(Table, mapper.local_table)
        target_table = cast(Table, rel.mapper.local_table)
        return RelationshipMetadata(
            name=rel.key,
            source_table=source_table.name,
            target_table=target_table.name,
            source_columns=source_columns,
            target_columns=target_columns,
            direction=_relationship_direction(rel.direction.name, bool(rel.uselist)),
            back_populates=rel.back_populates,
        )


def _relationship_direction(raw_direction: str, uselist: bool) -> RelationshipDirection:
    """Normalize SQLAlchemy's direction symbol + `uselist` into our enum.

    SQLAlchemy reports a nullable-unique-FK one-to-one relationship (e.g.
    `OrderItem.review`) with the same `ONETOMANY` direction as a normal
    one-to-many — `uselist=False` is what actually distinguishes them.
    """
    if raw_direction == "MANYTOONE":
        return RelationshipDirection.MANY_TO_ONE
    if raw_direction == "MANYTOMANY":
        return RelationshipDirection.MANY_TO_MANY
    return RelationshipDirection.ONE_TO_MANY if uselist else RelationshipDirection.ONE_TO_ONE
