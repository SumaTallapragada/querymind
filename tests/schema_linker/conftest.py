"""Shared fixtures: a small, fully synthetic schema for schema-linker tests.

Built directly from `querymind.metadata.models` (never from real
SQLAlchemy models) so every test controls its schema precisely —
matching, ambiguity, and relationship-path behavior are all exercised
against exact, known inputs rather than the real (and evolving)
QueryMind schema.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import registry as sa_registry

from querymind.metadata.cache import InMemoryMetadataCache
from querymind.metadata.extractor import MetadataExtractor
from querymind.metadata.models import (
    ColumnMetadata,
    DatabaseMetadata,
    PrimaryKeyMetadata,
    RelationshipDirection,
    RelationshipMetadata,
    TableMetadata,
)
from querymind.metadata.registry import MetadataRegistry


def make_column(
    table_name: str,
    name: str,
    *,
    synonyms: tuple[str, ...] = (),
    search_keywords: tuple[str, ...] = (),
    display_name: str | None = None,
    primary_key: bool = False,
) -> ColumnMetadata:
    return ColumnMetadata(
        table_name=table_name,
        name=name,
        sql_type="VARCHAR",
        python_type="str",
        nullable=not primary_key,
        primary_key=primary_key,
        unique=primary_key,
        autoincrement=primary_key,
        synonyms=synonyms,
        search_keywords=search_keywords,
        display_name=display_name,
    )


def make_table(
    name: str, columns: Iterable[ColumnMetadata], *, synonyms: tuple[str, ...] = ()
) -> TableMetadata:
    columns = tuple(columns)
    pk_columns = tuple(column.name for column in columns if column.primary_key) or (f"{name}_id",)
    return TableMetadata(
        name=name,
        columns=columns,
        primary_key=PrimaryKeyMetadata(name=f"pk_{name}", columns=pk_columns),
        synonyms=synonyms,
    )


def build_registry(
    tables: Iterable[TableMetadata], relationships: Iterable[RelationshipMetadata] = ()
) -> MetadataRegistry:
    """A `MetadataRegistry` pre-loaded with a synthetic schema, via the public `cache=` constructor param.

    The `MetadataExtractor` passed in is never actually invoked — the
    cache is pre-populated, so `MetadataRegistry.load()` returns it
    directly without ever calling `extractor.extract()`.
    """
    database = DatabaseMetadata(
        tables=tuple(tables), relationships=tuple(relationships), generated_at=datetime.now(UTC)
    )
    cache: InMemoryMetadataCache[DatabaseMetadata] = InMemoryMetadataCache()
    cache.set(database)
    return MetadataRegistry(MetadataExtractor(sa_registry()), cache=cache)


@pytest.fixture
def sample_registry() -> MetadataRegistry:
    """A small e-commerce-flavored schema: `customers` <- `orders`.

    Deliberately includes columns exercising every match tier:
    - `customers.customer_id` / `orders.order_id`: EXACT (via table name)
    - `orders.total_amount`: SYNONYM ("revenue"), BUSINESS_DICTIONARY
      (display name "Total")
    - `orders.qty`: ALIAS (abbreviation of "quantity")
    - `customers.region`: two ambiguous siblings sharing the synonym
      "location" with `orders.ship_region` at equal confidence
    - `customers.customer_name`: PARTIAL match target for "name"
    """
    customers = make_table(
        "customers",
        [
            make_column("customers", "customer_id", primary_key=True),
            make_column("customers", "customer_name", display_name="Customer Name"),
            make_column("customers", "region", synonyms=("location",), display_name="Region"),
        ],
    )
    orders = make_table(
        "orders",
        [
            make_column("orders", "order_id", primary_key=True),
            make_column("orders", "customer_id"),
            make_column(
                "orders",
                "total_amount",
                synonyms=("revenue", "order total"),
                search_keywords=("total",),
                display_name="Total",
            ),
            make_column("orders", "qty"),
            make_column(
                "orders", "ship_region", synonyms=("location",), display_name="Ship Region"
            ),
        ],
    )
    # Both directions, matching how a real bidirectional ORM relationship
    # pair (e.g. `Order.customer` / `Customer.orders`) is actually
    # extracted — `RelationshipGraph` has no reverse-edge inference of
    # its own, so a one-directional fixture here would make BFS fail to
    # find a path when the resolved anchor table happens to be the
    # target rather than the source.
    many_to_one = RelationshipMetadata(
        name="customer",
        source_table="orders",
        target_table="customers",
        source_columns=("customer_id",),
        target_columns=("customer_id",),
        direction=RelationshipDirection.MANY_TO_ONE,
    )
    one_to_many = RelationshipMetadata(
        name="orders",
        source_table="customers",
        target_table="orders",
        source_columns=("customer_id",),
        target_columns=("customer_id",),
        direction=RelationshipDirection.ONE_TO_MANY,
    )
    return build_registry([customers, orders], [many_to_one, one_to_many])
