"""Product review generator (feeds Phase 2 §3.12 `product_reviews`)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import ClassVar

from querymind.models.customer import Customer
from querymind.models.order import OrderItem, OrderStatus
from querymind.models.product import Product
from querymind.models.review import ProductReview
from querymind.models.shipment import Shipment
from querymind.seeds.base import BaseGenerator, SeedContext
from querymind.seeds.rules.review import ReviewRules


class ProductReviewGenerator(BaseGenerator[ProductReview]):
    """Generates `ProductReview` records for already-generated, delivered order items.

    Consumes `ReviewRules` for eligibility, rating, and posting-delay
    decisions. Only order items belonging to a `DELIVERED` order are ever
    considered — matching "only delivered orders may receive reviews" —
    and `review_date` is always computed as that order's shipment
    `delivered_at` plus `ReviewRules.review_delay_days()`, guaranteeing it
    can never land before delivery.

    `shipments` is a new required dependency beyond the original Phase 3
    signature: delivery timing can't be known without it. Every review
    this generator produces is a verified purchase — it only ever
    materializes from a real, delivered `OrderItem`.

    Because eligibility is a per-item probabilistic draw governed by
    `config.review_rate`, this generator's returned length is the natural
    result of that process, not forced to exactly match `count` — the
    same trade-off `OrderItemGenerator` makes.
    """

    #: rating -> (title, text) options, so review tone actually matches
    #: the star rating instead of being generic filler text.
    _REVIEW_CONTENT: ClassVar[dict[int, list[tuple[str, str]]]] = {
        5: [
            (
                "Excellent!",
                "Exceeded my expectations. Works exactly as described and arrived quickly.",
            ),
            (
                "Love it",
                "Best purchase I've made in a while. Highly recommend to anyone considering it.",
            ),
            ("Perfect", "Exactly what I needed. Great quality for the price."),
        ],
        4: [
            ("Very good", "Solid product, does what it says. Minor nitpicks but overall happy."),
            ("Great value", "Good quality for the price. Would buy again."),
            ("Happy with it", "Works well — a couple of small issues but nothing major."),
        ],
        3: [
            ("It's okay", "Does the job but nothing special. Average quality."),
            ("Decent", "Not bad, not great. Meets basic expectations."),
            ("Mixed feelings", "Some things I like, some I don't. Middle of the road."),
        ],
        2: [
            ("Disappointed", "Not what I expected. Quality feels below average."),
            ("Below expectations", "Had some issues out of the box. Wouldn't recommend."),
        ],
        1: [
            ("Not satisfied", "Arrived damaged and doesn't work as described."),
            ("Would not recommend", "Poor quality — broke within days of use."),
        ],
    }

    def __init__(
        self,
        count: int,
        products: Sequence[Product],
        customers: Sequence[Customer],
        order_items: Sequence[OrderItem] | None = None,
        context: SeedContext | None = None,
        *,
        shipments: Sequence[Shipment],
        rules: ReviewRules,
    ) -> None:
        super().__init__(count, context)
        self.products = products
        self.customers = customers
        self.order_items = order_items or []
        self.shipments = shipments
        self.rules = rules

    def generate(self) -> list[ProductReview]:
        delivered_at_by_order = self._delivered_at_by_order()

        reviews: list[ProductReview] = []
        for item in self.order_items:
            order = item.order
            if order.order_status != OrderStatus.DELIVERED:
                continue
            delivered_at = delivered_at_by_order.get(id(order))
            if delivered_at is None:
                continue
            if not self.rules.is_eligible_for_review(is_verified_purchase=True):
                continue

            rating = self.rules.assign_rating()
            title, text = self.rng.choice(self._REVIEW_CONTENT[rating])
            review = ProductReview(
                rating=rating,
                review_title=title,
                review_text=text,
                is_verified_purchase=True,
                review_date=delivered_at + timedelta(days=self.rules.review_delay_days()),
            )
            review.product = item.product
            review.customer = order.customer
            review.order_item = item
            reviews.append(review)

        return reviews

    def _delivered_at_by_order(self) -> dict[int, datetime]:
        delivered_at: dict[int, datetime] = {}
        for shipment in self.shipments:
            if shipment.delivered_at is None:
                continue
            key = id(shipment.order)
            existing = delivered_at.get(key)
            if existing is None or shipment.delivered_at > existing:
                delivered_at[key] = shipment.delivered_at
        return delivered_at
