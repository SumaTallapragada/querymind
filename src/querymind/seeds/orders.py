"""Order domain generators (feeds Phase 2 §3.8-3.9).

Mirrors `querymind.models.order`, which holds both `Order` and
`OrderItem` — the line-item generator is tightly coupled to the order
generator (it must know which orders exist) and lives alongside it here.

**Financial integrity** (`Order Total = Sum(Order Items) - Discount +
Tax + Shipping`) is guaranteed *by construction*, not by computing each
side independently and hoping they agree: `OrderGenerator` decides the
exact products/quantities/prices for each order (its "plan"), sums them
to get `subtotal_amount`, and derives every other financial field from
that same plan. `OrderItemGenerator` then materializes `OrderItem` rows
from exactly that plan — it never re-derives quantities or prices, so
the two can never drift apart.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal

from querymind.models.customer import Customer
from querymind.models.order import Order, OrderItem
from querymind.models.product import Product
from querymind.models.promotion import DiscountType, Promotion
from querymind.seeds.base import BaseGenerator, SeedContext
from querymind.seeds.config import SeedConfig
from querymind.seeds.rules.customer import CustomerRules
from querymind.seeds.rules.order import OrderRules
from querymind.seeds.rules.promotion import PromotionRules
from querymind.seeds.utils import create_faker, percentage_of, round_currency, weighted_choice

#: One planned order line: the product, quantity, and unit price
#: `OrderGenerator` decided for it. `OrderItemGenerator` materializes
#: `OrderItem` rows from exactly these tuples.
PlannedItem = tuple[Product, int, Decimal]

#: Quantity-per-line distribution before any segment-driven scaling —
#: most lines are a single unit, a long tail buys more.
_QUANTITY_WEIGHTS: dict[int, float] = {1: 0.55, 2: 0.22, 3: 0.12, 4: 0.07, 5: 0.04}


class OrderGenerator(BaseGenerator[Order]):
    """Generates `Order` records, fully financially resolved.

    Depends on already-generated customers (`orders.customer_id` is a
    `NOT NULL` FK) and optionally promotions (`orders.promotion_id` is
    nullable) — both linked via ORM relationships. Consumes `OrderRules`
    for status/channel/date/item-count/tax/shipping decisions,
    `PromotionRules` for whether/which promotion applies, and
    `CustomerRules.order_frequency_multiplier` to weight which customers
    place more orders (repeat VIP buyers vs. occasional standard ones).

    `products` is a new required dependency beyond the original Phase 3
    signature: an order's financial totals can't be computed without
    knowing what it actually contains, and Phase 3's stub predates any
    real data existing to reference.
    """

    def __init__(
        self,
        count: int,
        customers: Sequence[Customer],
        promotions: Sequence[Promotion] | None = None,
        context: SeedContext | None = None,
        *,
        products: Sequence[Product],
        config: SeedConfig,
        order_rules: OrderRules,
        promotion_rules: PromotionRules,
        customer_rules: CustomerRules,
    ) -> None:
        super().__init__(count, context)
        self.customers = customers
        self.promotions = promotions or []
        self.products = products
        self.config = config
        self.order_rules = order_rules
        self.promotion_rules = promotion_rules
        self.customer_rules = customer_rules
        self._faker = create_faker(self.context.seed, config.locale)
        self._planned_items: dict[int, list[PlannedItem]] = {}

    @property
    def planned_items_by_order(self) -> Mapping[int, list[PlannedItem]]:
        """`id(order)` -> the exact planned lines for that order.

        Consumed by `OrderItemGenerator` so the `OrderItem` rows it
        produces sum to exactly what this generator already computed —
        see the module docstring.
        """
        return self._planned_items

    def generate(self) -> list[Order]:
        if not self.customers:
            raise ValueError("OrderGenerator requires at least one customer")
        if not self.products:
            raise ValueError("OrderGenerator requires at least one product")

        customer_weights = [
            self.customer_rules.order_frequency_multiplier(customer.customer_segment)
            for customer in self.customers
        ]

        orders: list[Order] = []
        for index in range(1, self.count + 1):
            customer = weighted_choice(self.rng, self.customers, customer_weights)
            order_date = self.order_rules.sample_order_date(
                self.config.business_start_date, self.config.business_end_date
            )
            order_status = self.order_rules.assign_order_status()
            planned_items = self._plan_items(customer)
            subtotal_amount = round_currency(
                sum((price * qty for _, qty, price in planned_items), Decimal("0"))
            )

            promotion = self._select_promotion(order_date)
            discount_amount = self._compute_discount(promotion, subtotal_amount)
            tax_amount = round_currency(
                (subtotal_amount - discount_amount) * Decimal(str(self.order_rules.tax_rate()))
            )
            shipping_amount = self.order_rules.shipping_fee(subtotal_amount)
            total_amount = round_currency(
                subtotal_amount - discount_amount + tax_amount + shipping_amount
            )

            order_datetime = datetime.combine(
                order_date, time(hour=self.rng.randint(6, 22)), tzinfo=UTC
            )

            order = Order(
                order_number=f"ORD-{order_date.year}-{index:06d}",
                order_date=order_datetime,
                order_status=order_status,
                sales_channel=self.order_rules.assign_sales_channel(),
                shipping_address_line1=self._faker.street_address(),
                shipping_city=self._faker.city(),
                shipping_state_province=self._faker.state_abbr(include_territories=False),
                shipping_postal_code=self._faker.postcode(),
                shipping_country_code="US",
                subtotal_amount=subtotal_amount,
                discount_amount=discount_amount,
                tax_amount=tax_amount,
                shipping_amount=shipping_amount,
                total_amount=total_amount,
                currency_code=self.config.currency,
            )
            order.customer = customer
            if promotion is not None:
                order.promotion = promotion
            self._planned_items[id(order)] = planned_items
            orders.append(order)

        return orders

    def _plan_items(self, customer: Customer) -> list[PlannedItem]:
        item_count = min(self.order_rules.sample_item_count(), len(self.products))
        value_multiplier = self.order_rules.order_value_multiplier(customer.customer_segment)
        chosen_products = self._pick_products(item_count)

        quantity_choices = list(_QUANTITY_WEIGHTS.keys())
        quantity_weights = list(_QUANTITY_WEIGHTS.values())

        planned: list[PlannedItem] = []
        for product in chosen_products:
            base_quantity = weighted_choice(self.rng, quantity_choices, quantity_weights)
            quantity = max(1, round(base_quantity * value_multiplier))
            # Historical price snapshot: today's catalog price with small
            # drift, reflecting Phase 2 §3.9 — order_items.unit_price is
            # never assumed identical to products.unit_price.
            drift = Decimal(str(round(self.rng.uniform(0.92, 1.05), 4)))
            unit_price = round_currency(Decimal(str(product.unit_price)) * drift)
            planned.append((product, quantity, unit_price))
        return planned

    def _pick_products(self, item_count: int) -> list[Product]:
        """Pick `item_count` distinct products, biased toward a long-tail popularity curve.

        The earliest products in `self.products` are treated as the most
        popular — a small share of the catalog drives most sales, per the
        seed data strategy in Phase 2 §9.
        """
        weights = [1.0 / (index + 1) for index in range(len(self.products))]
        pool = list(self.products)
        pool_weights = list(weights)
        chosen: list[Product] = []
        for _ in range(min(item_count, len(pool))):
            product = weighted_choice(self.rng, pool, pool_weights)
            position = pool.index(product)
            pool.pop(position)
            pool_weights.pop(position)
            chosen.append(product)
        return chosen

    def _select_promotion(self, order_date: date) -> Promotion | None:
        if not self.promotions or not self.promotion_rules.applies_promotion():
            return None
        active = [
            promotion
            for promotion in self.promotions
            if self.promotion_rules.is_promotion_active(
                promotion.starts_at.date(), promotion.ends_at.date(), order_date
            )
        ]
        if not active:
            return None
        return self.rng.choice(active)

    def _compute_discount(self, promotion: Promotion | None, subtotal_amount: Decimal) -> Decimal:
        if promotion is None:
            return round_currency(Decimal("0.00"))
        if promotion.discount_type == DiscountType.PERCENTAGE:
            return percentage_of(subtotal_amount, float(promotion.discount_value))
        return round_currency(min(Decimal(str(promotion.discount_value)), subtotal_amount))


class OrderItemGenerator(BaseGenerator[OrderItem]):
    """Materializes `OrderItem` rows from `OrderGenerator`'s already-decided plan.

    Depends on already-generated orders and products (both `NOT NULL`
    foreign keys) plus `planned_items_by_order` (new — see
    `OrderGenerator.planned_items_by_order`). Deliberately does not
    independently pick products/quantities/prices: doing so would risk
    the resulting line items no longer summing to the parent order's
    already-computed `subtotal_amount`, breaking financial integrity.

    Because the real item count is a *derived* quantity (the natural sum
    of every order's planned lines, driven by `OrderRules.sample_item_count`
    averaging ~2.6 items/order), this generator's returned length is
    whatever that sum naturally comes out to — not forced to exactly
    match `count`. Financial correctness takes priority over hitting an
    arbitrary independent row-count target for this one entity.
    """

    def __init__(
        self,
        count: int,
        orders: Sequence[Order],
        products: Sequence[Product],
        context: SeedContext | None = None,
        *,
        planned_items_by_order: Mapping[int, list[PlannedItem]],
    ) -> None:
        super().__init__(count, context)
        self.orders = orders
        self.products = products
        self.planned_items_by_order = planned_items_by_order

    def generate(self) -> list[OrderItem]:
        valid_product_ids = {id(product) for product in self.products}
        items: list[OrderItem] = []
        for order in self.orders:
            for product, quantity, unit_price in self.planned_items_by_order.get(id(order), []):
                if id(product) not in valid_product_ids:
                    raise ValueError(
                        "OrderGenerator planned a product that is not in the injected products list"
                    )
                item = OrderItem(
                    quantity=quantity,
                    unit_price=unit_price,
                    discount_amount=round_currency(Decimal("0.00")),
                    line_total=round_currency(unit_price * quantity),
                )
                item.order = order
                item.product = product
                items.append(item)
        return items
