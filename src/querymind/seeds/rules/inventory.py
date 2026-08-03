"""Inventory allocation-strategy business rules."""

from __future__ import annotations

from querymind.seeds.rules.base import BaseRules


class InventoryRules(BaseRules):
    """Business rules governing how stock is allocated across the warehouse network."""

    #: Reorder threshold as a fraction of typical on-hand quantity — a
    #: conservative default (restock once a fifth of typical stock
    #: remains). Not a `SeedConfig` field: it's a supply-chain policy
    #: constant, not something a scenario profile needs to vary.
    REORDER_LEVEL_RATIO = 0.2

    def warehouse_coverage_ratio(self, product_count: int, warehouse_count: int) -> float:
        """The fraction of all possible (product, warehouse) pairs that should be stocked.

        Derived from `config.dataset_size.inventory` against the full
        product x warehouse combination space, clamped to `[0, 1]`. A
        scenario like Inventory Shortage lowers `dataset_size.inventory`,
        which lowers this ratio, which is exactly what "fewer
        product/warehouse combinations stocked" means operationally.
        """
        total_possible = product_count * warehouse_count
        if total_possible <= 0:
            return 0.0
        return min(self.config.dataset_size.inventory / total_possible, 1.0)

    def should_stock(self, coverage_ratio: float) -> bool:
        """Decide whether one specific (product, warehouse) pair gets an inventory row."""
        return self.rng.random() < coverage_ratio

    def quantity_on_hand_multiplier(self, is_high_demand: bool) -> float:
        """Stock-level multiplier for high-demand vs. long-tail products.

        Popular products are kept better-stocked; long-tail products are
        allocated leaner inventory — this is what makes "lowest inventory
        levels" queries (Phase 2 §6 Q32) meaningful once real quantities
        are generated.
        """
        return 2.5 if is_high_demand else 1.0
