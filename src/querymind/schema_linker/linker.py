"""The Semantic Schema Linker: turns a `QueryContext` into a `LinkedQueryContext`.

`SchemaLinker` is the single public entry point for this package. It
resolves every business concept a `QueryContext` carries — entities,
metrics, dimensions, filters, sort field — against a `MetadataRegistry`,
using `ConceptResolver` for each individual concept and
`RelationshipPathResolver` once at the end to connect whatever tables
were resolved. Nothing here inspects `querymind.models` (SQLAlchemy)
directly, generates SQL, builds a prompt, or calls an LLM — see the
`querymind.schema_linker` package docstring for that boundary.
"""

from __future__ import annotations

from querymind.metadata.registry import MetadataRegistry
from querymind.nlu.models import QueryContext
from querymind.schema_linker.exceptions import EmptyRegistryError
from querymind.schema_linker.models import (
    Ambiguity,
    LinkedQueryContext,
    ResolvedColumn,
    ResolvedFilter,
    ResolvedMetric,
    ResolvedRelationship,
    ResolvedSort,
    ResolvedTable,
)
from querymind.schema_linker.relationships import RelationshipPathResolver
from querymind.schema_linker.resolver import ConceptResolver


class SchemaLinker:
    """Links a `QueryContext` against a `MetadataRegistry`, producing a `LinkedQueryContext`.

    Depends on `ConceptResolver` (constructor-injected, defaulting to
    the standard candidate-generation/ambiguity-detection pipeline) and
    `RelationshipPathResolver` (built fresh per `link()` call from the
    registry's current `RelationshipGraph`, since which tables need
    connecting is only known once resolution finishes) — never on a
    concrete matching implementation directly.
    """

    def __init__(
        self,
        registry: MetadataRegistry,
        resolver: ConceptResolver | None = None,
    ) -> None:
        self._registry = registry
        self._resolver = resolver or ConceptResolver(registry)

    def link(self, query_context: QueryContext) -> LinkedQueryContext:
        """Resolve every business concept in `query_context` and connect the tables involved.

        Raises `EmptyRegistryError` if the registry has no tables
        loaded — every other outcome, including a `QueryContext` with
        nothing resolvable in it at all, returns a `LinkedQueryContext`
        (with everything unresolved recorded in `ambiguities`) rather
        than raising.
        """
        if not self._registry.load().tables:
            raise EmptyRegistryError()

        ambiguities: list[Ambiguity] = []
        involved_tables: list[str] = []

        primary_entity = self._resolve_entity(
            query_context.primary_entity, ambiguities, involved_tables
        )

        secondary_entities: list[ResolvedTable] = []
        for concept in query_context.secondary_entities:
            resolved = self._resolve_entity(concept, ambiguities, involved_tables)
            if resolved is not None:
                secondary_entities.append(resolved)

        metrics: list[ResolvedMetric] = []
        for metric in query_context.metrics:
            resolved_metric, ambiguity = self._resolver.resolve_metric(metric)
            if ambiguity is not None:
                ambiguities.append(ambiguity)
            if resolved_metric is not None:
                metrics.append(resolved_metric)
                involved_tables.append(resolved_metric.column.table_name)

        dimensions: list[ResolvedColumn] = []
        for dimension in query_context.dimensions:
            resolved_dimension, ambiguity = self._resolver.resolve_dimension(dimension)
            if ambiguity is not None:
                ambiguities.append(ambiguity)
            if resolved_dimension is not None:
                dimensions.append(resolved_dimension)
                involved_tables.append(resolved_dimension.column.table_name)

        filters: list[ResolvedFilter] = []
        for filter_expression in query_context.filters:
            resolved_filter, ambiguity = self._resolver.resolve_filter(filter_expression)
            if ambiguity is not None:
                ambiguities.append(ambiguity)
            if resolved_filter is not None:
                filters.append(resolved_filter)
                involved_tables.append(resolved_filter.column.table_name)

        sort: ResolvedSort | None = None
        if query_context.sort is not None:
            sort, ambiguity = self._resolver.resolve_sort(query_context.sort)
            if ambiguity is not None:
                ambiguities.append(ambiguity)
            if sort is not None:
                involved_tables.append(sort.column.table_name)

        relationship_paths = self._resolve_relationship_paths(involved_tables)

        return LinkedQueryContext(
            query_context=query_context,
            primary_entity=primary_entity,
            secondary_entities=tuple(secondary_entities),
            metrics=tuple(metrics),
            dimensions=tuple(dimensions),
            filters=tuple(filters),
            sort=sort,
            relationship_paths=relationship_paths,
            ambiguities=tuple(ambiguities),
        )

    def _resolve_entity(
        self, concept: str | None, ambiguities: list[Ambiguity], involved_tables: list[str]
    ) -> ResolvedTable | None:
        if concept is None:
            return None
        resolved, ambiguity = self._resolver.resolve_entity(concept)
        if ambiguity is not None:
            ambiguities.append(ambiguity)
        if resolved is not None:
            involved_tables.append(resolved.table.name)
        return resolved

    def _resolve_relationship_paths(
        self, involved_tables: list[str]
    ) -> tuple[ResolvedRelationship, ...]:
        unique_tables = tuple(dict.fromkeys(involved_tables))
        if len(unique_tables) < 2:
            return ()
        graph = self._registry.build_graph()
        path_resolver = RelationshipPathResolver(graph)
        anchor, others = unique_tables[0], unique_tables[1:]
        return path_resolver.find_paths_from(anchor, others)
