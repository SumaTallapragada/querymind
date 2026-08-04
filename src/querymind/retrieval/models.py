"""Immutable data models for the Knowledge Retrieval Engine.

`RetrievedKnowledgeBundle` is the single output type of
`querymind.retrieval.engine.RetrievalEngine.retrieve` — the top-K
`querymind.query_library.QueryExample`s most relevant to one
`querymind.schema_linker.LinkedQueryContext`, each with a full,
explainable score breakdown, plus statistics about the retrieval run
itself.

Every model is frozen (`model_config = ConfigDict(frozen=True)`) and uses
`tuple`, never `list`, for collections — matching every other Phase's
models package: a Pydantic `frozen=True` model still allows in-place
mutation of a `list` field, a `tuple` field does not.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from querymind.query_library.models import QueryExample
from querymind.schema_linker.models import LinkedQueryContext


class _FrozenModel(BaseModel):
    """Shared base: frozen, and rejects unknown fields (fail fast on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class SignalName(str, Enum):
    """The eight deterministic retrieval signals — see `querymind.retrieval.signals`."""

    INTENT_SIMILARITY = "intent_similarity"
    BUSINESS_CONCEPT_OVERLAP = "business_concept_overlap"
    SCHEMA_OVERLAP = "schema_overlap"
    TABLE_OVERLAP = "table_overlap"
    COLUMN_OVERLAP = "column_overlap"
    SQL_FEATURE_OVERLAP = "sql_feature_overlap"
    KEYWORD_OVERLAP = "keyword_overlap"
    DIFFICULTY_SIMILARITY = "difficulty_similarity"


class SignalBreakdown(_FrozenModel):
    """One signal's contribution to a candidate's overall retrieval score."""

    signal: SignalName
    score: float = Field(ge=0.0, le=1.0, description="This signal's own normalized score.")
    weight: float = Field(
        ge=0.0, le=1.0, description="How much this signal counts toward the overall score."
    )
    weighted_score: float = Field(ge=0.0, le=1.0, description="score * weight.")
    detail: str = Field(description="Human-readable explanation of what this signal found.")


class RetrievalScore(_FrozenModel):
    """The complete scoring result for one candidate example.

    Produced by `querymind.retrieval.scorer.RetrievalScorer.score` —
    purely the score and why it landed where it did, before match
    explanations (`matched_business_concepts`, ...) are attached by
    `querymind.retrieval.explanations.ExplanationBuilder` to build the
    final `RetrievedExample`.
    """

    overall_score: float = Field(ge=0.0, le=1.0)
    signal_scores: tuple[SignalBreakdown, ...]
    ranking_reason: str = Field(
        description="One-line human-readable summary of why this score was reached."
    )


class RetrievedExample(_FrozenModel):
    """One ranked candidate in a `RetrievedKnowledgeBundle`.

    Flattens `RetrievalScore`'s fields directly onto this model (rather
    than nesting a `score` sub-object) and adds the match explanation
    fields — every field a caller needs is a direct attribute.
    """

    example: QueryExample
    overall_score: float = Field(ge=0.0, le=1.0)
    signal_breakdown: tuple[SignalBreakdown, ...]
    matched_business_concepts: tuple[str, ...] = Field(
        default=(), description="Business concepts present in both the query and this example."
    )
    matched_schema_objects: tuple[str, ...] = Field(
        default=(), description="'table'/'table.column' references present in both."
    )
    matched_keywords: tuple[str, ...] = Field(
        default=(), description="Question keywords present in both."
    )
    selection_explanation: str = Field(
        description="Human-readable explanation of why this example was retrieved."
    )


class SignalContribution(_FrozenModel):
    """How much one signal contributed, on average, across a retrieval's returned results."""

    signal: SignalName
    average_weighted_score: float = Field(ge=0.0, le=1.0)


class RetrievalStatistics(_FrozenModel):
    """Observability data about one `RetrievalEngine.retrieve` call."""

    retrieval_latency_ms: float = Field(
        ge=0.0, description="Wall-clock time the retrieval took, in milliseconds."
    )
    top_k: int = Field(gt=0, description="The top_k requested for this retrieval.")
    candidate_count: int = Field(
        ge=0, description="How many library examples were scored before ranking."
    )
    average_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Average overall_score across the returned results (0.0 if none).",
    )
    signal_contribution: tuple[SignalContribution, ...] = Field(
        default=(),
        description="Average weighted contribution of each signal across the returned results.",
    )


class RetrievedKnowledgeBundle(_FrozenModel):
    """The complete output of one retrieval: the top-K ranked examples plus run statistics."""

    linked_query_context: LinkedQueryContext = Field(
        description="The input this retrieval was run for — kept for traceability."
    )
    retrieved_examples: tuple[RetrievedExample, ...] = Field(
        default=(), description="Ranked best-first; length is at most the requested top_k."
    )
    statistics: RetrievalStatistics
