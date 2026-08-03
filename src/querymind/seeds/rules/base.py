"""Shared construction contract for every business rule class.

`BaseRules` is meant to be subclassed, never used directly — each domain
module in this package (`customer.py`, `order.py`, ...) defines one rule
class that inherits it and adds domain-specific decision methods.
"""

from __future__ import annotations

from collections.abc import Mapping
from random import Random
from typing import TypeVar

from querymind.seeds.calendar import BusinessCalendar, CalendarProtocol
from querymind.seeds.config import SeedConfig
from querymind.seeds.utils import create_seeded_random, weighted_choice

K = TypeVar("K")


class BaseRules:
    """Shared construction contract every domain rule class follows.

    Every rule class is built from a `SeedConfig` (+ an optional
    `CalendarProtocol`, defaulting to a real `BusinessCalendar` built from
    that same config's seasonal multipliers) and a seeded `random.Random`
    — obtained the same way `BaseGenerator` obtains its `rng`
    (`querymind.seeds.utils.create_seeded_random`), so a rule class and
    the generator that will eventually consume it can share one seed and
    still draw independent, reproducible random sequences by using
    separate `Random` instances.

    Rule classes expose pure decision/computation methods only — a
    probability, a weighted distribution, a boolean eligibility check, a
    date. None of them call Faker, open a database session, or construct
    an ORM instance; that remains the generator's responsibility, in a
    later phase.
    """

    def __init__(
        self,
        config: SeedConfig,
        calendar: CalendarProtocol | None = None,
        *,
        rng: Random | None = None,
    ) -> None:
        self.config = config
        self.calendar: CalendarProtocol = calendar or BusinessCalendar(config.seasonal_multipliers)
        self.rng = rng or create_seeded_random(config.seed)

    def _weighted_pick(self, distribution: Mapping[K, float]) -> K:
        """Draw one key from `distribution`, weighted by its value.

        Shared by every subclass that needs to draw from a named
        weighted distribution (segment, channel, status, ...) so the
        `list(...)`/`list(...)` unpacking into `weighted_choice` is
        written once.
        """
        choices = list(distribution.keys())
        weights = list(distribution.values())
        return weighted_choice(self.rng, choices, weights)
