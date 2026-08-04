"""Resolves one business concept at a time into a `Resolved*` model or an `Ambiguity`.

`ConceptResolver` is the join point between candidate generation
(`querymind.schema_linker.candidates`), ambiguity detection
(`querymind.schema_linker.ambiguity`), and the Metadata Engine
(`MetadataRegistry.get_table`/`get_column`, used only to fetch the full
metadata object for whichever candidate wins). `SchemaLinker` calls one
`resolve_*` method per `QueryContext` field; each returns the resolved
model on success, or `None` plus an `Ambiguity` on anything less than a
confident single winner.
"""

from __future__ import annotations

from querymind.metadata.registry import MetadataRegistry
from querymind.nlu.models import FilterExpression, MetricExpression, SortExpression
from querymind.schema_linker.ambiguity import AmbiguityDetector
from querymind.schema_linker.candidates import CandidateGenerator
from querymind.schema_linker.models import (
    Ambiguity,
    ConceptKind,
    LinkCandidate,
    ResolvedFilter,
    ResolvedMetric,
    ResolvedSort,
    ResolvedTable,
)
from querymind.schema_linker.models import ResolvedColumn as ResolvedColumnModel


class ConceptResolver:
    """Resolves individual business concepts against a `MetadataRegistry`.

    Depends on `CandidateGenerator`/`AmbiguityDetector` through their
    constructor parameters (both optional, defaulting to the standard
    implementation) rather than importing a concrete class directly, so
    a caller can inject alternative matching/ambiguity policy without
    subclassing this class.
    """

    def __init__(
        self,
        registry: MetadataRegistry,
        candidate_generator: CandidateGenerator | None = None,
        ambiguity_detector: AmbiguityDetector | None = None,
    ) -> None:
        self._registry = registry
        self._candidates = candidate_generator or CandidateGenerator(registry)
        self._ambiguity = ambiguity_detector or AmbiguityDetector()

    def resolve_entity(self, concept: str) -> tuple[ResolvedTable | None, Ambiguity | None]:
        """Resolve a business entity (`QueryContext.primary_entity`/`secondary_entities`) to a table."""
        candidates = self._candidates.generate_table_candidates(concept)
        decision = self._ambiguity.decide(candidates)
        if not decision.is_confident:
            return None, self._ambiguity_for(
                concept, ConceptKind.ENTITY, candidates, decision.reason
            )

        winner = candidates[0]
        table = self._registry.get_table(winner.table_name)
        return (
            ResolvedTable(
                business_concept=concept,
                table=table,
                confidence=winner.confidence,
                matching_reason=winner.matching_reason,
                candidate_rank=winner.candidate_rank,
                alternatives=candidates[1:],
            ),
            None,
        )

    def resolve_dimension(
        self, concept: str
    ) -> tuple[ResolvedColumnModel | None, Ambiguity | None]:
        """Resolve a business dimension (`QueryContext.dimensions`) to a column."""
        winner, candidates, ambiguity = self._resolve_column(concept, ConceptKind.DIMENSION)
        if winner is None or ambiguity is not None:
            return None, ambiguity
        assert winner.column_name is not None, "column-level candidates always carry a column_name"
        column = self._registry.get_column(winner.table_name, winner.column_name)
        return (
            ResolvedColumnModel(
                business_concept=concept,
                column=column,
                confidence=winner.confidence,
                matching_reason=winner.matching_reason,
                candidate_rank=winner.candidate_rank,
                alternatives=candidates[1:],
            ),
            None,
        )

    def resolve_metric(
        self, metric: MetricExpression
    ) -> tuple[ResolvedMetric | None, Ambiguity | None]:
        """Resolve a business metric (`QueryContext.metrics`) to a column, preserving its aggregation."""
        winner, candidates, ambiguity = self._resolve_column(metric.name, ConceptKind.METRIC)
        if winner is None or ambiguity is not None:
            return None, ambiguity
        assert winner.column_name is not None, "column-level candidates always carry a column_name"
        column = self._registry.get_column(winner.table_name, winner.column_name)
        return (
            ResolvedMetric(
                business_concept=metric.name,
                column=column,
                aggregation=metric.aggregation,
                raw_text=metric.raw_text,
                confidence=winner.confidence,
                matching_reason=winner.matching_reason,
                candidate_rank=winner.candidate_rank,
                alternatives=candidates[1:],
            ),
            None,
        )

    def resolve_filter(
        self, filter_expression: FilterExpression
    ) -> tuple[ResolvedFilter | None, Ambiguity | None]:
        """Resolve a filter (`QueryContext.filters`) field to a column, preserving its operator/value."""
        winner, candidates, ambiguity = self._resolve_column(
            filter_expression.field, ConceptKind.FILTER_FIELD
        )
        if winner is None or ambiguity is not None:
            return None, ambiguity
        assert winner.column_name is not None, "column-level candidates always carry a column_name"
        column = self._registry.get_column(winner.table_name, winner.column_name)
        return (
            ResolvedFilter(
                business_concept=filter_expression.field,
                column=column,
                operator=filter_expression.operator,
                value=filter_expression.value,
                raw_text=filter_expression.raw_text,
                confidence=winner.confidence,
                matching_reason=winner.matching_reason,
                candidate_rank=winner.candidate_rank,
                alternatives=candidates[1:],
            ),
            None,
        )

    def resolve_sort(self, sort: SortExpression) -> tuple[ResolvedSort | None, Ambiguity | None]:
        """Resolve a sort (`QueryContext.sort`) field to a column, preserving its direction."""
        winner, candidates, ambiguity = self._resolve_column(sort.field, ConceptKind.SORT_FIELD)
        if winner is None or ambiguity is not None:
            return None, ambiguity
        assert winner.column_name is not None, "column-level candidates always carry a column_name"
        column = self._registry.get_column(winner.table_name, winner.column_name)
        return (
            ResolvedSort(
                business_concept=sort.field,
                column=column,
                direction=sort.direction,
                raw_text=sort.raw_text,
                confidence=winner.confidence,
                matching_reason=winner.matching_reason,
                candidate_rank=winner.candidate_rank,
                alternatives=candidates[1:],
            ),
            None,
        )

    def _resolve_column(
        self, concept: str, kind: ConceptKind
    ) -> tuple[LinkCandidate | None, tuple[LinkCandidate, ...], Ambiguity | None]:
        """Shared candidate generation + ambiguity decision for every column-level concept kind."""
        candidates = self._candidates.generate_column_candidates(concept)
        decision = self._ambiguity.decide(candidates)
        if not decision.is_confident:
            return None, candidates, self._ambiguity_for(concept, kind, candidates, decision.reason)
        return candidates[0], candidates, None

    @staticmethod
    def _ambiguity_for(
        concept: str, kind: ConceptKind, candidates: tuple[LinkCandidate, ...], reason: str | None
    ) -> Ambiguity:
        return Ambiguity(
            business_concept=concept,
            concept_kind=kind,
            candidates=candidates,
            reason=reason or "Could not be resolved to a single confident schema object.",
        )
