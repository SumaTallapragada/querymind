"""Immutable data models for the Query Intelligence Library.

`QueryExample` is the single catalog-entry model — one curated,
gold-standard natural-language-question-to-SQL pair, sourced from
`data/examples.yaml` and never hardcoded in Python. `QueryExampleLibrary`
is the complete loaded set.

Every model is frozen (`model_config = ConfigDict(frozen=True)`) and uses
`tuple`, never `list`, for collections — matching every other Phase's
models package (`querymind.metadata.models`, `querymind.nlu.models`,
`querymind.schema_linker.models`, `querymind.business_knowledge.models`):
a Pydantic `frozen=True` model still allows in-place mutation of a `list`
field, a `tuple` field does not.

This package has no runtime dependency on the NLU Engine, the Schema
Linker, or the Metadata Engine — it is "the curated knowledge base that
will power future retrieval," not a pipeline that calls them.
`QueryExample.query_context` is a small, hand-authored
`QueryContextSummary` (not a live `querymind.nlu.models.QueryContext`),
and `linked_schema_objects` is a tuple of plain `"table"`/`"table.column"`
strings (not a live `querymind.schema_linker` result) — the same
"logical reference only" pattern `querymind.business_knowledge.models
.BusinessConcept.preferred_schema_objects` already established. A future
Retrieval Engine is what will compare these curated summaries against a
*real*, freshly computed `QueryContext`/`LinkedQueryContext` — that
comparison is explicitly out of scope for this phase.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Difficulty(str, Enum):
    """How complex an example's `gold_sql` is to write or reason about."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class SQLDialect(str, Enum):
    """The SQL dialect `gold_sql` is written in.

    QueryMind's own database is PostgreSQL (`querymind.db`), but the
    library's model deliberately supports more than one dialect value —
    a curated example catalog is a reasonable thing to reuse against a
    different target dialect later, and "Valid SQL dialect" is an
    explicit validation rule precisely because this is a closed, not
    open-ended, set.
    """

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    ANSI = "ansi"


class ResultShape(str, Enum):
    """The shape of the result set `gold_sql` produces."""

    SCALAR = "scalar"
    SINGLE_ROW = "single_row"
    ROW_LIST = "row_list"
    TIME_SERIES = "time_series"
    RANKED_LIST = "ranked_list"


class QueryContextSummary(_FrozenModel):
    """A curated, hand-authored summary of how this question's NLU-parsed shape should look.

    Deliberately *not* `querymind.nlu.models.QueryContext` — see the
    module docstring for why this package has no dependency on the NLU
    Engine to load its static catalog.
    """

    intent: str = Field(
        description="The expected NLU intent, e.g. 'top_n', 'aggregation', 'trend'."
    )
    primary_entity: str | None = Field(
        default=None, description="The expected primary business entity, e.g. 'customer'."
    )
    metrics: tuple[str, ...] = Field(
        default=(), description="Expected business metric concepts, e.g. ('revenue',)."
    )
    dimensions: tuple[str, ...] = Field(
        default=(), description="Expected dimension concepts, e.g. ('region', 'category')."
    )
    aggregation: str | None = Field(
        default=None,
        description="The expected overall aggregation, e.g. 'sum', 'count', 'average'.",
    )


class QueryExample(_FrozenModel):
    """One curated, gold-standard natural-language-question-to-SQL example.

    The complete, flat representation of a single example — every field
    a caller needs is a direct attribute, never nested behind a
    sub-object beyond `query_context`, which is intentionally its own
    small model (see `QueryContextSummary`).
    """

    id: str = Field(
        description="Stable, unique identifier, e.g. 'top_customers_by_revenue'. Never changes once assigned."
    )
    title: str = Field(description="Short, human-readable label for this example.")
    natural_language_question: str = Field(
        description="The question exactly as a user might ask it."
    )
    normalized_question: str = Field(
        description="Lowercased, whitespace-collapsed form of the question, for keyword search."
    )
    query_context: QueryContextSummary
    business_concepts: tuple[str, ...] = Field(
        default=(), description="Business Knowledge Engine concept ids this question touches."
    )
    linked_schema_objects: tuple[str, ...] = Field(
        default=(),
        description="Logical 'table' or 'table.column' references `gold_sql` touches — plain "
        "strings, never a live schema/ORM reference.",
    )
    gold_sql: str = Field(description="The correct, hand-verified SQL answering the question.")
    sql_explanation: str = Field(
        description="Plain-language walkthrough of what `gold_sql` does and why."
    )
    difficulty: Difficulty
    tags: tuple[str, ...] = Field(
        default=(), description="Free-form topic labels, e.g. 'top-n', 'joins'."
    )
    dialect: SQLDialect = SQLDialect.POSTGRESQL
    expected_result_description: str = Field(
        description="Plain-language description of what the result means."
    )
    expected_result_shape: ResultShape
    common_variations: tuple[str, ...] = Field(
        default=(), description="Alternate phrasings of the same underlying question."
    )
    notes: str | None = Field(
        default=None,
        description="Free-form authoring notes — edge cases, caveats, why this SQL was chosen.",
    )


class QueryExampleLibrary(_FrozenModel):
    """The complete loaded library — every `QueryExample`, as loaded from `examples.yaml`."""

    examples: tuple[QueryExample, ...]
    loaded_at: datetime = Field(
        description="When this snapshot was loaded — informational only, not used by any lookup logic."
    )
