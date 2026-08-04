from __future__ import annotations

from datetime import date

import pytest

from querymind.nlu.models import TimePeriod
from querymind.nlu.time import DefaultTimeExtractor

#: A fixed Monday, so week/month/quarter/year boundary math is exact and
#: reproducible without depending on the real system clock.
_REFERENCE = date(2026, 8, 3)
_EXTRACTOR = DefaultTimeExtractor(reference_date=_REFERENCE)


@pytest.mark.parametrize(
    ("phrase", "period", "start", "end"),
    [
        ("today", TimePeriod.TODAY, date(2026, 8, 3), date(2026, 8, 3)),
        ("yesterday", TimePeriod.YESTERDAY, date(2026, 8, 2), date(2026, 8, 2)),
        ("this week", TimePeriod.THIS_WEEK, date(2026, 8, 3), date(2026, 8, 9)),
        ("last week", TimePeriod.LAST_WEEK, date(2026, 7, 27), date(2026, 8, 2)),
        ("this month", TimePeriod.THIS_MONTH, date(2026, 8, 1), date(2026, 8, 31)),
        ("last month", TimePeriod.LAST_MONTH, date(2026, 7, 1), date(2026, 7, 31)),
        ("this quarter", TimePeriod.THIS_QUARTER, date(2026, 7, 1), date(2026, 9, 30)),
        ("last quarter", TimePeriod.LAST_QUARTER, date(2026, 4, 1), date(2026, 6, 30)),
        ("this year", TimePeriod.THIS_YEAR, date(2026, 1, 1), date(2026, 12, 31)),
        ("last year", TimePeriod.LAST_YEAR, date(2025, 1, 1), date(2025, 12, 31)),
    ],
)
def test_resolves_relative_period_bounds(
    phrase: str, period: TimePeriod, start: date, end: date
) -> None:
    result = _EXTRACTOR.extract(f"revenue {phrase}")
    assert result is not None
    assert result.period is period
    assert result.start_date == start
    assert result.end_date == end


def test_last_month_crosses_a_year_boundary() -> None:
    extractor = DefaultTimeExtractor(reference_date=date(2026, 1, 15))
    result = extractor.extract("revenue last month")
    assert result is not None
    assert result.start_date == date(2025, 12, 1)
    assert result.end_date == date(2025, 12, 31)


def test_last_quarter_crosses_a_year_boundary() -> None:
    extractor = DefaultTimeExtractor(reference_date=date(2026, 2, 1))
    result = extractor.extract("revenue last quarter")
    assert result is not None
    assert result.start_date == date(2025, 10, 1)
    assert result.end_date == date(2025, 12, 31)


def test_parses_an_explicit_between_range() -> None:
    result = _EXTRACTOR.extract("revenue between 2024-01-01 and 2024-12-31")
    assert result is not None
    assert result.period is TimePeriod.BETWEEN
    assert result.start_date == date(2024, 1, 1)
    assert result.end_date == date(2024, 12, 31)


def test_parses_a_before_date() -> None:
    result = _EXTRACTOR.extract("returns before 2026-01-01")
    assert result is not None
    assert result.period is TimePeriod.BEFORE
    assert result.start_date is None
    assert result.end_date == date(2026, 1, 1)


def test_parses_an_after_date() -> None:
    result = _EXTRACTOR.extract("orders after january 1, 2024")
    assert result is not None
    assert result.period is TimePeriod.AFTER
    assert result.start_date == date(2024, 1, 1)
    assert result.end_date is None


def test_returns_none_when_no_time_expression_present() -> None:
    assert _EXTRACTOR.extract("show me all customers") is None
