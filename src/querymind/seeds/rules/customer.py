"""Customer lifecycle business rules."""

from __future__ import annotations

from datetime import date
from typing import ClassVar

from querymind.models.customer import CustomerSegment
from querymind.seeds.rules.base import BaseRules


class CustomerRules(BaseRules):
    """Business rules governing a customer's lifecycle: acquisition, segment, and churn.

    Pure decision logic only — see `BaseRules` for what that means and
    what it deliberately excludes.
    """

    #: Relative weights for `customers.customer_segment` — most customers
    #: are standard retail buyers; VIP and wholesale are minorities.
    _SEGMENT_WEIGHTS: ClassVar[dict[CustomerSegment, float]] = {
        CustomerSegment.STANDARD: 0.80,
        CustomerSegment.VIP: 0.15,
        CustomerSegment.WHOLESALE: 0.05,
    }

    #: Relative weights for `customers.signup_channel`.
    _SIGNUP_CHANNEL_WEIGHTS: ClassVar[dict[str, float]] = {
        "web": 0.55,
        "mobile_app": 0.30,
        "marketplace": 0.10,
        "referral": 0.05,
    }

    #: Order-frequency multiplier by segment, relative to a standard
    #: customer's baseline of 1.0.
    _ORDER_FREQUENCY_MULTIPLIER: ClassVar[dict[CustomerSegment, float]] = {
        CustomerSegment.STANDARD: 1.0,
        CustomerSegment.VIP: 2.5,
        CustomerSegment.WHOLESALE: 0.6,
    }

    def assign_segment(self) -> CustomerSegment:
        """Draw a customer segment from the standard/vip/wholesale distribution."""
        return self._weighted_pick(self._SEGMENT_WEIGHTS)

    def assign_signup_channel(self) -> str:
        """Draw a signup/acquisition channel."""
        return self._weighted_pick(self._SIGNUP_CHANNEL_WEIGHTS)

    def order_frequency_multiplier(self, segment: CustomerSegment) -> float:
        """How much more/less often a customer of `segment` orders than baseline.

        VIP customers order noticeably more often than standard retail
        customers; wholesale accounts (bulk B2B buyers) order less often
        but at much higher order value — that value effect belongs to
        `OrderRules.order_value_multiplier`, not here.
        """
        return self._ORDER_FREQUENCY_MULTIPLIER[segment]

    def is_active(self, signup_date: date, as_of: date) -> bool:
        """Whether a customer signed up on `signup_date` is still active `as_of` a given date.

        Models simple tenure-based churn: the longer a customer has been
        signed up, the more likely they've gone inactive, capped so
        long-tenured customers aren't almost-certainly churned.
        """
        tenure_days = max((as_of - signup_date).days, 0)
        churn_probability = min(tenure_days / (365 * 6), 0.35)
        return self.rng.random() >= churn_probability
