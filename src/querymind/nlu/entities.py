"""Business entity and dimension extraction.

Recognizes mentions of business *entities* (the "nouns" of the domain —
customer, order, product, ...) and *dimensions* (categorical attributes a
metric can be broken down or filtered by — region, category, status,
...) in a normalized question, using a fixed, hand-curated vocabulary of
synonyms. Deliberately has no knowledge of `querymind.models` or
`querymind.metadata` — mapping these canonical names onto real tables and
columns is schema linking, a later phase.

Also defines `find_vocabulary_matches`, the longest-match-first,
non-overlapping lookup shared with `querymind.nlu.metrics` — both modules
recognize phrases from a fixed `dict[str, str]` vocabulary the same way,
so the matching algorithm is written once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

#: Recognized phrase -> canonical entity name.
ENTITY_SYNONYMS: dict[str, str] = {
    "customers": "customer",
    "customer": "customer",
    "clients": "customer",
    "client": "customer",
    "buyers": "customer",
    "buyer": "customer",
    "shoppers": "customer",
    "shopper": "customer",
    "order items": "order_item",
    "order item": "order_item",
    "line items": "order_item",
    "line item": "order_item",
    "orders": "order",
    "order": "order",
    "purchases": "order",
    "purchase": "order",
    "product categories": "category",
    "product category": "category",
    "categories": "category",
    "category": "category",
    "products": "product",
    "product": "product",
    "items": "product",
    "item": "product",
    "skus": "product",
    "sku": "product",
    "suppliers": "supplier",
    "supplier": "supplier",
    "vendors": "supplier",
    "vendor": "supplier",
    "warehouses": "warehouse",
    "warehouse": "warehouse",
    "payments": "payment",
    "payment": "payment",
    "transactions": "payment",
    "transaction": "payment",
    "shipments": "shipment",
    "shipment": "shipment",
    "deliveries": "shipment",
    "delivery": "shipment",
    "reviews": "review",
    "review": "review",
    "ratings": "review",
    "rating": "review",
    "returns": "return",
    "return": "return",
    "refunds": "return",
    "refund": "return",
    "promotions": "promotion",
    "promotion": "promotion",
    "promo codes": "promotion",
    "promo code": "promotion",
    "inventory": "inventory",
    "stock": "inventory",
}

#: Recognized phrase -> canonical dimension name: categorical attributes
#: a metric can be grouped or filtered by. Deliberately excludes
#: calendar words ("month", "year", "quarter") — those are owned by
#: `querymind.nlu.time` and would otherwise double-count against a
#: `TimeExpression` extracted from the same phrase.
DIMENSION_SYNONYMS: dict[str, str] = {
    "regions": "region",
    "region": "region",
    "countries": "country",
    "country": "country",
    "states": "state",
    "state": "state",
    "cities": "city",
    "city": "city",
    "customer segment": "customer_segment",
    "customer segments": "customer_segment",
    "segments": "customer_segment",
    "segment": "customer_segment",
    "sales channel": "sales_channel",
    "sales channels": "sales_channel",
    "channels": "sales_channel",
    "channel": "sales_channel",
    "order status": "order_status",
    "status": "order_status",
    "payment method": "payment_method",
    "payment methods": "payment_method",
    "carriers": "carrier",
    "carrier": "carrier",
    "gender": "gender",
    "product name": "product_name",
}


def find_vocabulary_matches(text: str, vocabulary: dict[str, str]) -> list[tuple[str, int, str]]:
    """Return every non-overlapping vocabulary phrase found in `text`.

    Each result is `(canonical_name, start_position, matched_text)`,
    ordered by position. Longer phrases are tried first so a multi-word
    phrase claims its span before a shorter phrase nested inside it can
    separately match (e.g. "product category" claims its full span
    before the "product" inside it would otherwise also match under a
    different canonical name) — every character of `text` contributes to
    at most one recognized concept, and each canonical name is reported
    at most once, at its earliest match.
    """
    claimed: list[tuple[int, int]] = []
    found: dict[str, tuple[int, str]] = {}
    for phrase in sorted(vocabulary, key=len, reverse=True):
        canonical = vocabulary[phrase]
        if canonical in found:
            continue
        for match in re.finditer(rf"\b{re.escape(phrase)}\b", text):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in claimed):
                continue
            claimed.append(span)
            found[canonical] = (span[0], match.group(0))
            break
    return sorted(
        ((name, position, matched) for name, (position, matched) in found.items()),
        key=lambda item: item[1],
    )


@dataclass(frozen=True, slots=True)
class EntityExtractionResult:
    """The entities and dimensions recognized in a question."""

    primary_entity: str | None
    secondary_entities: tuple[str, ...]
    dimensions: tuple[str, ...]


class EntityExtractor(Protocol):
    """Recognizes business entities and dimensions in a normalized question."""

    def extract(self, normalized_question: str) -> EntityExtractionResult:
        """Return the entities and dimensions recognized in `normalized_question`."""
        ...


class DefaultEntityExtractor:
    """Rule-based `EntityExtractor` using a fixed business vocabulary.

    The first entity phrase to appear in the question (by character
    position) becomes `primary_entity`; every other distinct entity
    mentioned becomes a secondary entity, in the order they appear.
    """

    def extract(self, normalized_question: str) -> EntityExtractionResult:
        entity_matches = find_vocabulary_matches(normalized_question, ENTITY_SYNONYMS)
        dimension_matches = find_vocabulary_matches(normalized_question, DIMENSION_SYNONYMS)

        entities = [name for name, _position, _matched in entity_matches]
        primary = entities[0] if entities else None
        secondary = tuple(entities[1:])
        dimensions = tuple(name for name, _position, _matched in dimension_matches)

        return EntityExtractionResult(
            primary_entity=primary, secondary_entities=secondary, dimensions=dimensions
        )
