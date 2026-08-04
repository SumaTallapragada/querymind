from __future__ import annotations

from querymind.metadata.registry import MetadataRegistry
from querymind.nlu.models import (
    AggregationType,
    ComparisonOperator,
    FilterExpression,
    MetricExpression,
    SortDirection,
    SortExpression,
)
from querymind.schema_linker.models import ConceptKind, MatchTier
from querymind.schema_linker.resolver import ConceptResolver


def test_resolve_entity_returns_a_resolved_table(sample_registry: MetadataRegistry) -> None:
    resolver = ConceptResolver(sample_registry)
    resolved, ambiguity = resolver.resolve_entity("customer")
    assert ambiguity is None
    assert resolved is not None
    assert resolved.table.name == "customers"
    assert resolved.matching_reason is MatchTier.EXACT
    assert resolved.candidate_rank == 1


def test_resolve_entity_unresolvable_produces_an_ambiguity(
    sample_registry: MetadataRegistry,
) -> None:
    resolver = ConceptResolver(sample_registry)
    resolved, ambiguity = resolver.resolve_entity("nonexistent_concept_xyz")
    assert resolved is None
    assert ambiguity is not None
    assert ambiguity.concept_kind is ConceptKind.ENTITY
    assert ambiguity.business_concept == "nonexistent_concept_xyz"
    assert ambiguity.candidates == ()


def test_resolve_entity_ambiguous_tie_produces_all_candidates(
    sample_registry: MetadataRegistry,
) -> None:
    resolver = ConceptResolver(sample_registry)
    resolved, ambiguity = resolver.resolve_dimension("location")
    assert resolved is None
    assert ambiguity is not None
    assert ambiguity.concept_kind is ConceptKind.DIMENSION
    assert len(ambiguity.candidates) == 2


def test_resolve_metric_preserves_aggregation_and_raw_text(
    sample_registry: MetadataRegistry,
) -> None:
    resolver = ConceptResolver(sample_registry)
    metric = MetricExpression(
        name="revenue", aggregation=AggregationType.SUM, raw_text="total revenue"
    )
    resolved, ambiguity = resolver.resolve_metric(metric)
    assert ambiguity is None
    assert resolved is not None
    assert resolved.column.table_name == "orders"
    assert resolved.column.name == "total_amount"
    assert resolved.aggregation is AggregationType.SUM
    assert resolved.raw_text == "total revenue"


def test_resolve_filter_preserves_operator_and_value(sample_registry: MetadataRegistry) -> None:
    resolver = ConceptResolver(sample_registry)
    filter_expression = FilterExpression(
        field="revenue",
        operator=ComparisonOperator.GREATER_THAN,
        value="100",
        raw_text="revenue greater than 100",
    )
    resolved, ambiguity = resolver.resolve_filter(filter_expression)
    assert ambiguity is None
    assert resolved is not None
    assert resolved.column.name == "total_amount"
    assert resolved.operator is ComparisonOperator.GREATER_THAN
    assert resolved.value == "100"


def test_resolve_sort_preserves_direction(sample_registry: MetadataRegistry) -> None:
    resolver = ConceptResolver(sample_registry)
    sort = SortExpression(field="revenue", direction=SortDirection.DESCENDING, raw_text="highest")
    resolved, ambiguity = resolver.resolve_sort(sort)
    assert ambiguity is None
    assert resolved is not None
    assert resolved.column.name == "total_amount"
    assert resolved.direction is SortDirection.DESCENDING


def test_resolve_dimension_alternatives_exclude_the_winner(
    sample_registry: MetadataRegistry,
) -> None:
    """`alternatives` lists every *other* candidate, not the chosen one again."""
    resolver = ConceptResolver(sample_registry)
    resolved, _ambiguity = resolver.resolve_entity("customer")
    assert resolved is not None
    assert all(alt.table_name != resolved.table.name for alt in resolved.alternatives)
