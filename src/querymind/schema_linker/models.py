"""Immutable data models produced by the Semantic Schema Linker.

`LinkedQueryContext` is the single output type of
`querymind.schema_linker.linker.SchemaLinker` — it takes a
`querymind.nlu.QueryContext` (business concept names only) and a
`querymind.metadata.MetadataRegistry` (the real schema) and produces this:
the same query, with every business concept mapped onto the concrete
table/column it refers to, or explicitly flagged as ambiguous. Every
model here is a frozen Pydantic v2 model using `tuple` (never `list`) for
collections, for the same reason `querymind.metadata.models` and
`querymind.nlu.models` do: a Pydantic `frozen=True` model still allows
in-place mutation of a `list` field, a `tuple` field does not.

**Resolved-or-absent, never guessed.** A business concept appears in the
corresponding `LinkedQueryContext` field (`primary_entity`, `metrics`,
...) if and only if it was resolved with a single, confident winning
candidate. Anything else — no candidate matched at all, or the top
candidates were too close to call — produces an `Ambiguity` entry instead
and the concept is simply *absent* from its normal field. A caller must
check `LinkedQueryContext.ambiguities` (or `is_fully_resolved`) rather
than assume every concept the NLU engine found made it through.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from querymind.metadata.models import ColumnMetadata, TableMetadata
from querymind.nlu.models import AggregationType, ComparisonOperator, QueryContext, SortDirection


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class MatchTier(str, Enum):
    """The six deterministic matching tiers, in priority order (best first).

    `EXACT`/`BUSINESS_DICTIONARY`/`SYNONYM`/`ALIAS` are all exact-equality
    checks against a different piece of schema metadata (the identifier
    itself, curated business-dictionary terms, declared synonyms, and a
    small deterministic abbreviation-expansion rule, respectively) — none
    of them involve approximation, so each has one fixed confidence.
    `FUZZY` (character-similarity) and `PARTIAL` (substring containment)
    are approximate and score proportionally to how close the match was,
    always below every exact tier's confidence. See
    `querymind.schema_linker.matcher` for the matching logic and
    `querymind.schema_linker.scorer` for the confidence mapping.
    """

    EXACT = "exact"
    BUSINESS_DICTIONARY = "business_dictionary"
    SYNONYM = "synonym"
    ALIAS = "alias"
    FUZZY = "fuzzy"
    PARTIAL = "partial"


class ConceptKind(str, Enum):
    """Which `QueryContext` field a resolution attempt originated from."""

    ENTITY = "entity"
    METRIC = "metric"
    DIMENSION = "dimension"
    FILTER_FIELD = "filter_field"
    SORT_FIELD = "sort_field"


class LinkCandidate(_FrozenModel):
    """One possible schema match for a business concept, ranked among its alternatives."""

    table_name: str
    column_name: str | None = Field(
        default=None, description="None for a table-level (entity) candidate."
    )
    confidence: float = Field(ge=0.0, le=1.0)
    matching_reason: MatchTier
    candidate_rank: int = Field(ge=1, description="1 = the best candidate found for this concept.")
    matched_text: str = Field(
        description="The specific metadata text that produced the match, e.g. a synonym or the "
        "column name itself — see `matching_reason` for which field it came from."
    )


class ResolvedTable(_FrozenModel):
    """A business entity resolved to a concrete table."""

    business_concept: str = Field(
        description="The canonical entity name as given by the NLU engine."
    )
    table: TableMetadata
    confidence: float = Field(ge=0.0, le=1.0)
    matching_reason: MatchTier
    candidate_rank: int = Field(ge=1)
    alternatives: tuple[LinkCandidate, ...] = Field(
        default=(), description="Every other candidate considered for this concept, ranked."
    )


class ResolvedColumn(_FrozenModel):
    """A business dimension (or other bare column reference) resolved to a concrete column."""

    business_concept: str
    column: ColumnMetadata
    confidence: float = Field(ge=0.0, le=1.0)
    matching_reason: MatchTier
    candidate_rank: int = Field(ge=1)
    alternatives: tuple[LinkCandidate, ...] = ()


class ResolvedMetric(_FrozenModel):
    """A business metric resolved to a concrete column, with its requested aggregation preserved."""

    business_concept: str
    column: ColumnMetadata
    aggregation: AggregationType | None = Field(
        description="Carried over from the source `MetricExpression` — this stage never invents one."
    )
    raw_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    matching_reason: MatchTier
    candidate_rank: int = Field(ge=1)
    alternatives: tuple[LinkCandidate, ...] = ()


class ResolvedFilter(_FrozenModel):
    """A `field <operator> value` filter with its field resolved to a concrete column."""

    business_concept: str
    column: ColumnMetadata
    operator: ComparisonOperator
    value: str
    raw_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    matching_reason: MatchTier
    candidate_rank: int = Field(ge=1)
    alternatives: tuple[LinkCandidate, ...] = ()


class ResolvedSort(_FrozenModel):
    """A requested sort with its field resolved to a concrete column."""

    business_concept: str
    column: ColumnMetadata
    direction: SortDirection
    raw_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    matching_reason: MatchTier
    candidate_rank: int = Field(ge=1)
    alternatives: tuple[LinkCandidate, ...] = ()


class ResolvedRelationship(_FrozenModel):
    """One join edge between two resolved tables.

    A structural fact read directly off `RelationshipGraph` — not a term
    match — so unlike the other `Resolved*` models it carries no
    `confidence`/`matching_reason`/`candidate_rank`: there is nothing
    approximate about which foreign key connects two tables.
    """

    source_table: str
    target_table: str
    relationship_name: str
    source_columns: tuple[str, ...]
    target_columns: tuple[str, ...]


class Ambiguity(_FrozenModel):
    """A business concept that could not be resolved to a single confident schema object.

    Covers both ends of "not confident": `candidates` is empty when
    nothing matched at any tier, and has two or more entries when
    several plausible candidates were too close in confidence to pick
    between automatically. Either way, `SchemaLinker` never silently
    picked one — the caller decides what happens next (ask the user,
    default to the top-ranked candidate explicitly, etc.).
    """

    business_concept: str
    concept_kind: ConceptKind
    candidates: tuple[LinkCandidate, ...] = Field(
        default=(), description="Every candidate considered, ranked — empty if none matched at all."
    )
    reason: str = Field(
        description="Human-readable explanation of why this could not be auto-resolved."
    )


class LinkedQueryContext(_FrozenModel):
    """The complete result of linking one `QueryContext` against a `MetadataRegistry`.

    Holds the original `query_context` alongside the resolved form of
    every field it's possible to resolve. Fields mirror `QueryContext`'s
    shape (`primary_entity`, `metrics`, `dimensions`, `filters`, `sort`)
    but each entry is now a concrete schema object with a confidence
    score, plus `relationship_paths`: the join edges connecting every
    resolved table, computed once over the full set of tables this query
    touches. See the module docstring for what it means for a concept to
    be missing from its field instead of present.
    """

    query_context: QueryContext
    primary_entity: ResolvedTable | None = None
    secondary_entities: tuple[ResolvedTable, ...] = ()
    metrics: tuple[ResolvedMetric, ...] = ()
    dimensions: tuple[ResolvedColumn, ...] = ()
    filters: tuple[ResolvedFilter, ...] = ()
    sort: ResolvedSort | None = None
    relationship_paths: tuple[ResolvedRelationship, ...] = Field(
        default=(),
        description="Join edges connecting every resolved table, in discovery order. Empty when "
        "fewer than two distinct tables were resolved.",
    )
    ambiguities: tuple[Ambiguity, ...] = ()

    @property
    def is_fully_resolved(self) -> bool:
        """Whether every concept the NLU engine found was resolved with no ambiguity."""
        return len(self.ambiguities) == 0

    @property
    def resolved_table_names(self) -> tuple[str, ...]:
        """Every distinct table this query touches, in first-resolved order."""
        names: list[str] = []
        if self.primary_entity is not None:
            names.append(self.primary_entity.table.name)
        names.extend(entity.table.name for entity in self.secondary_entities)
        names.extend(metric.column.table_name for metric in self.metrics)
        names.extend(dimension.column.table_name for dimension in self.dimensions)
        names.extend(filter_.column.table_name for filter_ in self.filters)
        if self.sort is not None:
            names.append(self.sort.column.table_name)
        seen: set[str] = set()
        ordered: list[str] = []
        for name in names:
            if name not in seen:
                seen.add(name)
                ordered.append(name)
        return tuple(ordered)
