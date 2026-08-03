"""Scenario profiles: named, reusable overrides on top of a base `SeedConfig`.

Each profile changes *only* configuration values — never business-rule
logic itself. Swapping scenarios means swapping which `SeedConfig` a rule
class (or, in a later phase, a generator) is constructed from; the rule
classes themselves are completely unaware that scenarios exist.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from querymind.seeds.config import DatasetSizeConfig, SeedConfig


class SeedConfigOverrides(BaseModel):
    """Partial `SeedConfig` overrides — every field optional, defaulting to "unset".

    `ScenarioProfile.apply()` only touches the fields explicitly set
    here; everything else is inherited unchanged from the base
    `SeedConfig`. Note that `dataset_size`, when set, *replaces* the
    entire `DatasetSizeConfig` rather than merging field-by-field — a
    profile that only wants to change one dataset-size field should
    still construct the whole `DatasetSizeConfig` it wants.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_size: DatasetSizeConfig | None = None
    seed: int | None = None
    locale: str | None = None
    currency: str | None = None
    business_start_date: date | None = None
    business_end_date: date | None = None
    promotion_frequency: float | None = None
    return_rate: float | None = None
    review_rate: float | None = None
    payment_failure_rate: float | None = None
    seasonal_multipliers: dict[int, float] | None = None


class ScenarioProfile(BaseModel):
    """A named, documented set of configuration overrides.

    A profile is data, not behavior: it carries no logic of its own,
    only a `SeedConfigOverrides` to layer on top of a base `SeedConfig`
    via `apply()`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str
    overrides: SeedConfigOverrides = SeedConfigOverrides()

    def apply(self, base_config: SeedConfig) -> SeedConfig:
        """Return a new `SeedConfig`: `base_config` with this profile's overrides applied.

        `base_config` itself is left untouched (`SeedConfig` is frozen) —
        this always returns a distinct instance. Deliberately builds the
        update from the overrides' actual attribute values (`dict(...)`),
        not `model_dump()` — `model_dump()` recursively serializes nested
        models like `DatasetSizeConfig` into plain dicts, and
        `model_copy(update=...)` does not re-validate/coerce, so a dumped
        dict would silently replace a typed `DatasetSizeConfig` with an
        untyped `dict` on the resulting config.
        """
        changes = {name: value for name, value in dict(self.overrides).items() if value is not None}
        return base_config.model_copy(update=changes)


DEFAULT = ScenarioProfile(
    name="default",
    description=(
        "Baseline configuration with no overrides — the Phase 2 §9 seed data "
        "strategy volumes and rates, as-is."
    ),
)

HOLIDAY_SEASON = ScenarioProfile(
    name="holiday_season",
    description=(
        "November-December demand surge: the business window narrows to the "
        "holiday months, seasonal multipliers widen further, and promotion "
        "usage rises."
    ),
    overrides=SeedConfigOverrides(
        business_start_date=date(2025, 11, 1),
        business_end_date=date(2025, 12, 31),
        promotion_frequency=0.35,
        seasonal_multipliers={
            1: 1.0,
            2: 1.0,
            3: 1.0,
            4: 1.0,
            5: 1.0,
            6: 1.0,
            7: 1.0,
            8: 1.0,
            9: 1.0,
            10: 1.1,
            11: 2.0,
            12: 2.5,
        },
    ),
)

BLACK_FRIDAY = ScenarioProfile(
    name="black_friday",
    description=(
        "One concentrated week around Black Friday: an extreme demand spike, "
        "heavy promotion participation, and elevated payment failures from "
        "gateway load under traffic."
    ),
    overrides=SeedConfigOverrides(
        business_start_date=date(2025, 11, 24),
        business_end_date=date(2025, 11, 30),
        promotion_frequency=0.70,
        payment_failure_rate=0.06,
        seasonal_multipliers={
            1: 1.0,
            2: 1.0,
            3: 1.0,
            4: 1.0,
            5: 1.0,
            6: 1.0,
            7: 1.0,
            8: 1.0,
            9: 1.0,
            10: 1.0,
            11: 3.0,
            12: 1.0,
        },
    ),
)

INVENTORY_SHORTAGE = ScenarioProfile(
    name="inventory_shortage",
    description=(
        "Far fewer product/warehouse stock combinations maintained than the "
        "default network coverage, with a modest bump in returns as customers "
        "receive substitutions or delayed fulfillment."
    ),
    overrides=SeedConfigOverrides(
        dataset_size=DatasetSizeConfig(inventory=6_000),
        return_rate=0.08,
    ),
)

HIGH_RETURNS = ScenarioProfile(
    name="high_returns",
    description=(
        "Elevated return rate, e.g. modeling the aftermath of a quality "
        "incident or a poorly received product line."
    ),
    overrides=SeedConfigOverrides(return_rate=0.20),
)

GROWTH_YEAR = ScenarioProfile(
    name="growth_year",
    description=(
        "A full year of significant year-over-year growth: a larger dataset "
        "across every major table, over an extended business window."
    ),
    overrides=SeedConfigOverrides(
        business_start_date=date(2025, 8, 1),
        business_end_date=date(2026, 8, 1),
        dataset_size=DatasetSizeConfig(
            customers=12_000,
            products=2_600,
            orders=48_000,
            payments=49_500,
            shipments=43_000,
            inventory=20_000,
            product_reviews=19_000,
            returns=2_600,
        ),
    ),
)

#: Every built-in scenario profile, in no particular order — the name on
#: each `ScenarioProfile` is what identifies it, not its position here.
STANDARD_SCENARIOS: tuple[ScenarioProfile, ...] = (
    DEFAULT,
    HOLIDAY_SEASON,
    BLACK_FRIDAY,
    INVENTORY_SHORTAGE,
    HIGH_RETURNS,
    GROWTH_YEAR,
)
