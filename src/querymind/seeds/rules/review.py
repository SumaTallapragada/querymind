"""Review generation-eligibility business rules."""

from __future__ import annotations

from typing import ClassVar

from querymind.seeds.rules.base import BaseRules


class ReviewRules(BaseRules):
    """Business rules governing whether a purchase gets reviewed, and with what rating."""

    #: Positively skewed, per the seed data strategy in Phase 2 §9
    #: (mean rating ~4.2/5).
    _RATING_WEIGHTS: ClassVar[dict[int, float]] = {
        1: 0.03,
        2: 0.05,
        3: 0.12,
        4: 0.30,
        5: 0.50,
    }

    def is_eligible_for_review(self, is_verified_purchase: bool) -> bool:
        """Decide whether a purchased line item receives a review.

        Verified purchases are somewhat more likely to be reviewed than
        the baseline `config.review_rate` — platforms mainly solicit
        reviews from people who actually bought the item.
        """
        rate = self.config.review_rate * (1.2 if is_verified_purchase else 0.6)
        return self.rng.random() < min(rate, 1.0)

    def assign_rating(self) -> int:
        """Draw a star rating from the positively skewed distribution."""
        return self._weighted_pick(self._RATING_WEIGHTS)

    def review_delay_days(self) -> int:
        """Days between delivery and the review being posted."""
        return self.rng.randint(1, 30)
