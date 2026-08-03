"""Promotion generator (feeds Phase 2 §3.13 `promotions`)."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import ClassVar

from querymind.models.promotion import DiscountType, Promotion
from querymind.seeds.base import BaseGenerator, SeedContext
from querymind.seeds.calendar import BusinessCalendar
from querymind.seeds.config import SeedConfig
from querymind.seeds.utils import round_currency, weighted_choice


class PromotionGenerator(BaseGenerator[Promotion]):
    """Generates standalone `Promotion` records.

    Windows are anchored to `BusinessCalendar.standard_campaigns` (Black
    Friday/Cyber Monday, Holiday Season, Back to School) for every year
    the configured business window spans, so promotions genuinely align
    with the seasonal calendar rather than being placed arbitrarily.
    Remaining promotions beyond the calendar-anchored ones fill in
    generic mid-window campaigns.

    No dedicated creation-time `PromotionRules` exists: `PromotionRules`
    (consumed by `OrderGenerator`) governs how an order *uses* an
    already-created promotion, not how a promotion is authored.
    """

    _GENERIC_NAMES: ClassVar[tuple[str, ...]] = (
        "Flash Sale",
        "Clearance Event",
        "Loyalty Rewards",
        "New Customer Discount",
        "Weekend Special",
        "Spring Refresh",
        "Anniversary Sale",
        "Bundle Savings",
    )

    _DISCOUNT_TYPE_WEIGHTS: ClassVar[dict[DiscountType, float]] = {
        DiscountType.PERCENTAGE: 0.65,
        DiscountType.FIXED_AMOUNT: 0.35,
    }

    def __init__(
        self,
        count: int,
        config: SeedConfig,
        calendar: BusinessCalendar | None = None,
        context: SeedContext | None = None,
    ) -> None:
        super().__init__(count, context)
        self.config = config
        self.calendar = calendar or BusinessCalendar(config.seasonal_multipliers)

    def generate(self) -> list[Promotion]:
        promotions: list[Promotion] = []
        sequence = 1

        for name, start, end in self._calendar_anchored_windows():
            if len(promotions) >= self.count:
                break
            promotions.append(self._build(sequence, name, start, end))
            sequence += 1

        while len(promotions) < self.count:
            name = self.rng.choice(self._GENERIC_NAMES)
            start = self._random_window_start()
            end = start + timedelta(days=self.rng.randint(3, 21))
            promotions.append(self._build(sequence, name, start, end))
            sequence += 1

        return promotions

    def _calendar_anchored_windows(self) -> list[tuple[str, datetime, datetime]]:
        business_start = datetime.combine(self.config.business_start_date, time.min, tzinfo=UTC)
        business_end = datetime.combine(self.config.business_end_date, time(23, 59, 59), tzinfo=UTC)

        windows: list[tuple[str, datetime, datetime]] = []
        for year in range(
            self.config.business_start_date.year, self.config.business_end_date.year + 1
        ):
            for campaign in self.calendar.standard_campaigns(year):
                start_dt = datetime.combine(campaign.start, time.min, tzinfo=UTC)
                end_dt = datetime.combine(campaign.end, time(23, 59, 59), tzinfo=UTC)
                clamped_start = max(start_dt, business_start)
                clamped_end = min(end_dt, business_end)
                if clamped_end <= clamped_start:
                    continue  # campaign doesn't overlap the business window at all
                windows.append((campaign.name, clamped_start, clamped_end))
        return windows

    def _random_window_start(self) -> datetime:
        business_start = datetime.combine(self.config.business_start_date, time.min, tzinfo=UTC)
        business_end = datetime.combine(self.config.business_end_date, time.min, tzinfo=UTC)
        buffer_seconds = 21 * 86400  # leave room for the campaign's own duration
        span_seconds = max(int((business_end - business_start).total_seconds()) - buffer_seconds, 0)
        offset = (
            timedelta(seconds=self.rng.randint(0, span_seconds))
            if span_seconds > 0
            else timedelta()
        )
        return business_start + offset

    def _build(self, sequence: int, name: str, starts_at: datetime, ends_at: datetime) -> Promotion:
        discount_type = weighted_choice(
            self.rng, list(self._DISCOUNT_TYPE_WEIGHTS), list(self._DISCOUNT_TYPE_WEIGHTS.values())
        )
        discount_value = (
            round_currency(self.rng.uniform(10, 40))
            if discount_type == DiscountType.PERCENTAGE
            else round_currency(self.rng.uniform(5, 50))
        )
        return Promotion(
            promotion_code=f"PROMO{sequence:04d}",
            promotion_name=name,
            discount_type=discount_type,
            discount_value=discount_value,
            starts_at=starts_at,
            ends_at=ends_at,
            is_active=True,
        )
