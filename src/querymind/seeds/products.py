"""Product generator (feeds Phase 2 §3.5 `products`)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from querymind.models.product import Product, ProductCategory
from querymind.models.supplier import Supplier
from querymind.seeds.base import BaseGenerator, SeedContext
from querymind.seeds.config import SeedConfig
from querymind.seeds.utils import create_faker, random_datetime_between, round_currency


class ProductGenerator(BaseGenerator[Product]):
    """Generates `Product` records.

    Depends on already-generated categories and suppliers — both of
    `products.category_id`/`products.supplier_id` are `NOT NULL` foreign
    keys — linked via the ORM `category`/`supplier` relationships (object
    references), not raw integer ids, matching the same reasoning as
    `ProductCategoryGenerator`.

    No dedicated `ProductRules` class exists (see `SupplierGenerator` for
    why); pricing/margin is a simple, self-contained markup model here.
    """

    #: Retail markup range applied over `cost_price` to derive
    #: `unit_price` — a simple, self-contained margin model (no dedicated
    #: `ProductRules` class was defined for this).
    _MARKUP_RANGE = (1.4, 3.2)

    def __init__(
        self,
        count: int,
        categories: Sequence[ProductCategory],
        suppliers: Sequence[Supplier],
        config: SeedConfig,
        context: SeedContext | None = None,
    ) -> None:
        super().__init__(count, context)
        self.categories = categories
        self.suppliers = suppliers
        self.config = config
        self._faker = create_faker(self.context.seed, config.locale)

    def generate(self) -> list[Product]:
        if not self.categories:
            raise ValueError("ProductGenerator requires at least one category")
        if not self.suppliers:
            raise ValueError("ProductGenerator requires at least one supplier")

        window_end = datetime.combine(
            self.config.business_start_date, datetime.min.time(), tzinfo=UTC
        )
        window_start = window_end - timedelta(days=365 * 3)

        products: list[Product] = []
        for index in range(1, self.count + 1):
            category = self.rng.choice(self.categories)
            supplier = self.rng.choice(self.suppliers)
            cost_price = round_currency(Decimal(str(round(self.rng.uniform(3.0, 250.0), 2))))
            markup = self.rng.uniform(*self._MARKUP_RANGE)
            unit_price = round_currency(cost_price * Decimal(str(markup)))
            launch_date = random_datetime_between(self.rng, window_start, window_end)

            product = Product(
                sku=f"SKU-{index:06d}",
                product_name=self._faker.catch_phrase().title(),
                description=self._faker.paragraph(nb_sentences=3),
                unit_price=unit_price,
                cost_price=cost_price,
                weight_kg=round(self.rng.uniform(0.05, 15.0), 3),
                is_active=self.rng.random() < 0.92,
                launch_date=launch_date.date(),
                created_at=launch_date,
            )
            product.category = category
            product.supplier = supplier
            products.append(product)
        return products
