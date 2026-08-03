"""Product category generator (feeds Phase 2 §3.3 `product_categories`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import ClassVar

from querymind.models.product import ProductCategory
from querymind.seeds.base import BaseGenerator, SeedContext
from querymind.seeds.config import SeedConfig


class ProductCategoryGenerator(BaseGenerator[ProductCategory]):
    """Generates the self-referencing product category hierarchy.

    No dependencies on other generators. No dedicated `CategoryRules`
    class exists (see `SupplierGenerator` for why) — the taxonomy itself
    is curated, real e-commerce category data, not something a
    probability-driven rule decides.

    Top-level categories are linked to their subcategories via the ORM
    `parent` relationship (`child.parent = parent_category`), not a raw
    `parent_category_id` integer — the parent doesn't have a real primary
    key yet at generation time (it isn't persisted until
    `TransactionRunner.persist()` runs), so only the object reference
    works here. SQLAlchemy's unit-of-work topologically sorts the insert
    order within one `add_all`/flush, resolving the self-referencing FK
    correctly even though parents and children are returned in the same
    flat list.
    """

    #: A curated, realistic e-commerce taxonomy: top-level category ->
    #: its subcategories. Real business data, not Faker noise.
    _TAXONOMY: ClassVar[dict[str, list[str]]] = {
        "Electronics": [
            "Laptops",
            "Smartphones",
            "Tablets",
            "Televisions",
            "Cameras",
            "Headphones",
            "Wearable Tech",
            "Computer Accessories",
        ],
        "Home & Kitchen": [
            "Cookware",
            "Small Appliances",
            "Furniture",
            "Bedding",
            "Home Decor",
            "Storage & Organization",
            "Lighting",
        ],
        "Apparel": [
            "Men's Clothing",
            "Women's Clothing",
            "Kids' Clothing",
            "Shoes",
            "Activewear",
            "Outerwear",
            "Accessories",
        ],
        "Sports & Outdoors": [
            "Fitness Equipment",
            "Camping & Hiking",
            "Cycling",
            "Team Sports",
            "Water Sports",
            "Outdoor Apparel",
        ],
        "Beauty & Personal Care": [
            "Skincare",
            "Haircare",
            "Makeup",
            "Fragrances",
            "Personal Care Appliances",
            "Bath & Body",
        ],
        "Books & Media": [
            "Fiction",
            "Non-Fiction",
            "Children's Books",
            "Music",
            "Movies & TV",
            "Audiobooks",
        ],
        "Toys & Games": [
            "Action Figures",
            "Board Games",
            "Building Sets",
            "Puzzles",
            "Outdoor Toys",
            "Educational Toys",
        ],
        "Automotive": [
            "Car Electronics",
            "Interior Accessories",
            "Exterior Accessories",
            "Tools & Equipment",
            "Tires & Wheels",
        ],
        "Grocery": [
            "Snacks",
            "Beverages",
            "Pantry Staples",
            "Breakfast Foods",
            "Candy & Chocolate",
        ],
        "Health & Wellness": [
            "Vitamins & Supplements",
            "Medical Supplies",
            "Fitness Trackers",
            "Personal Care",
        ],
        "Office Supplies": [
            "Writing Instruments",
            "Paper Products",
            "Desk Accessories",
            "Office Electronics",
        ],
        "Pet Supplies": [
            "Dog Supplies",
            "Cat Supplies",
            "Fish & Aquatics",
            "Small Animal Supplies",
        ],
    }

    def __init__(self, count: int, config: SeedConfig, context: SeedContext | None = None) -> None:
        super().__init__(count, context)
        self.config = config

    def generate(self) -> list[ProductCategory]:
        window_end = datetime.combine(
            self.config.business_start_date, datetime.min.time(), tzinfo=UTC
        )
        window_start = window_end - timedelta(days=365 * 5)
        created_at = window_start + (window_end - window_start) / 2

        categories: list[ProductCategory] = []
        remaining = self.count

        top_level_names = list(self._TAXONOMY.keys())
        top_levels: list[ProductCategory] = []
        for name in top_level_names:
            if remaining <= 0:
                break
            category = ProductCategory(
                category_name=name,
                category_path=name,
                is_active=True,
                created_at=created_at,
            )
            top_levels.append(category)
            categories.append(category)
            remaining -= 1

        if not top_levels:
            return categories

        # Cycle through each top-level's curated subcategory list until
        # `count` is reached. `BaseGenerator` guarantees exactly `count`
        # records, so once the curated taxonomy (12 top-level x ~4-8
        # subcategories = 80 names) is exhausted for a large `count`, keep
        # producing plausibly-named, uniquely-numbered subcategories under
        # the same top levels rather than stopping short or inventing
        # unrelated names.
        subcategory_cursors = dict.fromkeys(top_level_names, 0)
        overflow_counters = dict.fromkeys(top_level_names, 0)
        top_level_index = 0
        while remaining > 0:
            parent = top_levels[top_level_index % len(top_levels)]
            name = parent.category_name
            subcategories = self._TAXONOMY[name]
            cursor = subcategory_cursors[name]
            if cursor < len(subcategories):
                subcategory_name = subcategories[cursor]
                subcategory_cursors[name] += 1
            else:
                overflow_counters[name] += 1
                subcategory_name = f"{name} Specialty {overflow_counters[name]}"
            child = ProductCategory(
                category_name=subcategory_name,
                category_path=f"{name}/{subcategory_name}",
                is_active=True,
                created_at=created_at,
            )
            child.parent = parent
            categories.append(child)
            remaining -= 1
            top_level_index += 1

        return categories
