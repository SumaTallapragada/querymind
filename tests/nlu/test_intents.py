from __future__ import annotations

import pytest

from querymind.nlu.intents import DefaultIntentClassifier
from querymind.nlu.models import Intent

_CLASSIFIER = DefaultIntentClassifier()


@pytest.mark.parametrize(
    ("question", "expected_intent"),
    [
        ("show me the top 10 customers by revenue", Intent.TOP_N),
        ("show the bottom 5 products", Intent.TOP_N),
        ("show me the revenue trend this year", Intent.TREND),
        ("compare revenue between east and west", Intent.COMPARISON),
        ("how many orders were placed last week", Intent.COUNT),
        ("what is the average order value", Intent.AVERAGE),
        ("what is the total revenue this month", Intent.SUM),
        ("which supplier has the highest lead time", Intent.MAX),
        ("show the cheapest products", Intent.MIN),
        ("show revenue by region", Intent.AGGREGATION),
        ("list the products with price greater than 50", Intent.DETAIL),
        ("customers from california", Intent.SELECT),
    ],
)
def test_classifies_expected_intent(question: str, expected_intent: Intent) -> None:
    assert _CLASSIFIER.classify(question).intent is expected_intent


def test_at_least_does_not_trigger_min_intent() -> None:
    """ "at least" is a filter threshold (see `filters.py`), not a MIN superlative."""
    result = _CLASSIFIER.classify("show products with price at least 50")
    assert result.intent is not Intent.MIN


def test_at_most_does_not_trigger_max_intent() -> None:
    result = _CLASSIFIER.classify("show products with price at most 50")
    assert result.intent is not Intent.MAX


def test_top_n_takes_priority_over_min() -> None:
    """An explicit "top N" must win over the generic MIN superlative check."""
    result = _CLASSIFIER.classify("top 5 cheapest products")
    assert result.intent is Intent.TOP_N


def test_fallback_intent_has_lower_confidence_than_a_specific_match() -> None:
    fallback = _CLASSIFIER.classify("customers from california")
    specific = _CLASSIFIER.classify("how many customers are there")
    assert fallback.confidence < specific.confidence
