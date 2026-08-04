from __future__ import annotations

from querymind.nlu.metrics import DefaultMetricExtractor
from querymind.nlu.models import AggregationType

_EXTRACTOR = DefaultMetricExtractor()


def test_finds_a_metric_mention() -> None:
    metrics = _EXTRACTOR.extract("what is the revenue")
    assert [metric.name for metric in metrics] == ["revenue"]


def test_infers_aggregation_from_a_nearby_keyword() -> None:
    metrics = _EXTRACTOR.extract("what is the total revenue this month")
    assert metrics[0].name == "revenue"
    assert metrics[0].aggregation is AggregationType.SUM


def test_no_aggregation_keyword_leaves_aggregation_none() -> None:
    metrics = _EXTRACTOR.extract("show me the revenue")
    assert metrics[0].aggregation is None


def test_longer_phrase_wins_over_the_shorter_phrase_nested_inside_it() -> None:
    """ "average order value" must resolve as one metric, not also "order value"."""
    metrics = _EXTRACTOR.extract("what is the average order value")
    assert [metric.name for metric in metrics] == ["average_order_value"]


def test_finds_multiple_distinct_metrics_in_order_of_appearance() -> None:
    metrics = _EXTRACTOR.extract("show revenue and profit")
    assert [metric.name for metric in metrics] == ["revenue", "profit"]


def test_returns_empty_tuple_when_no_metric_mentioned() -> None:
    assert _EXTRACTOR.extract("show me all customers") == ()
