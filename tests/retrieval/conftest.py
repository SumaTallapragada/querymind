"""Shared fixtures and object-graph builders for retrieval tests.

Builds `LinkedQueryContext` and `QueryExample` instances directly from
their models (never through the real `QueryParser`/`SchemaLinker`
pipeline) so every test controls its scenario precisely.
`tests/retrieval/test_integration.py` separately exercises the real,
fully wired pipeline.
"""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from querymind.metadata.models import ColumnMetadata, PrimaryKeyMetadata, TableMetadata
from querymind.nlu.models import AggregationType, Intent, QueryContext
from querymind.query_library.catalog import build_library
from querymind.query_library.models import (
    Difficulty,
    QueryContextSummary,
    QueryExample,
    QueryExampleLibrary,
    ResultShape,
)
from querymind.schema_linker.models import (
    LinkedQueryContext,
    MatchTier,
    ResolvedMetric,
    ResolvedTable,
)


def make_column(table_name: str, name: str, *, primary_key: bool = False) -> ColumnMetadata:
    return ColumnMetadata(
        table_name=table_name,
        name=name,
        sql_type="VARCHAR",
        python_type="str",
        nullable=not primary_key,
        primary_key=primary_key,
        unique=primary_key,
        autoincrement=primary_key,
    )


def make_table(name: str, columns: Iterable[ColumnMetadata]) -> TableMetadata:
    columns = tuple(columns)
    pk_columns = tuple(c.name for c in columns if c.primary_key) or (f"{name}_id",)
    return TableMetadata(
        name=name,
        columns=columns,
        primary_key=PrimaryKeyMetadata(name=f"pk_{name}", columns=pk_columns),
    )


_CUSTOMERS_TABLE = make_table(
    "customers", [make_column("customers", "customer_id", primary_key=True)]
)
_ORDERS_TABLE = make_table(
    "orders",
    [make_column("orders", "order_id", primary_key=True), make_column("orders", "total_amount")],
)
_TOTAL_AMOUNT_COLUMN = make_column("orders", "total_amount")


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


@pytest.fixture
def linked_context() -> LinkedQueryContext:
    return make_linked_context()


@pytest.fixture
def matching_example() -> QueryExample:
    """An example that should score highly against `linked_context`."""
    return make_example()


@pytest.fixture
def unrelated_example() -> QueryExample:
    """An example sharing essentially nothing with `linked_context`."""
    return make_example(
        id="shipments_by_carrier",
        title="Shipment Count by Carrier",
        natural_language_question="Show shipment counts by carrier.",
        normalized_question="show shipment counts by carrier",
        query_context=QueryContextSummary(
            intent="aggregation", primary_entity="shipment", aggregation="count"
        ),
        business_concepts=(),
        linked_schema_objects=("shipments.carrier",),
        gold_sql="SELECT carrier, COUNT(*) FROM shipments GROUP BY carrier;",
        sql_explanation="Groups shipments by carrier.",
        difficulty=Difficulty.BEGINNER,
        tags=("shipments", "grouping"),
        expected_result_description="One row per carrier.",
        expected_result_shape=ResultShape.ROW_LIST,
    )


@pytest.fixture
def sample_examples(
    matching_example: QueryExample, unrelated_example: QueryExample
) -> tuple[QueryExample, ...]:
    return (matching_example, unrelated_example)


@pytest.fixture
def sample_library(sample_examples: tuple[QueryExample, ...]) -> QueryExampleLibrary:
    return build_library(sample_examples)
