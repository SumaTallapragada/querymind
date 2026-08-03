"""Supplier generator (feeds Phase 2 §3.4 `suppliers`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import ClassVar

from querymind.models.supplier import Supplier
from querymind.seeds.base import BaseGenerator, SeedContext
from querymind.seeds.config import SeedConfig
from querymind.seeds.utils import create_faker, random_datetime_between, weighted_choice


class SupplierGenerator(BaseGenerator[Supplier]):
    """Generates standalone `Supplier` records.

    No dependencies on other generators — suppliers are a root entity in
    the FK dependency graph and generate first (Phase 2 §9 seed data
    strategy). No dedicated `SupplierRules` class exists: Phase 4A only
    defined rules for entities with ongoing behavioral decisions to make
    (order timing, payment success, ...); a supplier's attributes are
    simple, one-time facts drawn directly from Faker plus a small,
    self-contained weighted distribution.

    Constructed with `config: SeedConfig` (new in Phase 4B) for locale
    and `created_at`-adjacent business-window bounds; `context` is kept
    for compatibility with `BaseGenerator`'s existing contract.
    """

    #: Countries suppliers are commonly sourced from, weighted toward
    #: manufacturing hubs.
    _COUNTRY_WEIGHTS: ClassVar[dict[str, float]] = {
        "CN": 0.35,
        "US": 0.15,
        "VN": 0.10,
        "IN": 0.10,
        "MX": 0.08,
        "DE": 0.07,
        "TR": 0.05,
        "BD": 0.05,
        "IT": 0.05,
    }

    def __init__(self, count: int, config: SeedConfig, context: SeedContext | None = None) -> None:
        super().__init__(count, context)
        self.config = config
        self._faker = create_faker(self.context.seed, config.locale)

    def generate(self) -> list[Supplier]:
        countries = list(self._COUNTRY_WEIGHTS.keys())
        weights = list(self._COUNTRY_WEIGHTS.values())
        # Suppliers are onboarded well before the tracked business window
        # begins — `created_at` doubles as an approximate onboarding date
        # for this table (Phase 2 §5 data dictionary synonym).
        window_end = datetime.combine(
            self.config.business_start_date, datetime.min.time(), tzinfo=UTC
        )
        window_start = window_end - timedelta(days=365 * 10)
        suppliers: list[Supplier] = []
        for index in range(1, self.count + 1):
            onboarded = random_datetime_between(self.rng, window_start, window_end)
            suppliers.append(
                Supplier(
                    supplier_code=f"SUP-{index:04d}",
                    supplier_name=self._faker.company(),
                    contact_email=self._faker.company_email(),
                    contact_phone=self._faker.phone_number(),
                    country_code=weighted_choice(self.rng, countries, weights),
                    lead_time_days=self.rng.randint(5, 45),
                    rating=round(self.rng.uniform(2.5, 5.0), 2),
                    is_active=self.rng.random() < 0.95,
                    created_at=onboarded,
                )
            )
        return suppliers
