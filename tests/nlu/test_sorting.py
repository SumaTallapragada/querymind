from __future__ import annotations

from querymind.nlu.models import AggregationType, MetricExpression, SortDirection
from querymind.nlu.sorting import DefaultSortExtractor

_EXTRACTOR = DefaultSortExtractor()
_REVENUE = (MetricExpression(name="revenue", aggregation=AggregationType.SUM, raw_text="revenue"),)


def test_explicit_sort_by_with_direction() -> None:
    result = _EXTRACTOR.extract("show orders sorted by revenue descending", _REVENUE)
    assert result is not None
    assert result.field == "revenue"
    assert result.direction is SortDirection.DESCENDING


def test_explicit_sort_by_defaults_to_descending_when_direction_omitted() -> None:
    result = _EXTRACTOR.extract("show orders sorted by revenue", _REVENUE)
    assert result is not None
    assert result.direction is SortDirection.DESCENDING


def test_superlative_highest_implies_descending_using_the_first_metric() -> None:
    result = _EXTRACTOR.extract("show the highest revenue", _REVENUE)
    assert result is not None
    assert result.field == "revenue"
    assert result.direction is SortDirection.DESCENDING


def test_superlative_cheapest_implies_ascending() -> None:
    result = _EXTRACTOR.extract("show the cheapest products by price", _REVENUE)
    assert result is not None
    assert result.direction is SortDirection.ASCENDING


def test_at_least_does_not_trigger_a_sort() -> None:
    """ "at least" is a filter threshold, not a sort request."""
    result = _EXTRACTOR.extract("reviews with rating at least 4", _REVENUE)
    assert result is None


def test_at_most_does_not_trigger_a_sort() -> None:
    result = _EXTRACTOR.extract("products with price at most 50", _REVENUE)
    assert result is None


def test_returns_none_when_no_metric_and_no_explicit_field() -> None:
    result = _EXTRACTOR.extract("show the highest revenue", ())
    assert result is None
