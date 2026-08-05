"""ValueFormatter: deterministic, locale-independent formatting of a single raw value.

No localization (no thousands separators, no locale-specific date
formats), no unexpected rounding (floats and Decimals are rendered via
`str()`, which is exact/round-trippable in Python -- never `round()` or
`format(value, ",.2f")`), and no currency inference (a numeric column is
never assumed to represent money).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from querymind.result_formatter.models import FormattedValue


class ValueFormatter:
    """Formats one raw value into a `FormattedValue`. Stateless, deterministic."""

    def format(self, value: Any) -> FormattedValue:
        """Convert `value` into a `FormattedValue`. Never raises for any input type."""
        formatted_value, detected_type = self._render(value)
        return FormattedValue(
            original_value=value, formatted_value=formatted_value, detected_type=detected_type
        )

    @staticmethod
    def _render(value: Any) -> tuple[str, str]:
        # `bool` must be checked before `int` -- `bool` is a subclass of `int` in Python.
        if value is None:
            return "NULL", "none"
        if isinstance(value, bool):
            return ("true" if value else "false"), "bool"
        if isinstance(value, int):
            return str(value), "int"
        if isinstance(value, float):
            return str(value), "float"
        if isinstance(value, Decimal):
            return str(value), "decimal"
        # `datetime` must be checked before `date` -- `datetime` is a subclass of `date`.
        if isinstance(value, datetime):
            return value.isoformat(), "datetime"
        if isinstance(value, date):
            return value.isoformat(), "date"
        if isinstance(value, str):
            return value, "str"
        # Any other real-world driver value (e.g. `uuid.UUID`, a JSON/JSONB `dict`/`list`)
        # still needs a deterministic, non-crashing text form -- `str()` is exact for these.
        return str(value), type(value).__name__
