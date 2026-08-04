"""Immutable data models produced by the NLU engine.

`QueryContext` is the single output type of `querymind.nlu.parser.QueryParser`
— everything downstream of this package (schema linking, SQL generation, a
future phase) consumes it and it alone. Every model here is a frozen
Pydantic v2 model: once a `QueryContext` is built for a question, nothing
about it can be mutated in place, matching the fact that it represents one
immutable interpretation of that question at the time it was parsed.
Collections use `tuple` rather than `list` for the same reason — a Pydantic
`frozen=True` model still allows in-place mutation of a `list` field, but
not of a `tuple` field.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Intent(str, Enum):
    """What kind of question is being asked, at the coarsest useful grain.

    `COUNT`/`SUM`/`AVERAGE`/`MIN`/`MAX` are single-aggregate questions
    ("how many orders...", "total revenue..."); `AGGREGATION` is a
    grouped/broken-down aggregate ("revenue by region") that doesn't
    reduce to one of those five specific reducers; `TOP_N` asks for a
    ranked subset; `TREND` asks how something changes over time;
    `COMPARISON` asks to contrast two or more things; `DETAIL` asks for
    specific records/attributes rather than a computed value; `SELECT` is
    the fallback for a plain lookup that doesn't fit any of the above.
    """

    SELECT = "select"
    TOP_N = "top_n"
    AGGREGATION = "aggregation"
    COMPARISON = "comparison"
    TREND = "trend"
    DETAIL = "detail"
    COUNT = "count"
    AVERAGE = "average"
    SUM = "sum"
    MIN = "min"
    MAX = "max"


class AggregationType(str, Enum):
    """The reducer implied by an intent, or explicitly requested alongside a metric."""

    COUNT = "count"
    SUM = "sum"
    AVERAGE = "average"
    MIN = "min"
    MAX = "max"


class ComparisonOperator(str, Enum):
    """How a `FilterExpression`'s value relates to the field it filters."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    IN = "in"
    CONTAINS = "contains"


class SortDirection(str, Enum):
    """The direction a `SortExpression` orders results in."""

    ASCENDING = "asc"
    DESCENDING = "desc"


class TimePeriod(str, Enum):
    """The kind of time window a `TimeExpression` represents."""

    TODAY = "today"
    YESTERDAY = "yesterday"
    THIS_WEEK = "this_week"
    LAST_WEEK = "last_week"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    THIS_QUARTER = "this_quarter"
    LAST_QUARTER = "last_quarter"
    THIS_YEAR = "this_year"
    LAST_YEAR = "last_year"
    BETWEEN = "between"
    BEFORE = "before"
    AFTER = "after"


class FilterExpression(BaseModel):
    """One `field <operator> value` constraint extracted from the question."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str = Field(
        description="Canonical business concept the filter applies to, e.g. 'price' or 'region'."
    )
    operator: ComparisonOperator
    value: str = Field(description="The literal value as matched, e.g. '50' or 'california'.")
    raw_text: str = Field(
        description="The substring of the normalized question this was parsed from."
    )


class MetricExpression(BaseModel):
    """One measurable business quantity the question is asking about."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(description="Canonical business metric name, e.g. 'revenue'.")
    aggregation: AggregationType | None = Field(
        default=None,
        description="The reducer explicitly requested alongside this specific metric mention, if any.",
    )
    raw_text: str


class TimeExpression(BaseModel):
    """The time window the question refers to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    period: TimePeriod
    start_date: date | None = None
    end_date: date | None = None
    raw_text: str


class SortExpression(BaseModel):
    """How results should be ordered."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    direction: SortDirection
    raw_text: str


class LimitExpression(BaseModel):
    """A cap on the number of results returned."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: int = Field(gt=0)
    raw_text: str


class QueryContext(BaseModel):
    """The complete, structured interpretation of one natural language question.

    Produced exclusively by `querymind.nlu.parser.QueryParser.parse` — every
    field here is derived deterministically from `original_question` by one
    pipeline stage, documented on that stage's module. Nothing in this
    model is resolved against the real database schema or metadata
    registry: `primary_entity`, `secondary_entities`, `dimensions`,
    `metrics`, and filter `field`s are canonical *business* concept names
    (e.g. `"customer"`, `"revenue"`), not table or column names. Mapping
    those names onto real tables and columns is schema linking, a later
    phase this model deliberately stops short of.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    original_question: str = Field(description="The question exactly as given, unmodified.")
    normalized_question: str = Field(
        description="The lowercased, whitespace-collapsed form parsed against."
    )
    intent: Intent
    primary_entity: str | None = Field(
        default=None, description="The most prominent business entity mentioned, e.g. 'customer'."
    )
    secondary_entities: tuple[str, ...] = Field(default_factory=tuple)
    business_concepts: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Every canonical business concept recognized anywhere in the question "
        "(entities, dimensions, metrics, and filter fields), in first-mention order.",
    )
    metrics: tuple[MetricExpression, ...] = Field(default_factory=tuple)
    dimensions: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Categorical attributes the question breaks down or filters by, e.g. 'region'.",
    )
    filters: tuple[FilterExpression, ...] = Field(default_factory=tuple)
    time_expression: TimeExpression | None = None
    sort: SortExpression | None = None
    limit: LimitExpression | None = None
    aggregation: AggregationType | None = Field(
        default=None, description="The overall reducer implied by `intent`, if any."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="A deterministic heuristic score, not a calibrated probability — see "
        "`QueryParser._compute_confidence`.",
    )
