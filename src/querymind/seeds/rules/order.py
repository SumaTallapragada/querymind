"""Order frequency and seasonal purchasing-behavior business rules.

Covers both "order frequency rules" and "seasonal purchasing behavior"
from the Phase 4A brief in a single class — the two are naturally the
same concern (how often, and when, a customer orders) rather than
separate rule classes, which is also why the Phase 4A "BUSINESS RULES"
section only names eight classes for nine listed behaviors.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import ClassVar

from querymind.models.customer import CustomerSegment
from querymind.models.order import OrderStatus, SalesChannel
from querymind.seeds.rules.base import BaseRules
from querymind.seeds.utils import random_date_between, round_currency, weighted_choice


def _month_windows(start: date, end: date) -> list[tuple[date, date]]:
    """Split `[start, end]` into per-calendar-month `(start, end)` windows, clipped at the edges."""
    windows: list[tuple[date, date]] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        next_month = (
            date(cursor.year + 1, 1, 1)
            if cursor.month == 12
            else date(cursor.year, cursor.month + 1, 1)
        )
        window_start = max(cursor, start)
        window_end = min(next_month - timedelta(days=1), end)
        windows.append((window_start, window_end))
        cursor = next_month
    return windows


class OrderRules(BaseRules):
    """Business rules governing when orders happen and how they resolve."""

    #: Matches the weighted fulfillment funnel in Phase 2 §9: ~70%
    #: delivered, ~15% shipped, ~8% pending/confirmed, ~5% cancelled,
    #: ~2% returned.
    _ORDER_STATUS_WEIGHTS: ClassVar[dict[OrderStatus, float]] = {
        OrderStatus.DELIVERED: 0.70,
        OrderStatus.SHIPPED: 0.15,
        OrderStatus.CONFIRMED: 0.04,
        OrderStatus.PENDING: 0.04,
        OrderStatus.CANCELLED: 0.05,
        OrderStatus.RETURNED: 0.02,
    }

    _SALES_CHANNEL_WEIGHTS: ClassVar[dict[SalesChannel, float]] = {
        SalesChannel.WEB: 0.45,
        SalesChannel.MOBILE_APP: 0.35,
        SalesChannel.MARKETPLACE: 0.15,
        SalesChannel.PHONE: 0.05,
    }

    #: Typical order-value multiplier by customer segment, relative to a
    #: standard customer's baseline of 1.0 — wholesale accounts order
    #: less often (see `CustomerRules.order_frequency_multiplier`) but at
    #: much higher value per order.
    _ORDER_VALUE_MULTIPLIER: ClassVar[dict[CustomerSegment, float]] = {
        CustomerSegment.STANDARD: 1.0,
        CustomerSegment.VIP: 1.4,
        CustomerSegment.WHOLESALE: 4.0,
    }

    def assign_order_status(self) -> OrderStatus:
        """Draw an order's lifecycle status from the fulfillment-funnel distribution."""
        return self._weighted_pick(self._ORDER_STATUS_WEIGHTS)

    def assign_sales_channel(self) -> SalesChannel:
        """Draw the channel an order originated from."""
        return self._weighted_pick(self._SALES_CHANNEL_WEIGHTS)

    def order_value_multiplier(self, segment: CustomerSegment) -> float:
        """How much larger/smaller a `segment` customer's typical order value is than baseline."""
        return self._ORDER_VALUE_MULTIPLIER[segment]

    def seasonal_demand_multiplier(self, order_date: date) -> float:
        """The demand multiplier in effect for `order_date`.

        Delegates to the calendar — this method exists so callers reason
        about "seasonal order demand" without needing to know the
        calendar is where that number comes from.
        """
        return self.calendar.seasonal_multiplier(order_date)

    def sample_order_date(self, start: date, end: date) -> date:
        """Draw a single order date in `[start, end]`, weighted by seasonal demand.

        Splits the range into calendar months, weights each month by its
        seasonal multiplier (a November with multiplier 1.8 is ~1.8x as
        likely to be chosen as a flat month), then draws a uniform day
        within the chosen month.
        """
        windows = _month_windows(start, end)
        weights = [self.calendar.seasonal_multiplier(window_start) for window_start, _ in windows]
        chosen_start, chosen_end = weighted_choice(self.rng, windows, weights)
        return random_date_between(self.rng, chosen_start, chosen_end)

    def sample_item_count(self) -> int:
        """Draw how many line items one order contains.

        Centered on `config.dataset_size.order_items_per_order_avg`, with
        +/-40%/+80% jitter around it, never fewer than 1.
        """
        avg = self.config.dataset_size.order_items_per_order_avg
        low = max(1, round(avg * 0.4))
        high = max(low, round(avg * 1.8))
        return self.rng.randint(low, high)

    #: A flat effective sales-tax rate. A simplification (real tax varies
    #: by jurisdiction, which this schema doesn't model per Phase 2) —
    #: not a `SeedConfig` field since no scenario profile needs to vary
    #: it, but centralized here rather than hardcoded in a generator.
    TAX_RATE = 0.0725

    #: Orders at or above this subtotal ship free.
    FREE_SHIPPING_THRESHOLD = Decimal("50.00")
    STANDARD_SHIPPING_FEE = Decimal("5.99")

    def tax_rate(self) -> float:
        """The effective sales-tax rate applied to `subtotal - discount`."""
        return self.TAX_RATE

    def shipping_fee(self, subtotal_amount: Decimal) -> Decimal:
        """The shipping fee for an order with the given subtotal.

        Free above `FREE_SHIPPING_THRESHOLD`, a flat fee otherwise.
        """
        if subtotal_amount >= self.FREE_SHIPPING_THRESHOLD:
            return round_currency(Decimal("0.00"))
        return round_currency(self.STANDARD_SHIPPING_FEE)
