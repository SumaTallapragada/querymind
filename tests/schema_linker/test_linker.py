from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import registry as sa_registry

from querymind.metadata.cache import InMemoryMetadataCache
from querymind.metadata.extractor import MetadataExtractor
from querymind.metadata.models import DatabaseMetadata
from querymind.metadata.registry import MetadataRegistry
from querymind.nlu.models import (
    AggregationType,
    ComparisonOperator,
    FilterExpression,
    Intent,
    MetricExpression,
    QueryContext,
    SortDirection,
    SortExpression,
)
from querymind.schema_linker.exceptions import EmptyRegistryError
from querymind.schema_linker.linker import SchemaLinker


def _query_context(**overrides: object) -> QueryContext:
    defaults: dict[str, object] = {
        "original_question": "test",
        "normalized_question": "test",
        "intent": Intent.SELECT,
        "confidence": 1.0,
    }
    defaults.update(overrides)
    return QueryContext(**defaults)  # type: ignore[arg-type]


def test_resolves_a_primary_entity(sample_registry: MetadataRegistry) -> None:
    linker = SchemaLinker(sample_registry)
    context = _query_context(primary_entity="customer")
    linked = linker.link(context)
    assert linked.primary_entity is not None
    assert linked.primary_entity.table.name == "customers"
    assert linked.is_fully_resolved is True


def test_unresolvable_entity_produces_an_ambiguity_and_leaves_field_none(
    sample_registry: MetadataRegistry,
) -> None:
    linker = SchemaLinker(sample_registry)
    context = _query_context(primary_entity="nonexistent_concept_xyz")
    linked = linker.link(context)
    assert linked.primary_entity is None
    assert linked.is_fully_resolved is False
    assert len(linked.ambiguities) == 1
    assert linked.ambiguities[0].business_concept == "nonexistent_concept_xyz"


def test_resolves_relationship_path_between_primary_entity_and_a_filter_field(
    sample_registry: MetadataRegistry,
) -> None:
    linker = SchemaLinker(sample_registry)
    context = _query_context(
        primary_entity="customer",
        filters=(
            FilterExpression(
                field="revenue",
                operator=ComparisonOperator.GREATER_THAN,
                value="100",
                raw_text="revenue greater than 100",
            ),
        ),
    )
    linked = linker.link(context)
    assert linked.primary_entity is not None
    assert len(linked.filters) == 1
    assert linked.filters[0].column.table_name == "orders"
    # customers (primary entity) and orders (filter field's table) are
    # different tables, connected by exactly one relationship edge.
    assert len(linked.relationship_paths) == 1
    assert linked.relationship_paths[0].source_table == "customers"
    assert linked.relationship_paths[0].target_table == "orders"


def test_single_resolved_table_produces_no_relationship_paths(
    sample_registry: MetadataRegistry,
) -> None:
    linker = SchemaLinker(sample_registry)
    context = _query_context(primary_entity="customer")
    linked = linker.link(context)
    assert linked.relationship_paths == ()


def test_empty_query_context_resolves_to_nothing_without_error(
    sample_registry: MetadataRegistry,
) -> None:
    linker = SchemaLinker(sample_registry)
    linked = linker.link(_query_context())
    assert linked.primary_entity is None
    assert linked.metrics == ()
    assert linked.ambiguities == ()
    assert linked.is_fully_resolved is True


def test_resolved_table_names_reflects_every_distinct_table(
    sample_registry: MetadataRegistry,
) -> None:
    linker = SchemaLinker(sample_registry)
    context = _query_context(
        primary_entity="customer",
        filters=(
            FilterExpression(
                field="revenue",
                operator=ComparisonOperator.GREATER_THAN,
                value="100",
                raw_text="revenue greater than 100",
            ),
        ),
    )
    linked = linker.link(context)
    assert linked.resolved_table_names == ("customers", "orders")


def test_resolves_secondary_entities(sample_registry: MetadataRegistry) -> None:
    linker = SchemaLinker(sample_registry)
    context = _query_context(primary_entity="customer", secondary_entities=("customer",))
    linked = linker.link(context)
    assert len(linked.secondary_entities) == 1
    assert linked.secondary_entities[0].table.name == "customers"


def test_resolves_metrics(sample_registry: MetadataRegistry) -> None:
    linker = SchemaLinker(sample_registry)
    context = _query_context(
        metrics=(
            MetricExpression(name="revenue", aggregation=AggregationType.SUM, raw_text="revenue"),
        )
    )
    linked = linker.link(context)
    assert len(linked.metrics) == 1
    assert linked.metrics[0].column.name == "total_amount"
    assert linked.metrics[0].aggregation is AggregationType.SUM


def test_resolves_dimensions(sample_registry: MetadataRegistry) -> None:
    linker = SchemaLinker(sample_registry)
    context = _query_context(dimensions=("customer_name",))
    linked = linker.link(context)
    assert len(linked.dimensions) == 1
    assert linked.dimensions[0].column.table_name == "customers"


def test_resolves_sort(sample_registry: MetadataRegistry) -> None:
    linker = SchemaLinker(sample_registry)
    context = _query_context(
        sort=SortExpression(field="revenue", direction=SortDirection.DESCENDING, raw_text="highest")
    )
    linked = linker.link(context)
    assert linked.sort is not None
    assert linked.sort.column.name == "total_amount"
    assert linked.sort.direction is SortDirection.DESCENDING


def test_unresolvable_sort_leaves_the_field_none_and_records_an_ambiguity(
    sample_registry: MetadataRegistry,
) -> None:
    linker = SchemaLinker(sample_registry)
    context = _query_context(
        sort=SortExpression(
            field="nonexistent_concept_xyz", direction=SortDirection.ASCENDING, raw_text="x"
        )
    )
    linked = linker.link(context)
    assert linked.sort is None
    assert len(linked.ambiguities) == 1


def test_raises_on_empty_registry() -> None:
    cache: InMemoryMetadataCache[DatabaseMetadata] = InMemoryMetadataCache()
    cache.set(DatabaseMetadata(tables=(), generated_at=datetime.now(UTC)))
    empty_registry = MetadataRegistry(MetadataExtractor(sa_registry()), cache=cache)

    linker = SchemaLinker(empty_registry)
    with pytest.raises(EmptyRegistryError):
        linker.link(_query_context())
