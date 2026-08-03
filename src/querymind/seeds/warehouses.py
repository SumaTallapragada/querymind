"""Warehouse generator (feeds Phase 2 §3.6 `warehouses`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import ClassVar

from querymind.models.inventory import Warehouse
from querymind.seeds.base import BaseGenerator, SeedContext
from querymind.seeds.config import SeedConfig
from querymind.seeds.utils import create_faker, random_datetime_between, weighted_choice


class WarehouseGenerator(BaseGenerator[Warehouse]):
    """Generates standalone `Warehouse` records.

    No dependencies on other generators. No dedicated `WarehouseRules`
    class exists (see `SupplierGenerator` for why) — regional/coverage
    facts are drawn directly from a small, self-contained distribution.
    """

    #: (region label, country_code, weight) — regions used both for the
    #: warehouse_code and to bias city/state generation toward the US,
    #: matching a domestic-fulfillment-network assumption.
    _REGIONS: ClassVar[tuple[tuple[str, str, float], ...]] = (
        ("EAST", "US", 0.30),
        ("WEST", "US", 0.25),
        ("CENTRAL", "US", 0.20),
        ("SOUTH", "US", 0.15),
        ("INTL", "CA", 0.10),
    )

    def __init__(self, count: int, config: SeedConfig, context: SeedContext | None = None) -> None:
        super().__init__(count, context)
        self.config = config
        self._faker = create_faker(self.context.seed, config.locale)

    def generate(self) -> list[Warehouse]:
        regions = [region for region, _, _ in self._REGIONS]
        weights = [weight for _, _, weight in self._REGIONS]
        country_by_region = {region: country for region, country, _ in self._REGIONS}
        window_end = datetime.combine(
            self.config.business_start_date, datetime.min.time(), tzinfo=UTC
        )
        window_start = window_end - timedelta(days=365 * 15)
        region_sequence: dict[str, int] = dict.fromkeys(regions, 0)

        warehouses: list[Warehouse] = []
        for _ in range(self.count):
            region = weighted_choice(self.rng, regions, weights)
            region_sequence[region] += 1
            country_code = country_by_region[region]
            opened = random_datetime_between(self.rng, window_start, window_end)
            warehouses.append(
                Warehouse(
                    warehouse_code=f"WH-{region}-{region_sequence[region]:02d}",
                    warehouse_name=f"{self._faker.city()} Distribution Center",
                    city=self._faker.city(),
                    state_province=(
                        self._faker.state_abbr(include_territories=False)
                        if country_code == "US"
                        else None
                    ),
                    country_code=country_code,
                    is_active=self.rng.random() < 0.97,
                    created_at=opened,
                )
            )
        return warehouses
