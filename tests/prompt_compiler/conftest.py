"""Shared fixtures and object-graph builders for prompt compiler tests.

Builds a `RetrievedKnowledgeBundle` directly from its models (never
through the real NLU/Schema Linker/Retrieval pipeline) so every test
controls its scenario precisely. `tests/prompt_compiler/test_integration.py`
separately exercises the real, fully wired pipeline.
"""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from querymind.metadata.models import ColumnMetadata, PrimaryKeyMetadata, TableMetadata
from querymind.nlu.models import AggregationType, Intent, QueryContext
from querymind.query_library.models import (
    Difficulty,
    QueryContextSummary,
    QueryExample,
    ResultShape,
)
from querymind.retrieval.models import (
    RetrievalStatistics,
    RetrievedExample,
    RetrievedKnowledgeBundle,
    SignalBreakdown,
    SignalName,
)
from querymind.schema_linker.models import (
    LinkedQueryContext,
    MatchTier,
    ResolvedMetric,
    ResolvedRelationship,
    ResolvedTable,
)


def make_column(
    table_name: str, name: str, *, primary_key: bool = False, description: str | None = None
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
        description=description,
    )


def make_table(
    name: str, columns: Iterable[ColumnMetadata], *, description: str | None = None
) -> TableMetadata:
    columns = tuple(columns)
    pk_columns = tuple(c.name for c in columns if c.primary_key) or (f"{name}_id",)
    return TableMetadata(
        name=name,
        columns=columns,
        primary_key=PrimaryKeyMetadata(name=f"pk_{name}", columns=pk_columns),
        description=description,
    )


_CUSTOMERS_TABLE = make_table(
    "customers",
    [make_column("customers", "customer_id", primary_key=True)],
    description="One row per customer.",
)
_ORDERS_TABLE = make_table(
    "orders",
    [make_column("orders", "order_id", primary_key=True), make_column("orders", "total_amount")],
    description="One row per placed order.",
)
_TOTAL_AMOUNT_COLUMN = make_column(
    "orders", "total_amount", description="The order's total charged amount."
)


def make_query_context(**overrides: object) -> QueryContext:
    defaults: dict[str, object] = {
        "original_question": "Who are our top 10 customers by revenue?",
        "normalized_question": "who are our top 10 customers by revenue",
        "intent": Intent.TOP_N,
        "business_concepts": ("customer", "revenue"),
        "confidence": 0.9,
    }
    defaults.update(overrides)
    return QueryContext(**defaults)  # type: ignore[arg-type]


def make_linked_context(**overrides: object) -> LinkedQueryContext:
    """A "top 10 customers by revenue"-shaped `LinkedQueryContext`: customer entity + revenue metric."""
    defaults: dict[str, object] = {
        "query_context": make_query_context(),
        "primary_entity": ResolvedTable(
            business_concept="customer",
            table=_CUSTOMERS_TABLE,
            confidence=1.0,
            matching_reason=MatchTier.EXACT,
            candidate_rank=1,
        ),
        "secondary_entities": (
            ResolvedTable(
                business_concept="order",
                table=_ORDERS_TABLE,
                confidence=0.95,
                matching_reason=MatchTier.EXACT,
                candidate_rank=1,
            ),
        ),
        "metrics": (
            ResolvedMetric(
                business_concept="revenue",
                column=_TOTAL_AMOUNT_COLUMN,
                aggregation=AggregationType.SUM,
                raw_text="revenue",
                confidence=0.85,
                matching_reason=MatchTier.SYNONYM,
                candidate_rank=1,
            ),
        ),
        "relationship_paths": (
            ResolvedRelationship(
                source_table="orders",
                target_table="customers",
                relationship_name="customer",
                source_columns=("customer_id",),
                target_columns=("customer_id",),
            ),
        ),
    }
    defaults.update(overrides)
    return LinkedQueryContext(**defaults)  # type: ignore[arg-type]


def make_example(**overrides: object) -> QueryExample:
    defaults: dict[str, object] = {
        "id": "top_customers_by_revenue",
        "title": "Top 10 Customers by Revenue",
        "natural_language_question": "Who are our top 10 customers by total revenue?",
        "normalized_question": "who are our top 10 customers by total revenue",
        "query_context": QueryContextSummary(
            intent="top_n", primary_entity="customer", metrics=("revenue",), aggregation="sum"
        ),
        "business_concepts": ("revenue", "top_customer"),
        "linked_schema_objects": ("orders.total_amount", "customers.customer_id"),
        "gold_sql": (
            "SELECT c.customer_id, SUM(o.total_amount) AS total_revenue "
            "FROM customers c JOIN orders o ON o.customer_id = c.customer_id "
            "GROUP BY c.customer_id ORDER BY total_revenue DESC LIMIT 10;"
        ),
        "sql_explanation": "Joins customers to orders and sums revenue per customer.",
        "difficulty": Difficulty.INTERMEDIATE,
        "tags": ("customers", "top-n", "joins"),
        "expected_result_description": "Up to 10 customers ranked by revenue.",
        "expected_result_shape": ResultShape.RANKED_LIST,
    }
    defaults.update(overrides)
    return QueryExample(**defaults)  # type: ignore[arg-type]


def make_retrieved_example(**overrides: object) -> RetrievedExample:
    defaults: dict[str, object] = {
        "example": make_example(),
        "overall_score": 0.92,
        "signal_breakdown": (
            SignalBreakdown(
                signal=SignalName.BUSINESS_CONCEPT_OVERLAP,
                score=0.9,
                weight=0.3,
                weighted_score=0.27,
                detail="Shared concepts: revenue, top_customer.",
            ),
        ),
        "matched_business_concepts": ("revenue",),
        "matched_schema_objects": ("orders.total_amount",),
        "matched_keywords": ("customers", "revenue"),
        "selection_explanation": "Closely matches on business concepts and schema objects.",
    }
    defaults.update(overrides)
    return RetrievedExample(**defaults)  # type: ignore[arg-type]


def make_statistics(**overrides: object) -> RetrievalStatistics:
    defaults: dict[str, object] = {
        "retrieval_latency_ms": 1.5,
        "top_k": 5,
        "candidate_count": 25,
        "average_score": 0.92,
    }
    defaults.update(overrides)
    return RetrievalStatistics(**defaults)  # type: ignore[arg-type]


def make_bundle(**overrides: object) -> RetrievedKnowledgeBundle:
    defaults: dict[str, object] = {
        "linked_query_context": make_linked_context(),
        "retrieved_examples": (make_retrieved_example(),),
        "statistics": make_statistics(),
    }
    defaults.update(overrides)
    return RetrievedKnowledgeBundle(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def linked_context() -> LinkedQueryContext:
    return make_linked_context()


@pytest.fixture
def bundle() -> RetrievedKnowledgeBundle:
    return make_bundle()


@pytest.fixture
def empty_bundle() -> RetrievedKnowledgeBundle:
    """A bundle with no resolved schema objects, no relationships, and no retrieved examples."""
    return make_bundle(
        linked_query_context=make_linked_context(
            primary_entity=None,
            secondary_entities=(),
            metrics=(),
            relationship_paths=(),
            query_context=make_query_context(business_concepts=()),
        ),
        retrieved_examples=(),
    )
