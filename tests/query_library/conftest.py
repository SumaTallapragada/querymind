"""Shared fixtures: a small, fully synthetic library for query-library tests.

Built directly from `querymind.query_library.models` (never from the
real shipped `examples.yaml`) so every test controls its catalog
precisely. `tests/query_library/test_integration.py` separately
exercises the real shipped catalog.
"""

from __future__ import annotations

import pytest

from querymind.query_library.catalog import build_library
from querymind.query_library.models import (
    Difficulty,
    QueryContextSummary,
    QueryExample,
    QueryExampleLibrary,
    ResultShape,
    SQLDialect,
)


@pytest.fixture
def sample_examples() -> tuple[QueryExample, ...]:
    """Three well-formed examples spanning tags/concepts/difficulty, for search/registry tests."""
    return (
        QueryExample(
            id="customer_count",
            title="Total Customer Count",
            natural_language_question="How many customers do we have?",
            normalized_question="how many customers do we have",
            query_context=QueryContextSummary(
                intent="count", primary_entity="customer", aggregation="count"
            ),
            business_concepts=(),
            linked_schema_objects=("customers.customer_id",),
            gold_sql="SELECT COUNT(*) FROM customers;",
            sql_explanation="Counts every customer row.",
            difficulty=Difficulty.BEGINNER,
            tags=("customers", "aggregation"),
            dialect=SQLDialect.POSTGRESQL,
            expected_result_description="A single number.",
            expected_result_shape=ResultShape.SCALAR,
        ),
        QueryExample(
            id="top_customers_by_revenue",
            title="Top 10 Customers by Revenue",
            natural_language_question="Who are our top 10 customers by revenue?",
            normalized_question="who are our top 10 customers by revenue",
            query_context=QueryContextSummary(
                intent="top_n", primary_entity="customer", metrics=("revenue",), aggregation="sum"
            ),
            business_concepts=("revenue", "top_customer"),
            linked_schema_objects=("orders.total_amount",),
            gold_sql="SELECT customer_id, SUM(total_amount) FROM orders GROUP BY customer_id ORDER BY 2 DESC LIMIT 10;",
            sql_explanation="Sums revenue per customer and ranks them.",
            difficulty=Difficulty.INTERMEDIATE,
            tags=("customers", "top-n", "joins"),
            dialect=SQLDialect.POSTGRESQL,
            expected_result_description="Up to 10 customers ranked by revenue.",
            expected_result_shape=ResultShape.RANKED_LIST,
        ),
        QueryExample(
            id="monthly_revenue_trend",
            title="Monthly Revenue Trend",
            natural_language_question="Show monthly revenue for the past year.",
            normalized_question="show monthly revenue for the past year",
            query_context=QueryContextSummary(
                intent="trend", primary_entity="order", metrics=("revenue",), aggregation="sum"
            ),
            business_concepts=("revenue",),
            linked_schema_objects=("orders.order_date", "orders.total_amount"),
            gold_sql=(
                "SELECT DATE_TRUNC('month', order_date), SUM(total_amount) "
                "FROM orders GROUP BY 1 ORDER BY 1;"
            ),
            sql_explanation="Buckets revenue by month.",
            difficulty=Difficulty.ADVANCED,
            tags=("orders", "trend-analysis", "time-based"),
            dialect=SQLDialect.POSTGRESQL,
            expected_result_description="One row per month.",
            expected_result_shape=ResultShape.TIME_SERIES,
        ),
    )


@pytest.fixture
def sample_library(sample_examples: tuple[QueryExample, ...]) -> QueryExampleLibrary:
    return build_library(sample_examples)
