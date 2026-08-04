"""End-to-end pipeline tests, covering the representative business
questions in Phase 5's OUTPUT deliverable.
"""

from __future__ import annotations

from datetime import date

import pytest

from querymind.nlu.exceptions import EmptyQuestionError
from querymind.nlu.models import (
    AggregationType,
    ComparisonOperator,
    Intent,
    SortDirection,
    TimePeriod,
)
from querymind.nlu.parser import QueryParser
from querymind.nlu.time import DefaultTimeExtractor

#: A fixed reference date so time-relative questions ("this month", ...)
#: produce reproducible bounds independent of the real system clock.
_REFERENCE_DATE = date(2026, 8, 3)


@pytest.fixture
def parser() -> QueryParser:
    return QueryParser(time_extractor=DefaultTimeExtractor(reference_date=_REFERENCE_DATE))


def test_raises_on_empty_question(parser: QueryParser) -> None:
    with pytest.raises(EmptyQuestionError):
        parser.parse("   ")


def test_preserves_the_original_question_verbatim(parser: QueryParser) -> None:
    context = parser.parse("What is the Total Revenue?")
    assert context.original_question == "What is the Total Revenue?"
    assert context.normalized_question == "what is the total revenue"


def test_total_revenue_this_month(parser: QueryParser) -> None:
    context = parser.parse("What is the total revenue this month?")
    assert context.intent is Intent.SUM
    assert context.aggregation is AggregationType.SUM
    assert [m.name for m in context.metrics] == ["revenue"]
    assert context.time_expression is not None
    assert context.time_expression.period is TimePeriod.THIS_MONTH


def test_top_n_customers_by_revenue(parser: QueryParser) -> None:
    context = parser.parse("Show me the top 10 customers by revenue")
    assert context.intent is Intent.TOP_N
    assert context.primary_entity == "customer"
    assert context.limit is not None
    assert context.limit.value == 10
    assert context.sort is not None
    assert context.sort.field == "revenue"
    assert context.sort.direction is SortDirection.DESCENDING


def test_count_orders_last_week(parser: QueryParser) -> None:
    context = parser.parse("How many orders were placed last week?")
    assert context.intent is Intent.COUNT
    assert context.aggregation is AggregationType.COUNT
    assert context.primary_entity == "order"
    assert context.time_expression is not None
    assert context.time_expression.period is TimePeriod.LAST_WEEK


def test_products_with_price_filter(parser: QueryParser) -> None:
    context = parser.parse("List the products with price greater than 500")
    assert context.intent is Intent.DETAIL
    assert context.primary_entity == "product"
    assert len(context.filters) == 1
    assert context.filters[0].field == "price"
    assert context.filters[0].operator is ComparisonOperator.GREATER_THAN
    assert context.filters[0].value == "500"


def test_comparison_between_regions(parser: QueryParser) -> None:
    context = parser.parse("Compare revenue between the east region and the west region")
    assert context.intent is Intent.COMPARISON
    assert context.dimensions == ("region",)
    assert [m.name for m in context.metrics] == ["revenue"]


def test_trend_this_year(parser: QueryParser) -> None:
    context = parser.parse("Show me the monthly revenue trend this year")
    assert context.intent is Intent.TREND
    assert context.time_expression is not None
    assert context.time_expression.period is TimePeriod.THIS_YEAR


def test_average_order_value_last_quarter(parser: QueryParser) -> None:
    context = parser.parse("What is the average order value last quarter?")
    assert context.intent is Intent.AVERAGE
    assert context.aggregation is AggregationType.AVERAGE
    assert [m.name for m in context.metrics] == ["average_order_value"]
    assert context.time_expression is not None
    assert context.time_expression.period is TimePeriod.LAST_QUARTER


def test_equality_filter_on_a_dimension(parser: QueryParser) -> None:
    context = parser.parse("Show products where category equals electronics")
    assert context.primary_entity == "product"
    assert len(context.filters) == 1
    assert context.filters[0].field == "category"
    assert context.filters[0].operator is ComparisonOperator.EQUALS
    assert context.filters[0].value == "electronics"


def test_max_intent_with_implicit_sort(parser: QueryParser) -> None:
    context = parser.parse("Which supplier has the highest lead time?")
    assert context.intent is Intent.MAX
    assert context.aggregation is AggregationType.MAX
    assert context.primary_entity == "supplier"
    assert context.sort is not None
    assert context.sort.direction is SortDirection.DESCENDING


def test_before_date_filter(parser: QueryParser) -> None:
    context = parser.parse("What is the return rate for returns before 2026-01-01?")
    assert context.time_expression is not None
    assert context.time_expression.period is TimePeriod.BEFORE
    assert context.time_expression.end_date == date(2026, 1, 1)


def test_min_intent_with_explicit_sort_field(parser: QueryParser) -> None:
    context = parser.parse("Show the cheapest products by price")
    assert context.intent is Intent.MIN
    assert context.aggregation is AggregationType.MIN
    assert context.sort is not None
    assert context.sort.field == "price"
    assert context.sort.direction is SortDirection.ASCENDING


def test_at_least_is_a_filter_not_a_min_intent(parser: QueryParser) -> None:
    """Regression test: "at least" must not be misread as a MIN superlative."""
    context = parser.parse("Count the number of reviews with rating at least 4")
    assert context.intent is Intent.COUNT
    assert context.aggregation is AggregationType.COUNT
    assert len(context.filters) == 1
    assert context.filters[0].field == "review_rating"
    assert context.filters[0].operator is ComparisonOperator.GREATER_THAN_OR_EQUAL
    assert context.filters[0].value == "4"


def test_business_concepts_deduplicates_across_stages(parser: QueryParser) -> None:
    context = parser.parse("Show products where category equals electronics")
    assert context.business_concepts.count("category") == 1


def test_confidence_is_within_bounds(parser: QueryParser) -> None:
    context = parser.parse("customers from california")
    assert 0.0 <= context.confidence <= 1.0
