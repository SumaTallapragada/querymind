"""Configuration for the business simulation engine.

`SeedConfig` is the single, YAML-loadable object every business rule
class (`querymind.seeds.rules`) and calendar (`querymind.seeds.calendar`)
is constructed from. Nothing in this simulation layer reads an
environment variable or a bare literal directly — every tunable value
lives here, with a documented default, and can be overridden via YAML or
a `ScenarioProfile` (`querymind.seeds.scenarios`).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetSizeConfig(BaseModel):
    """Target row counts for the major tables, plus derived-quantity ratios.

    Defaults match the seed data strategy in the approved Phase 2 design
    document (`docs/phase2_database_design.md` §9) — this class makes
    those numbers configurable, it does not re-derive them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    customers: int = Field(default=8_000, gt=0)
    suppliers: int = Field(default=150, gt=0)
    warehouses: int = Field(default=8, gt=0)
    product_categories: int = Field(default=120, gt=0)
    products: int = Field(default=2_000, gt=0)
    promotions: int = Field(default=60, gt=0)
    orders: int = Field(default=30_000, gt=0)
    order_items_per_order_avg: float = Field(
        default=2.6, gt=0, description="Used to derive the `order_items` target; see the property."
    )
    payments: int = Field(default=31_000, gt=0)
    shipments: int = Field(default=27_000, gt=0)
    inventory: int = Field(default=16_000, gt=0)
    product_reviews: int = Field(default=12_000, gt=0)
    returns: int = Field(default=2_200, gt=0)
    customer_addresses_per_customer_avg: float = Field(
        default=1.4,
        gt=0,
        description="Used to derive the `customer_addresses` target; see the property.",
    )

    @property
    def order_items(self) -> int:
        """Derived target count for `order_items`.

        Not a stored field — keeping it derived from `orders` x
        `order_items_per_order_avg` means the two numbers can never drift
        out of sync with each other.
        """
        return round(self.orders * self.order_items_per_order_avg)

    @property
    def customer_addresses(self) -> int:
        """Derived target count for `customer_addresses`, on the same pattern as `order_items`."""
        return round(self.customers * self.customer_addresses_per_customer_avg)


class SeedConfig(BaseModel):
    """The complete, YAML-loadable configuration for one simulated dataset.

    Every business rule class and calendar is constructed from an
    instance of this class — never from ad hoc keyword arguments — so a
    `ScenarioProfile` can change the entire simulated business by
    producing one modified copy of it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_size: DatasetSizeConfig = Field(default_factory=DatasetSizeConfig)
    seed: int = Field(default=42, description="Deterministic random seed for the whole run.")
    locale: str = Field(default="en_US", description="Faker locale for later data generation.")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO 4217 code.")
    output_verbosity: Literal["quiet", "normal", "verbose"] = Field(
        default="normal", description="How much the generation run prints to the console."
    )
    business_start_date: date = Field(default=date(2024, 8, 1))
    business_end_date: date = Field(default=date(2026, 8, 1))
    promotion_frequency: float = Field(
        default=0.15, ge=0, le=1, description="Fraction of orders that apply a promotion."
    )
    return_rate: float = Field(
        default=0.05, ge=0, le=1, description="Fraction of eligible order items that get returned."
    )
    review_rate: float = Field(
        default=0.15, ge=0, le=1, description="Fraction of order items that receive a review."
    )
    payment_failure_rate: float = Field(
        default=0.03, ge=0, le=1, description="Fraction of payment attempts that fail."
    )
    seasonal_multipliers: dict[int, float] = Field(
        default_factory=lambda: {
            1: 1.0,
            2: 1.0,
            3: 1.0,
            4: 1.0,
            5: 1.0,
            6: 1.0,
            7: 1.0,
            8: 1.3,
            9: 1.0,
            10: 1.0,
            11: 1.8,
            12: 2.2,
        },
        description="Calendar month (1-12) -> demand multiplier.",
    )

    @model_validator(mode="after")
    def _validate_business_window(self) -> SeedConfig:
        if self.business_end_date <= self.business_start_date:
            raise ValueError("business_end_date must be after business_start_date")
        return self

    @model_validator(mode="after")
    def _validate_seasonal_multiplier_months(self) -> SeedConfig:
        invalid_months = sorted(set(self.seasonal_multipliers) - set(range(1, 13)))
        if invalid_months:
            raise ValueError(
                f"seasonal_multipliers keys must be 1-12, got invalid: {invalid_months}"
            )
        return self

    @classmethod
    def from_yaml(cls, path: Path) -> SeedConfig:
        """Load a `SeedConfig` from a YAML file.

        Any key omitted from the file falls back to its documented
        default — a scenario-specific YAML file only needs to specify
        what it changes.
        """
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(raw)
