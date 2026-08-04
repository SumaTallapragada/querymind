"""Immutable data models for the Business Knowledge Engine.

`BusinessConcept` is the single catalog-entry model — one per business
term the engine understands (`"Revenue"`, `"Top Customer"`, ...),
sourced from `data/concepts.yaml` and never hardcoded in Python.
`BusinessKnowledgeCatalog` is the complete loaded set.

Every model is frozen (`model_config = ConfigDict(frozen=True)`) and
uses `tuple`, never `list`, for collections — matching
`querymind.metadata.models`, `querymind.nlu.models`, and
`querymind.schema_linker.models`: a Pydantic `frozen=True` model still
allows in-place mutation of a `list` field, a `tuple` field does not.

Nothing here references a SQLAlchemy model or a `querymind.metadata`
type. `BusinessConcept.preferred_schema_objects` is a tuple of plain
strings (`"table"` or `"table.column"`) — a *logical* pointer a later
integration phase can resolve through the Schema Linker, not a live
reference to anything. That is what keeps this package usable on its
own, independent of both the Metadata Engine and the Schema Linker.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class BusinessConceptType(str, Enum):
    """The kind of business concept a `BusinessConcept` represents.

    Not every concept in the catalog is a precisely computed number:
    `METRIC` concepts (Revenue, Average Order Value, ...) are; `SEGMENT`
    concepts (Top Customer, Repeat Customer) classify a group; `STATUS`
    concepts (Active Customer, Inactive Customer) classify a state; `KPI`
    concepts (Supplier Performance) are composite, judgment-driven
    indicators; `ATTRIBUTE` concepts (Warehouse Capacity) describe a
    property without a single agreed formula.
    """

    METRIC = "metric"
    SEGMENT = "segment"
    STATUS = "status"
    KPI = "kpi"
    ATTRIBUTE = "attribute"


class BusinessMatchType(str, Enum):
    """How a search term matched a `BusinessConcept`, in resolver priority order.

    See `querymind.business_knowledge.resolver.ConceptResolver` for the
    matching logic — `EXACT` checked first, `PARTIAL` last.
    """

    EXACT = "exact"
    ALIAS = "alias"
    SYNONYM = "synonym"
    PARTIAL = "partial"


class BusinessAlias(_FrozenModel):
    """One alternate name a user might use instead of a concept's canonical `name`."""

    text: str = Field(
        description="The alternate name itself, e.g. 'AOV' for 'Average Order Value'."
    )


class BusinessFormula(_FrozenModel):
    """A structured, human-readable computation for a metric-like `BusinessConcept`.

    `expression` is prose/pseudocode, not SQL or a parseable formula
    language — turning it into an executable expression against real
    schema objects is SQL generation, explicitly out of scope for this
    package.
    """

    expression: str = Field(
        description="Human-readable formula, e.g. 'SUM(orders.total_amount) / COUNT(orders.order_id)'."
    )
    variables: tuple[str, ...] = Field(
        default=(),
        description="Named terms `expression` references, e.g. ('total_amount', 'order_id').",
    )


class BusinessDefinition(_FrozenModel):
    """A minimal, display-ready summary of what a concept means.

    A deliberately smaller projection of `BusinessConcept` — everything
    needed to *explain* a concept to a person, without the
    matching-oriented fields (`aliases`, `related_terms`,
    `preferred_schema_objects`) a resolver needs but a definition card
    doesn't. Built via `BusinessConcept.to_definition()`.
    """

    concept_id: str
    name: str
    description: str
    calculation_description: str
    example_questions: tuple[str, ...] = ()


class BusinessConcept(_FrozenModel):
    """One entry in the business knowledge catalog.

    The complete, flat representation of a single business term — every
    field a caller needs is a direct attribute, never nested behind a
    sub-object, so `concept.description`/`concept.aliases`/... always
    work without knowing this class's internal composition.
    """

    id: str = Field(
        description="Stable, unique identifier, e.g. 'revenue'. Never changes once assigned."
    )
    name: str = Field(description="Canonical display name, e.g. 'Revenue'.")
    concept_type: BusinessConceptType
    description: str = Field(description="What this concept means, in plain business language.")
    aliases: tuple[BusinessAlias, ...] = Field(
        default=(), description="Alternate names that mean exactly this concept."
    )
    related_terms: tuple[str, ...] = Field(
        default=(),
        description="Looser, associated terminology — related enough to resolve to this concept, "
        "but not a strict alternate name for it.",
    )
    example_questions: tuple[str, ...] = Field(
        default=(), description="Sample natural-language questions this concept answers."
    )
    calculation_description: str = Field(
        description="Plain-language explanation of how this concept is determined."
    )
    formula: BusinessFormula | None = Field(
        default=None,
        description="A structured formula, populated when one exists (mainly for METRIC concepts).",
    )
    preferred_schema_objects: tuple[str, ...] = Field(
        default=(),
        description="Logical 'table' or 'table.column' references this concept most naturally maps "
        "to — plain strings, never a live schema/ORM reference. Resolving these against the "
        "real schema is a later integration phase's job, not this package's.",
    )

    @field_validator("aliases", mode="before")
    @classmethod
    def _coerce_alias_strings(cls, value: object) -> object:
        """Accept plain strings for `aliases` (what `concepts.yaml` actually contains).

        `BusinessAlias` is a real, structured model, but authoring
        `- {text: "AOV"}` for every alias in the YAML source of truth
        would be needless ceremony — this lets the file stay a plain
        list of strings while `BusinessConcept.aliases` still comes out
        as `tuple[BusinessAlias, ...]`.
        """
        if not isinstance(value, list | tuple):
            return value
        return [{"text": item} if isinstance(item, str) else item for item in value]

    def to_definition(self) -> BusinessDefinition:
        """Return the display-ready `BusinessDefinition` projection of this concept."""
        return BusinessDefinition(
            concept_id=self.id,
            name=self.name,
            description=self.description,
            calculation_description=self.calculation_description,
            example_questions=self.example_questions,
        )


class BusinessMetric(BusinessConcept):
    """A `BusinessConcept` that is specifically a precisely computed numeric metric.

    Same fields as `BusinessConcept` — this exists so a caller that only
    wants metrics (e.g. `BusinessKnowledgeRegistry.list_metrics()`) can
    express that in the type system, not just by filtering on
    `concept_type` themselves. Construct via `BusinessMetric.from_concept`
    rather than directly; the catalog itself only ever holds
    `BusinessConcept` instances (see `catalog.py`).
    """

    concept_type: Literal[BusinessConceptType.METRIC] = BusinessConceptType.METRIC

    @classmethod
    def from_concept(cls, concept: BusinessConcept) -> BusinessMetric:
        """Reinterpret an already-`METRIC`-typed `BusinessConcept` as a `BusinessMetric`.

        Raises `ValueError` if `concept.concept_type` isn't `METRIC` —
        this is a type-narrowing view, not a way to redefine a
        non-metric concept as one.
        """
        if concept.concept_type is not BusinessConceptType.METRIC:
            raise ValueError(
                f"Cannot view concept {concept.id!r} (type {concept.concept_type.value!r}) as a "
                "BusinessMetric — only METRIC concepts qualify."
            )
        return cls(**concept.model_dump())


class BusinessKnowledgeCatalog(_FrozenModel):
    """The complete loaded catalog — every `BusinessConcept`, as loaded from `concepts.yaml`."""

    concepts: tuple[BusinessConcept, ...]
    loaded_at: datetime = Field(
        description="When this snapshot was loaded — informational only, not used by any lookup logic."
    )
