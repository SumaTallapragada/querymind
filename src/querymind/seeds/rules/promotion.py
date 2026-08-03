"""Promotion-participation business rules."""

from __future__ import annotations

from datetime import date
from typing import ClassVar

from querymind.models.promotion import DiscountType
from querymind.seeds.rules.base import BaseRules


class PromotionRules(BaseRules):
    """Business rules governing whether/how an order participates in a promotion."""

    _DISCOUNT_TYPE_WEIGHTS: ClassVar[dict[DiscountType, float]] = {
        DiscountType.PERCENTAGE: 0.65,
        DiscountType.FIXED_AMOUNT: 0.35,
    }

    def applies_promotion(self) -> bool:
        """Decide whether a given order applies a promotion.

        Draws against `config.promotion_frequency` — the Black Friday
        scenario raises that to 0.7, so this returns `True` far more
        often under that profile.
        """
        return self.rng.random() < self.config.promotion_frequency

    def assign_discount_type(self) -> DiscountType:
        """Draw whether a new promotion is percentage- or fixed-amount-based."""
        return self._weighted_pick(self._DISCOUNT_TYPE_WEIGHTS)

    def is_promotion_active(self, starts_at: date, ends_at: date, order_date: date) -> bool:
        """Whether a promotion running `[starts_at, ends_at]` is active on `order_date`."""
        return starts_at <= order_date <= ends_at
