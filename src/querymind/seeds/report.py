"""Post-generation reporting and validation.

`GenerationReport` summarizes what one `SeedOrchestrator.run()` produced,
built from the in-memory generated objects and timing collected during
the run. `DatasetValidator` is a separate, subsequent step: it queries
PostgreSQL directly — not the in-memory objects — to confirm what was
actually persisted is internally consistent, independent of whatever the
generators believed they produced.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from querymind.models.customer import Customer, CustomerAddress
from querymind.models.inventory import Inventory, Warehouse
from querymind.models.order import Order, OrderItem
from querymind.models.payment import Payment, PaymentStatus
from querymind.models.product import Product, ProductCategory
from querymind.models.promotion import Promotion
from querymind.models.returns import Return
from querymind.models.review import ProductReview
from querymind.models.shipment import Shipment
from querymind.models.supplier import Supplier
from querymind.seeds.utils import round_currency


class GenerationReport(BaseModel):
    """Summary of one seed-generation run: what was produced, and how it performed.

    Built from the in-memory generated objects at the end of
    `SeedOrchestrator.run()` — no database round trip required, since
    every object already carries everything needed to compute these
    figures.
    """

    model_config = ConfigDict(frozen=True)

    scenario_name: str
    seed: int

    # -- row counts -----------------------------------------------------
    suppliers: int
    warehouses: int
    product_categories: int
    products: int
    inventory: int
    customers: int
    customer_addresses: int
    promotions: int
    orders: int
    order_items: int
    payments: int
    shipments: int
    reviews: int
    returns: int

    # -- business metrics -------------------------------------------------
    total_revenue: Decimal
    average_order_value: Decimal
    return_rate: float
    review_rate: float
    inventory_coverage: float
    promotion_usage_rate: float
    payment_success_rate: float

    # -- performance --------------------------------------------------------
    generation_time_seconds: float
    persist_time_seconds: float

    @classmethod
    def from_results(
        cls,
        *,
        scenario_name: str,
        seed: int,
        suppliers: Sequence[Supplier],
        warehouses: Sequence[Warehouse],
        categories: Sequence[ProductCategory],
        products: Sequence[Product],
        inventory: Sequence[Inventory],
        customers: Sequence[Customer],
        customer_addresses: Sequence[CustomerAddress],
        promotions: Sequence[Promotion],
        orders: Sequence[Order],
        order_items: Sequence[OrderItem],
        payments: Sequence[Payment],
        shipments: Sequence[Shipment],
        reviews: Sequence[ProductReview],
        returns: Sequence[Return],
        generation_time_seconds: float,
        persist_time_seconds: float,
    ) -> GenerationReport:
        """Compute a report from one run's generated objects and timing."""
        total_revenue = round_currency(sum((order.total_amount for order in orders), Decimal("0")))
        average_order_value = (
            round_currency(total_revenue / len(orders)) if orders else Decimal("0")
        )

        delivered_item_count = sum(
            1 for item in order_items if item.order.order_status.value == "delivered"
        )
        return_rate = len(returns) / delivered_item_count if delivered_item_count else 0.0
        review_rate = len(reviews) / delivered_item_count if delivered_item_count else 0.0

        total_possible_inventory_pairs = len(products) * len(warehouses)
        inventory_coverage = (
            len(inventory) / total_possible_inventory_pairs
            if total_possible_inventory_pairs
            else 0.0
        )

        orders_with_promotion = sum(1 for order in orders if order.promotion is not None)
        promotion_usage_rate = orders_with_promotion / len(orders) if orders else 0.0

        captured_payments = sum(
            1 for payment in payments if payment.payment_status == PaymentStatus.CAPTURED
        )
        payment_success_rate = captured_payments / len(payments) if payments else 0.0

        return cls(
            scenario_name=scenario_name,
            seed=seed,
            suppliers=len(suppliers),
            warehouses=len(warehouses),
            product_categories=len(categories),
            products=len(products),
            inventory=len(inventory),
            customers=len(customers),
            customer_addresses=len(customer_addresses),
            promotions=len(promotions),
            orders=len(orders),
            order_items=len(order_items),
            payments=len(payments),
            shipments=len(shipments),
            reviews=len(reviews),
            returns=len(returns),
            total_revenue=total_revenue,
            average_order_value=average_order_value,
            return_rate=return_rate,
            review_rate=review_rate,
            inventory_coverage=inventory_coverage,
            promotion_usage_rate=promotion_usage_rate,
            payment_success_rate=payment_success_rate,
            generation_time_seconds=generation_time_seconds,
            persist_time_seconds=persist_time_seconds,
        )

    def summary(self) -> str:
        """A pre-formatted, human-readable report for console output."""
        lines = [
            "=" * 60,
            f"GENERATION REPORT — scenario={self.scenario_name!r} seed={self.seed}",
            "=" * 60,
            "Row counts:",
            f"  suppliers            {self.suppliers:>10,}",
            f"  warehouses           {self.warehouses:>10,}",
            f"  product_categories   {self.product_categories:>10,}",
            f"  products             {self.products:>10,}",
            f"  inventory            {self.inventory:>10,}",
            f"  customers            {self.customers:>10,}",
            f"  customer_addresses   {self.customer_addresses:>10,}",
            f"  promotions           {self.promotions:>10,}",
            f"  orders               {self.orders:>10,}",
            f"  order_items          {self.order_items:>10,}",
            f"  payments             {self.payments:>10,}",
            f"  shipments            {self.shipments:>10,}",
            f"  reviews              {self.reviews:>10,}",
            f"  returns              {self.returns:>10,}",
            "",
            "Business metrics:",
            f"  Revenue                  ${self.total_revenue:,.2f}",
            f"  Average order value      ${self.average_order_value:,.2f}",
            f"  Return rate              {self.return_rate:.1%}",
            f"  Review rate              {self.review_rate:.1%}",
            f"  Inventory coverage       {self.inventory_coverage:.1%}",
            f"  Promotion usage          {self.promotion_usage_rate:.1%}",
            f"  Payment success          {self.payment_success_rate:.1%}",
            "",
            "Performance:",
            f"  Generation time          {self.generation_time_seconds:.2f}s",
            f"  Persist time             {self.persist_time_seconds:.2f}s",
            "=" * 60,
        ]
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ValidationCheck:
    """One named pass/fail validation check, with a human-readable detail."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The result of running every post-generation integrity check."""

    checks: tuple[ValidationCheck, ...]

    @property
    def all_passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def summary(self) -> str:
        lines = ["=" * 60, "VALIDATION SUMMARY", "=" * 60]
        for check in self.checks:
            status = "PASS" if check.passed else "FAIL"
            lines.append(f"[{status}] {check.name}: {check.detail}")
        lines.append("=" * 60)
        lines.append(
            "ALL CHECKS PASSED" if self.all_passed else "VALIDATION FAILED — see FAIL lines above"
        )
        return "\n".join(lines)


class DatasetValidator:
    """Runs post-generation integrity checks directly against PostgreSQL.

    Deliberately queries the database rather than re-checking in-memory
    objects — this validates what was *actually persisted*, independent
    of whatever the generators believed they produced. Some checks (no
    orphan rows) duplicate what the schema's `FK` constraints already
    physically guarantee; they're included anyway because the phase
    explicitly asks for them as an independent, visible confirmation, not
    because the database could plausibly disagree.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def validate(self) -> ValidationReport:
        checks = (
            await self._check_row_counts(),
            await self._check_no_orphan_orders(),
            await self._check_no_orphan_order_items(),
            await self._check_order_totals(),
            await self._check_payment_amounts(),
            await self._check_inventory_non_negative(),
            await self._check_review_eligibility(),
            await self._check_return_eligibility(),
        )
        return ValidationReport(checks=checks)

    async def _scalar_count(self, model: type) -> int:
        result = await self._session.execute(select(func.count()).select_from(model))
        return result.scalar_one()

    async def _check_row_counts(self) -> ValidationCheck:
        tables: tuple[tuple[type, str], ...] = (
            (Supplier, "suppliers"),
            (Warehouse, "warehouses"),
            (ProductCategory, "product_categories"),
            (Product, "products"),
            (Inventory, "inventory"),
            (Customer, "customers"),
            (CustomerAddress, "customer_addresses"),
            (Promotion, "promotions"),
            (Order, "orders"),
            (OrderItem, "order_items"),
            (Payment, "payments"),
            (Shipment, "shipments"),
            (ProductReview, "product_reviews"),
            (Return, "returns"),
        )
        counts = {name: await self._scalar_count(model) for model, name in tables}
        detail = ", ".join(f"{name}={count}" for name, count in counts.items())
        return ValidationCheck(
            "Row counts (non-zero)", all(count > 0 for count in counts.values()), detail
        )

    async def _check_no_orphan_orders(self) -> ValidationCheck:
        query = text(
            "SELECT COUNT(*) FROM orders o "
            "LEFT JOIN customers c ON o.customer_id = c.customer_id "
            "WHERE c.customer_id IS NULL"
        )
        orphans = (await self._session.execute(query)).scalar_one()
        return ValidationCheck(
            "No orphan orders (customer_id)", orphans == 0, f"{orphans} orphaned rows"
        )

    async def _check_no_orphan_order_items(self) -> ValidationCheck:
        query = text(
            "SELECT COUNT(*) FROM order_items oi "
            "LEFT JOIN orders o ON oi.order_id = o.order_id "
            "LEFT JOIN products p ON oi.product_id = p.product_id "
            "WHERE o.order_id IS NULL OR p.product_id IS NULL"
        )
        orphans = (await self._session.execute(query)).scalar_one()
        return ValidationCheck(
            "No orphan order_items (order_id, product_id)", orphans == 0, f"{orphans} orphaned rows"
        )

    async def _check_order_totals(self) -> ValidationCheck:
        query = text(
            "SELECT COUNT(*) FROM orders o WHERE "
            "o.subtotal_amount != COALESCE("
            "  (SELECT SUM(oi.line_total) FROM order_items oi WHERE oi.order_id = o.order_id), 0"
            ") "
            "OR o.total_amount != (o.subtotal_amount - o.discount_amount + o.tax_amount + o.shipping_amount)"
        )
        mismatches = (await self._session.execute(query)).scalar_one()
        return ValidationCheck(
            "Order totals correct (subtotal=SUM(items), total=subtotal-discount+tax+shipping)",
            mismatches == 0,
            f"{mismatches} mismatched orders",
        )

    async def _check_payment_amounts(self) -> ValidationCheck:
        query = text(
            "SELECT COUNT(*) FROM payments p "
            "JOIN orders o ON p.order_id = o.order_id "
            "WHERE p.amount != o.total_amount"
        )
        mismatches = (await self._session.execute(query)).scalar_one()
        return ValidationCheck(
            "Payment amounts match their order's total",
            mismatches == 0,
            f"{mismatches} mismatched payments",
        )

    async def _check_inventory_non_negative(self) -> ValidationCheck:
        query = text("SELECT COUNT(*) FROM inventory WHERE quantity_on_hand < 0")
        negative = (await self._session.execute(query)).scalar_one()
        return ValidationCheck(
            "Inventory quantities never negative", negative == 0, f"{negative} negative rows"
        )

    async def _check_review_eligibility(self) -> ValidationCheck:
        wrong_status_query = text(
            "SELECT COUNT(*) FROM product_reviews pr "
            "JOIN order_items oi ON pr.order_item_id = oi.order_item_id "
            "JOIN orders o ON oi.order_id = o.order_id "
            "WHERE o.order_status != 'delivered'"
        )
        wrong_status = (await self._session.execute(wrong_status_query)).scalar_one()

        before_delivery_query = text(
            "SELECT COUNT(*) FROM product_reviews pr "
            "JOIN order_items oi ON pr.order_item_id = oi.order_item_id "
            "JOIN orders o ON oi.order_id = o.order_id "
            "JOIN shipments s ON s.order_id = o.order_id "
            "WHERE s.delivered_at IS NOT NULL AND pr.review_date <= s.delivered_at"
        )
        before_delivery = (await self._session.execute(before_delivery_query)).scalar_one()

        passed = wrong_status == 0 and before_delivery == 0
        return ValidationCheck(
            "Review eligibility (delivered orders only, dated after delivery)",
            passed,
            f"{wrong_status} reviews on non-delivered orders, {before_delivery} dated before/at delivery",
        )

    async def _check_return_eligibility(self) -> ValidationCheck:
        query = text(
            "SELECT COUNT(*) FROM returns r "
            "JOIN order_items oi ON r.order_item_id = oi.order_item_id "
            "JOIN orders o ON oi.order_id = o.order_id "
            "WHERE o.order_status NOT IN ('delivered', 'returned')"
        )
        ineligible = (await self._session.execute(query)).scalar_one()
        return ValidationCheck(
            "Return eligibility (delivered/returned orders only)",
            ineligible == 0,
            f"{ineligible} ineligible returns",
        )
