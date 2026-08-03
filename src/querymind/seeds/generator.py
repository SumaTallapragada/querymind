"""Seed orchestration entry point.

`SeedOrchestrator.run()` executes every generator in `SEED_GENERATION_ORDER`,
persisting each stage's output through a `TransactionRunner` before the
next stage begins (so later stages can reference already-persisted
objects), and returns a `GenerationReport` summarizing the run. It never
opens a database connection itself — the caller (see
`scripts/seed_database.py`) supplies an already-connected
`TransactionRunner`.
"""

from __future__ import annotations

import time
from random import Random
from typing import Any

from querymind.seeds.base import BaseGenerator, SeedContext, TransactionRunner
from querymind.seeds.calendar import BusinessCalendar
from querymind.seeds.categories import ProductCategoryGenerator
from querymind.seeds.config import SeedConfig
from querymind.seeds.customers import CustomerAddressGenerator, CustomerGenerator
from querymind.seeds.inventory import InventoryGenerator
from querymind.seeds.orders import OrderGenerator, OrderItemGenerator
from querymind.seeds.payments import PaymentGenerator
from querymind.seeds.products import ProductGenerator
from querymind.seeds.promotions import PromotionGenerator
from querymind.seeds.report import GenerationReport
from querymind.seeds.returns import ReturnGenerator
from querymind.seeds.reviews import ProductReviewGenerator
from querymind.seeds.rules.customer import CustomerRules
from querymind.seeds.rules.inventory import InventoryRules
from querymind.seeds.rules.order import OrderRules
from querymind.seeds.rules.payment import PaymentRules
from querymind.seeds.rules.promotion import PromotionRules
from querymind.seeds.rules.returns import ReturnRules
from querymind.seeds.rules.review import ReviewRules
from querymind.seeds.rules.shipment import ShipmentRules
from querymind.seeds.scenarios import ScenarioProfile
from querymind.seeds.shipments import ShipmentGenerator
from querymind.seeds.suppliers import SupplierGenerator
from querymind.seeds.utils import create_seeded_random
from querymind.seeds.warehouses import WarehouseGenerator

#: Every generator class, in the order Phase 4B requires: suppliers ->
#: warehouses -> categories -> products -> inventory -> customers ->
#: customer addresses -> promotions -> orders -> order items -> payments
#: -> shipments -> reviews -> returns. Inventory runs right after
#: products/warehouses (not near the end, as an earlier draft had it) so
#: stock levels exist before any order references the catalog. Purely
#: declarative — this is FK-dependency metadata; `SeedOrchestrator.run()`
#: is what actually executes it.
SEED_GENERATION_ORDER: tuple[type[BaseGenerator[Any]], ...] = (
    SupplierGenerator,
    WarehouseGenerator,
    ProductCategoryGenerator,
    ProductGenerator,
    InventoryGenerator,
    CustomerGenerator,
    CustomerAddressGenerator,
    PromotionGenerator,
    OrderGenerator,
    OrderItemGenerator,
    PaymentGenerator,
    ShipmentGenerator,
    ProductReviewGenerator,
    ReturnGenerator,
)

#: Distinct seed offsets per generator/rules instance so that giving every
#: component the *same* base seed can't make their random sequences
#: silently correlate (e.g. `SupplierGenerator` and `WarehouseGenerator`
#: independently seeded to 42 would otherwise draw identical first
#: values). Generators use offsets 1-14 (matching `SEED_GENERATION_ORDER`);
#: rules classes use 101-108 — disjoint ranges, no collisions.
_GENERATOR_SEED_OFFSETS = {
    "suppliers": 1,
    "warehouses": 2,
    "categories": 3,
    "products": 4,
    "inventory": 5,
    "customers": 6,
    "customer_addresses": 7,
    "promotions": 8,
    "orders": 9,
    "order_items": 10,
    "payments": 11,
    "shipments": 12,
    "reviews": 13,
    "returns": 14,
}
_RULES_SEED_OFFSETS = {
    "customer": 101,
    "order": 102,
    "inventory": 103,
    "promotion": 104,
    "shipment": 105,
    "payment": 106,
    "review": 107,
    "return": 108,
}


class SeedOrchestrator:
    """Coordinates running every generator in `SEED_GENERATION_ORDER`.

    Applies `scenario` (if given) to `config` once at construction, builds
    one shared `BusinessCalendar` and one instance of each `*Rules` class
    (each with its own decorrelated seed — see `_RULES_SEED_OFFSETS`),
    then `run()` walks the fourteen stages in order: generate, persist,
    repeat. Each stage's generator receives whatever earlier stages'
    *already-persisted* objects it depends on directly as constructor
    arguments — never by querying the database back.
    """

    def __init__(
        self,
        config: SeedConfig,
        transaction_runner: TransactionRunner,
        scenario: ScenarioProfile | None = None,
    ) -> None:
        self.scenario = scenario
        self.config = scenario.apply(config) if scenario is not None else config
        self.transaction_runner = transaction_runner
        self.calendar = BusinessCalendar(self.config.seasonal_multipliers)

    def _context(self, generator_name: str) -> SeedContext:
        offset = _GENERATOR_SEED_OFFSETS[generator_name]
        return SeedContext(seed=self.config.seed + offset, locale=self.config.locale)

    def _rng(self, rules_name: str) -> Random:
        offset = _RULES_SEED_OFFSETS[rules_name]
        return create_seeded_random(self.config.seed + offset)

    async def run(self) -> GenerationReport:
        """Execute every generator in `SEED_GENERATION_ORDER`, persisting as it goes.

        Returns a `GenerationReport` built from the in-memory results.
        Post-generation database validation (`DatasetValidator`) is a
        separate, subsequent step the caller runs afterward — see
        `scripts/seed_database.py`.
        """
        generation_started = time.perf_counter()
        persist_seconds = 0.0

        async def persist(records: list[Any]) -> None:
            nonlocal persist_seconds
            started = time.perf_counter()
            await self.transaction_runner.persist(records)
            persist_seconds += time.perf_counter() - started

        sizes = self.config.dataset_size

        customer_rules = CustomerRules(self.config, self.calendar, rng=self._rng("customer"))
        order_rules = OrderRules(self.config, self.calendar, rng=self._rng("order"))
        inventory_rules = InventoryRules(self.config, self.calendar, rng=self._rng("inventory"))
        promotion_rules = PromotionRules(self.config, self.calendar, rng=self._rng("promotion"))
        shipment_rules = ShipmentRules(self.config, self.calendar, rng=self._rng("shipment"))
        payment_rules = PaymentRules(self.config, self.calendar, rng=self._rng("payment"))
        review_rules = ReviewRules(self.config, self.calendar, rng=self._rng("review"))
        return_rules = ReturnRules(self.config, self.calendar, rng=self._rng("return"))

        # 1. Suppliers
        suppliers = SupplierGenerator(
            sizes.suppliers, self.config, context=self._context("suppliers")
        ).generate()
        await persist(suppliers)

        # 2. Warehouses
        warehouses = WarehouseGenerator(
            sizes.warehouses, self.config, context=self._context("warehouses")
        ).generate()
        await persist(warehouses)

        # 3. Categories
        categories = ProductCategoryGenerator(
            sizes.product_categories, self.config, context=self._context("categories")
        ).generate()
        await persist(categories)

        # 4. Products
        products = ProductGenerator(
            sizes.products, categories, suppliers, self.config, context=self._context("products")
        ).generate()
        await persist(products)

        # 5. Inventory
        inventory = InventoryGenerator(
            sizes.inventory,
            products,
            warehouses,
            self.config,
            inventory_rules,
            context=self._context("inventory"),
        ).generate()
        await persist(inventory)

        # 6. Customers
        customers = CustomerGenerator(
            sizes.customers, self.config, customer_rules, context=self._context("customers")
        ).generate()
        await persist(customers)

        # 7. Customer addresses
        customer_addresses = CustomerAddressGenerator(
            sizes.customer_addresses,
            customers,
            self.config,
            context=self._context("customer_addresses"),
        ).generate()
        await persist(customer_addresses)

        # 8. Promotions
        promotions = PromotionGenerator(
            sizes.promotions, self.config, self.calendar, context=self._context("promotions")
        ).generate()
        await persist(promotions)

        # 9. Orders
        order_generator = OrderGenerator(
            sizes.orders,
            customers,
            promotions,
            context=self._context("orders"),
            products=products,
            config=self.config,
            order_rules=order_rules,
            promotion_rules=promotion_rules,
            customer_rules=customer_rules,
        )
        orders = order_generator.generate()
        await persist(orders)

        # 10. Order items
        order_items = OrderItemGenerator(
            sizes.order_items,
            orders,
            products,
            context=self._context("order_items"),
            planned_items_by_order=order_generator.planned_items_by_order,
        ).generate()
        await persist(order_items)

        # 11. Payments
        payments = PaymentGenerator(
            sizes.payments, orders, context=self._context("payments"), rules=payment_rules
        ).generate()
        await persist(payments)

        # 12. Shipments
        shipments = ShipmentGenerator(
            sizes.shipments,
            orders,
            warehouses,
            context=self._context("shipments"),
            rules=shipment_rules,
        ).generate()
        await persist(shipments)

        # 13. Reviews
        reviews = ProductReviewGenerator(
            sizes.product_reviews,
            products,
            customers,
            order_items,
            context=self._context("reviews"),
            shipments=shipments,
            rules=review_rules,
        ).generate()
        await persist(reviews)

        # 14. Returns
        returns = ReturnGenerator(
            sizes.returns,
            order_items,
            context=self._context("returns"),
            shipments=shipments,
            payments=payments,
            rules=return_rules,
        ).generate()
        await persist(returns)

        generation_seconds = (time.perf_counter() - generation_started) - persist_seconds

        return GenerationReport.from_results(
            scenario_name=self.scenario.name if self.scenario is not None else "default",
            seed=self.config.seed,
            suppliers=suppliers,
            warehouses=warehouses,
            categories=categories,
            products=products,
            inventory=inventory,
            customers=customers,
            customer_addresses=customer_addresses,
            promotions=promotions,
            orders=orders,
            order_items=order_items,
            payments=payments,
            shipments=shipments,
            reviews=reviews,
            returns=returns,
            generation_time_seconds=generation_seconds,
            persist_time_seconds=persist_seconds,
        )
