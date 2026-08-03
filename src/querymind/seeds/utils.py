"""Generic, domain-agnostic helpers shared by every seed generator.

Nothing here knows about Faker, the database, or any specific business
model — these are pure functions (weighted choice, date ranges, currency
rounding) that every domain generator in Phase 4 will share, so logic like
"round to cents" or "pick a random date in the last two years" is written
exactly once instead of copy-pasted into twelve generator files.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TypeVar

from faker import Faker

T = TypeVar("T")


def create_seeded_random(seed: int) -> random.Random:
    """Return a `random.Random` instance seeded for reproducible output.

    Every generator draws randomness from an instance built this way —
    never from the `random` module's global functions — so that two
    generators seeded identically always produce identical sequences,
    regardless of what else has drawn from the global random state.
    """
    return random.Random(seed)


def create_faker(seed: int, locale: str = "en_US") -> Faker:
    """Build a `Faker` instance seeded for reproducible output.

    Constructing and seeding the instance is infrastructure, not data
    generation: this function never calls a provider method (`.name()`,
    `.email()`, ...) on the instance it returns. Domain generators do
    that themselves once implemented, in Phase 4.
    """
    Faker.seed(seed)
    return Faker(locale)


def weighted_choice(rng: random.Random, choices: Sequence[T], weights: Sequence[float]) -> T:
    """Pick one item from `choices`, weighted by the matching `weights` entry.

    Used to model realistic skew (e.g. a Zipfian product-popularity curve,
    or an order-status split that isn't uniform across its six values) per
    the seed data strategy in Phase 2 §9.
    """
    if len(choices) != len(weights):
        raise ValueError("choices and weights must be the same length")
    if not choices:
        raise ValueError("choices must not be empty")
    return rng.choices(choices, weights=weights, k=1)[0]


def random_date_between(rng: random.Random, start: date, end: date) -> date:
    """Return a uniformly random calendar date in the inclusive range `[start, end]`."""
    if start > end:
        raise ValueError("start must not be after end")
    span_days = (end - start).days
    return start + timedelta(days=rng.randint(0, span_days))


def random_datetime_between(rng: random.Random, start: datetime, end: datetime) -> datetime:
    """Return a uniformly random timestamp in the inclusive range `[start, end]`."""
    if start > end:
        raise ValueError("start must not be after end")
    span_seconds = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, span_seconds))


def round_currency(amount: Decimal | float) -> Decimal:
    """Round a monetary amount to 2 decimal places (half-up), as `Decimal`.

    Always goes through `Decimal(str(amount))` rather than `Decimal(amount)`
    directly, so a `float` input is rounded from its printed decimal
    representation instead of its exact (and often surprising) binary
    floating-point value.
    """
    return Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def percentage_of(amount: Decimal | float, percent: float) -> Decimal:
    """Return `percent`% of `amount`, rounded to currency precision.

    E.g. `percentage_of(149.95, 10)` -> `Decimal("15.00")` — used for
    percentage-type promotions and tax/discount calculations.
    """
    return round_currency(Decimal(str(amount)) * Decimal(str(percent)) / Decimal("100"))
