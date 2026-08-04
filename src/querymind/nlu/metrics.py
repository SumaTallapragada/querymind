"""Business metric extraction.

Recognizes mentions of measurable business quantities (revenue, order
count, average rating, ...) in a normalized question, and the reducer
(`AggregationType`) explicitly requested alongside each one, using a
fixed vocabulary — the same deliberate boundary as `entities.py`: no
lookup against the real schema, only canonical business concept names.
"""

from __future__ import annotations

import re
from typing import Protocol

from querymind.nlu.entities import find_vocabulary_matches
from querymind.nlu.models import AggregationType, MetricExpression

#: Recognized phrase -> canonical metric name.
METRIC_SYNONYMS: dict[str, str] = {
    "total sales": "revenue",
    "gross merchandise value": "revenue",
    "revenue": "revenue",
    "sales": "revenue",
    "gmv": "revenue",
    "profit": "profit",
    "margin": "profit",
    "average order value": "average_order_value",
    "aov": "average_order_value",
    "order value": "order_value",
    "order count": "order_count",
    "number of orders": "order_count",
    "quantity sold": "quantity",
    "units sold": "quantity",
    "quantity": "quantity",
    "unit price": "price",
    "price": "price",
    "cost price": "cost",
    "cost": "cost",
    "discount amount": "discount_amount",
    "discount": "discount_amount",
    "tax amount": "tax_amount",
    "tax": "tax_amount",
    "shipping cost": "shipping_amount",
    "shipping fee": "shipping_amount",
    "return rate": "return_rate",
    "average rating": "review_rating",
    "review rating": "review_rating",
    "rating": "review_rating",
    "inventory level": "inventory_level",
    "stock level": "inventory_level",
    "quantity on hand": "inventory_level",
    "lead time": "lead_time",
}

#: Aggregation keyword -> `AggregationType`, checked against the text
#: immediately preceding a metric mention.
_AGGREGATION_KEYWORDS: dict[str, AggregationType] = {
    "sum of": AggregationType.SUM,
    "total": AggregationType.SUM,
    "sum": AggregationType.SUM,
    "average": AggregationType.AVERAGE,
    "avg": AggregationType.AVERAGE,
    "mean": AggregationType.AVERAGE,
    "count of": AggregationType.COUNT,
    "number of": AggregationType.COUNT,
    "how many": AggregationType.COUNT,
    "count": AggregationType.COUNT,
    "minimum": AggregationType.MIN,
    "lowest": AggregationType.MIN,
    "smallest": AggregationType.MIN,
    "cheapest": AggregationType.MIN,
    "min": AggregationType.MIN,
    "maximum": AggregationType.MAX,
    "highest": AggregationType.MAX,
    "largest": AggregationType.MAX,
    "max": AggregationType.MAX,
}

#: How far (in characters) before a metric mention to look for an
#: aggregation keyword.
_AGGREGATION_WINDOW = 20


class MetricExtractor(Protocol):
    """Recognizes business metrics, and their requested aggregation, in a normalized question."""

    def extract(self, normalized_question: str) -> tuple[MetricExpression, ...]:
        """Return every metric mentioned in `normalized_question`, in first-mention order."""
        ...


def _find_aggregation_before(text: str, position: int) -> AggregationType | None:
    """Return the aggregation keyword closest to (and before) `position`, if any."""
    window_start = max(0, position - _AGGREGATION_WINDOW)
    window = text[window_start:position]
    best: tuple[int, AggregationType] | None = None
    for keyword, aggregation in _AGGREGATION_KEYWORDS.items():
        match = re.search(rf"\b{re.escape(keyword)}\b", window)
        if match and (best is None or match.start() > best[0]):
            best = (match.start(), aggregation)
    return best[1] if best else None


class DefaultMetricExtractor:
    """Rule-based `MetricExtractor` using a fixed business metric vocabulary."""

    def extract(self, normalized_question: str) -> tuple[MetricExpression, ...]:
        matches = find_vocabulary_matches(normalized_question, METRIC_SYNONYMS)
        metrics = [
            MetricExpression(
                name=canonical,
                aggregation=_find_aggregation_before(normalized_question, position),
                raw_text=raw_text,
            )
            for canonical, position, raw_text in matches
        ]
        return tuple(metrics)
