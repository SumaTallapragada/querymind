"""Time expression extraction.

Recognizes calendar-relative phrases ("today", "last quarter", ...) and
explicit ranges ("between X and Y", "before X", "after X") in a
normalized question, resolving each to concrete `start_date`/`end_date`
bounds. Everything here is computed from a single injected reference
date (defaulting to `date.today()`) — never from an ad hoc call to the
system clock deep in the matching logic — so the extractor stays
deterministic and testable without mocking the clock.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Protocol

from querymind.nlu.models import TimeExpression, TimePeriod

_MONTH_NAMES: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

#: Relative-period phrase -> `TimePeriod`. No date parsing needed; bounds
#: are computed relative to the reference date instead.
_RELATIVE_PHRASES: dict[str, TimePeriod] = {
    "today": TimePeriod.TODAY,
    "yesterday": TimePeriod.YESTERDAY,
    "this week": TimePeriod.THIS_WEEK,
    "last week": TimePeriod.LAST_WEEK,
    "this month": TimePeriod.THIS_MONTH,
    "last month": TimePeriod.LAST_MONTH,
    "this quarter": TimePeriod.THIS_QUARTER,
    "last quarter": TimePeriod.LAST_QUARTER,
    "this year": TimePeriod.THIS_YEAR,
    "last year": TimePeriod.LAST_YEAR,
}

_MONTH_NAME_ALTERNATION = "|".join(_MONTH_NAMES)
#: A single explicit date token, in any of a handful of common written
#: forms: ISO (`2024-01-31`), long (`January 31, 2024` / `Jan 31 2024`),
#: month-year (`January 2024`), numeric (`01/31/2024`), or a bare year.
_DATE_TOKEN = (
    rf"(?:\d{{4}}-\d{{2}}-\d{{2}}"
    rf"|(?:{_MONTH_NAME_ALTERNATION})\s+\d{{1,2}},?\s+\d{{4}}"
    rf"|(?:{_MONTH_NAME_ALTERNATION})\s+\d{{4}}"
    rf"|\d{{1,2}}/\d{{1,2}}/\d{{4}}"
    rf"|\d{{4}})"
)
_BETWEEN_PATTERN = re.compile(rf"between\s+({_DATE_TOKEN})\s+and\s+({_DATE_TOKEN})")
_BEFORE_PATTERN = re.compile(rf"before\s+({_DATE_TOKEN})")
_AFTER_PATTERN = re.compile(rf"after\s+({_DATE_TOKEN})")

#: `strptime` formats tried, in order, against a matched `_DATE_TOKEN`.
_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%B %d, %Y",
    "%B %d %Y",
    "%b %d, %Y",
    "%b %d %Y",
    "%B %Y",
    "%b %Y",
    "%m/%d/%Y",
    "%Y",
)
#: Formats that only specify a month (or only a year) resolve to the
#: first day of that month/year, not a literal day-less date.
_MONTH_ONLY_FORMATS = frozenset({"%B %Y", "%b %Y"})
_YEAR_ONLY_FORMATS = frozenset({"%Y"})


def _parse_date_token(token: str) -> date | None:
    """Parse one matched `_DATE_TOKEN` into a concrete `date`, or `None` if malformed."""
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(token, fmt)
        except ValueError:
            continue
        if fmt in _MONTH_ONLY_FORMATS:
            return date(parsed.year, parsed.month, 1)
        if fmt in _YEAR_ONLY_FORMATS:
            return date(parsed.year, 1, 1)
        return parsed.date()
    return None


def _week_bounds(reference: date) -> tuple[date, date]:
    """Return the (Monday, Sunday) bounds of the calendar week containing `reference`."""
    start = reference - timedelta(days=reference.weekday())
    return start, start + timedelta(days=6)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    """Return the (first day, last day) bounds of the given calendar month."""
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _quarter_of(month: int) -> int:
    return (month - 1) // 3 + 1


def _quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    """Return the (first day, last day) bounds of the given calendar quarter (1-4)."""
    start_month = (quarter - 1) * 3 + 1
    start = date(year, start_month, 1)
    _, end = _month_bounds(year, start_month + 2)
    return start, end


class TimeExtractor(Protocol):
    """Recognizes the time window a normalized question refers to."""

    def extract(self, normalized_question: str) -> TimeExpression | None:
        """Return the `TimeExpression` found in `normalized_question`, or `None`."""
        ...


class DefaultTimeExtractor:
    """Rule-based `TimeExtractor` resolving relative phrases against an injected reference date."""

    def __init__(self, reference_date: date | None = None) -> None:
        self._reference_date = reference_date or date.today()

    def extract(self, normalized_question: str) -> TimeExpression | None:
        between_match = _BETWEEN_PATTERN.search(normalized_question)
        if between_match:
            start = _parse_date_token(between_match.group(1))
            end = _parse_date_token(between_match.group(2))
            if start is not None and end is not None:
                return TimeExpression(
                    period=TimePeriod.BETWEEN,
                    start_date=start,
                    end_date=end,
                    raw_text=between_match.group(0),
                )

        before_match = _BEFORE_PATTERN.search(normalized_question)
        if before_match:
            end = _parse_date_token(before_match.group(1))
            if end is not None:
                return TimeExpression(
                    period=TimePeriod.BEFORE, end_date=end, raw_text=before_match.group(0)
                )

        after_match = _AFTER_PATTERN.search(normalized_question)
        if after_match:
            start = _parse_date_token(after_match.group(1))
            if start is not None:
                return TimeExpression(
                    period=TimePeriod.AFTER, start_date=start, raw_text=after_match.group(0)
                )

        for phrase in sorted(_RELATIVE_PHRASES, key=len, reverse=True):
            match = re.search(rf"\b{re.escape(phrase)}\b", normalized_question)
            if match:
                period = _RELATIVE_PHRASES[phrase]
                start, end = self._bounds_for(period)
                return TimeExpression(
                    period=period, start_date=start, end_date=end, raw_text=match.group(0)
                )

        return None

    def _bounds_for(self, period: TimePeriod) -> tuple[date, date]:
        today = self._reference_date
        if period is TimePeriod.TODAY:
            return today, today
        if period is TimePeriod.YESTERDAY:
            yesterday = today - timedelta(days=1)
            return yesterday, yesterday
        if period is TimePeriod.THIS_WEEK:
            return _week_bounds(today)
        if period is TimePeriod.LAST_WEEK:
            return _week_bounds(today - timedelta(days=7))
        if period is TimePeriod.THIS_MONTH:
            return _month_bounds(today.year, today.month)
        if period is TimePeriod.LAST_MONTH:
            year, month = (
                (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
            )
            return _month_bounds(year, month)
        if period is TimePeriod.THIS_QUARTER:
            return _quarter_bounds(today.year, _quarter_of(today.month))
        if period is TimePeriod.LAST_QUARTER:
            quarter, year = _quarter_of(today.month) - 1, today.year
            if quarter == 0:
                quarter, year = 4, year - 1
            return _quarter_bounds(year, quarter)
        if period is TimePeriod.THIS_YEAR:
            return date(today.year, 1, 1), date(today.year, 12, 31)
        if period is TimePeriod.LAST_YEAR:
            return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
        raise AssertionError(f"unreachable: {period}")  # pragma: no cover
