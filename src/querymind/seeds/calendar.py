"""Reusable business calendar utilities: weekends, holidays, and seasonal campaigns.

Pure date logic only — nothing here generates a record. Business rule
classes (`querymind.seeds.rules`) query a calendar to decide how a given
date should be weighted; the calendar itself has no opinion about
customers, orders, or any other domain concept.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Protocol


class HolidayName(str, Enum):
    """The fixed holidays `BusinessCalendar` recognizes."""

    NEW_YEAR = "new_year"
    THANKSGIVING = "thanksgiving"
    BLACK_FRIDAY = "black_friday"
    CHRISTMAS = "christmas"


@dataclass(frozen=True, slots=True)
class Holiday:
    """One concrete holiday occurrence in a given year."""

    name: HolidayName
    date: date
    label: str


@dataclass(frozen=True, slots=True)
class SeasonalCampaign:
    """A named seasonal demand window, e.g. "Black Friday / Cyber Monday"."""

    name: str
    start: date
    end: date
    demand_multiplier: float


class CalendarProtocol(Protocol):
    """The calendar surface business rule classes depend on.

    `BusinessCalendar` satisfies this structurally; rule classes
    (`querymind.seeds.rules.base.BaseRules`) type against the protocol so
    a test can inject a fake calendar without constructing a real one.
    """

    def is_weekend(self, day: date) -> bool:
        """Whether `day` falls on a Saturday or Sunday."""
        ...

    def is_holiday(self, day: date) -> bool:
        """Whether `day` is a recognized holiday."""
        ...

    def seasonal_multiplier(self, day: date) -> float:
        """The configured seasonal demand multiplier for `day`'s calendar month."""
        ...


class BusinessCalendar:
    """Weekends, holidays, and seasonal campaign windows for the simulated business.

    Constructed with the `seasonal_multipliers` from a `SeedConfig`
    (calendar month -> multiplier), so a `ScenarioProfile` that overrides
    those multipliers automatically reshapes every campaign window this
    calendar reports — the calendar holds no seasonal opinion of its own.
    """

    def __init__(self, seasonal_multipliers: dict[int, float] | None = None) -> None:
        self._seasonal_multipliers = dict(seasonal_multipliers or {})

    @staticmethod
    def is_weekend(day: date) -> bool:
        """Whether `day` falls on a Saturday or Sunday."""
        return day.weekday() >= 5

    @staticmethod
    def new_years_day(year: int) -> date:
        """January 1st of `year`."""
        return date(year, 1, 1)

    @staticmethod
    def christmas(year: int) -> date:
        """December 25th of `year`."""
        return date(year, 12, 25)

    @staticmethod
    def thanksgiving(year: int) -> date:
        """The 4th Thursday of November in `year` (US convention)."""
        first_of_month = date(year, 11, 1)
        first_thursday_offset = (3 - first_of_month.weekday()) % 7  # Thursday == 3
        first_thursday = first_of_month + timedelta(days=first_thursday_offset)
        return first_thursday + timedelta(weeks=3)

    @classmethod
    def black_friday(cls, year: int) -> date:
        """The day after Thanksgiving in `year`."""
        return cls.thanksgiving(year) + timedelta(days=1)

    def holidays_for_year(self, year: int) -> tuple[Holiday, ...]:
        """Every recognized holiday occurrence in `year`."""
        return (
            Holiday(HolidayName.NEW_YEAR, self.new_years_day(year), "New Year's Day"),
            Holiday(HolidayName.THANKSGIVING, self.thanksgiving(year), "Thanksgiving"),
            Holiday(HolidayName.BLACK_FRIDAY, self.black_friday(year), "Black Friday"),
            Holiday(HolidayName.CHRISTMAS, self.christmas(year), "Christmas"),
        )

    def is_holiday(self, day: date) -> bool:
        """Whether `day` is one of the recognized holidays for its year."""
        return any(holiday.date == day for holiday in self.holidays_for_year(day.year))

    def seasonal_multiplier(self, day: date) -> float:
        """The configured seasonal demand multiplier for `day`'s calendar month.

        Defaults to `1.0` (no seasonal effect) for any month not present
        in the configured multipliers.
        """
        return self._seasonal_multipliers.get(day.month, 1.0)

    def standard_campaigns(self, year: int) -> tuple[SeasonalCampaign, ...]:
        """The standard e-commerce seasonal campaign windows for `year`.

        Each campaign's `demand_multiplier` comes straight from the
        configured `seasonal_multipliers` — this method never hardcodes a
        multiplier of its own, so overriding those multipliers (as a
        `ScenarioProfile` does) automatically reshapes these windows too.
        """
        black_friday = self.black_friday(year)
        return (
            SeasonalCampaign(
                name="Black Friday / Cyber Monday",
                start=black_friday,
                end=black_friday + timedelta(days=3),
                demand_multiplier=self.seasonal_multiplier(black_friday),
            ),
            SeasonalCampaign(
                name="Holiday Season",
                start=date(year, 12, 1),
                end=date(year, 12, 31),
                demand_multiplier=self.seasonal_multiplier(date(year, 12, 15)),
            ),
            SeasonalCampaign(
                name="Back to School",
                start=date(year, 8, 1),
                end=date(year, 8, 31),
                demand_multiplier=self.seasonal_multiplier(date(year, 8, 15)),
            ),
        )
