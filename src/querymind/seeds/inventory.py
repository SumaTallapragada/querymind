"""Inventory generator (feeds Phase 2 §3.7 `inventory`)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from querymind.models.inventory import Inventory, Warehouse
from querymind.models.product import Product
from querymind.seeds.base import BaseGenerator, SeedContext
from querymind.seeds.config import SeedConfig
from querymind.seeds.rules.inventory import InventoryRules
from querymind.seeds.utils import random_datetime_between


class InventoryGenerator(BaseGenerator[Inventory]):
    """Generates `Inventory` records for already-generated products and warehouses.

    Consumes `InventoryRules` for the warehouse-coverage ratio, the
    per-pair stocking decision, and the demand-based quantity multiplier
    — this generator makes no stocking judgment of its own that isn't
    delegated to that class. `should_stock()` is called for every
    (product, warehouse) candidate pair and genuinely influences which
    pairs are picked; because it's a probabilistic draw, the accepted
    count won't land on `self.count` exactly, so any shortfall is topped
    up (and any excess trimmed) from the same shuffled candidate pool —
    `BaseGenerator` guarantees the caller gets exactly `count` records.

    `inventory.quantity_on_hand` models a *current snapshot after ongoing
    sales*, not a day-one stock level: the approved schema has no
    per-sale stock ledger (`inventory` only carries `updated_at`, not a
    history table), so "inventory decreases after sales" is represented
    statistically — a configured fraction of stocked rows are generated
    already below their `reorder_level`, exactly the rows a "needs
    restocking" business query should surface, rather than by decrementing
    a ledger the schema doesn't have.
    """

    #: Fraction of stocked (product, warehouse) pairs generated already
    #: below their reorder threshold, simulating post-sales depletion.
    _BELOW_REORDER_FRACTION = 0.15

    #: Fraction of products treated as "high demand" for
    #: `InventoryRules.quantity_on_hand_multiplier` — the earliest
    #: products in `products` are the most popular, the same long-tail
    #: convention used by the order-side generators.
    _HIGH_DEMAND_FRACTION = 0.2

    def __init__(
        self,
        count: int,
        products: Sequence[Product],
        warehouses: Sequence[Warehouse],
        config: SeedConfig,
        rules: InventoryRules,
        context: SeedContext | None = None,
    ) -> None:
        super().__init__(count, context)
        self.products = products
        self.warehouses = warehouses
        self.config = config
        self.rules = rules

    def generate(self) -> list[Inventory]:
        if not self.products or not self.warehouses:
            raise ValueError("InventoryGenerator requires at least one product and one warehouse")
        total_possible = len(self.products) * len(self.warehouses)
        if self.count > total_possible:
            raise ValueError(
                f"count={self.count} exceeds the {total_possible} possible "
                "(product, warehouse) combinations"
            )

        coverage_ratio = self.rules.warehouse_coverage_ratio(
            len(self.products), len(self.warehouses)
        )
        product_rank = {id(product): index for index, product in enumerate(self.products)}
        high_demand_cutoff = max(1, round(len(self.products) * self._HIGH_DEMAND_FRACTION))

        window_end = datetime.combine(
            self.config.business_start_date, datetime.min.time(), tzinfo=UTC
        )
        window_start = window_end - timedelta(days=30)

        candidates = [
            (product, warehouse) for product in self.products for warehouse in self.warehouses
        ]
        self.rng.shuffle(candidates)

        accepted: list[tuple[Product, Warehouse]] = []
        rejected: list[tuple[Product, Warehouse]] = []
        for pair in candidates:
            bucket = accepted if self.rules.should_stock(coverage_ratio) else rejected
            bucket.append(pair)
        if len(accepted) < self.count:
            accepted.extend(rejected[: self.count - len(accepted)])
        selected = accepted[: self.count]

        records: list[Inventory] = []
        for product, warehouse in selected:
            is_high_demand = product_rank[id(product)] < high_demand_cutoff
            multiplier = self.rules.quantity_on_hand_multiplier(is_high_demand)
            base_quantity = self.rng.randint(10, 100)
            reorder_level = max(
                1, round(base_quantity * multiplier * self.rules.REORDER_LEVEL_RATIO)
            )

            if self.rng.random() < self._BELOW_REORDER_FRACTION:
                quantity_on_hand = self.rng.randint(0, max(reorder_level - 1, 0))
            else:
                quantity_on_hand = round(base_quantity * multiplier) + reorder_level

            inventory = Inventory(
                quantity_on_hand=quantity_on_hand,
                reorder_level=reorder_level,
                last_restocked_at=random_datetime_between(self.rng, window_start, window_end),
            )
            inventory.product = product
            inventory.warehouse = warehouse
            records.append(inventory)

        return records
