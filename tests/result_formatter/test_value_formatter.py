"""Tests for `querymind.result_formatter.value_formatter.ValueFormatter`."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from querymind.result_formatter.value_formatter import ValueFormatter


class TestValueFormatter:
    def test_none_becomes_null(self) -> None:
        result = ValueFormatter().format(None)
        assert result.formatted_value == "NULL"
        assert result.detected_type == "none"
        assert result.original_value is None

    def test_bool_true(self) -> None:
        result = ValueFormatter().format(True)
        assert result.formatted_value == "true"
        assert result.detected_type == "bool"

    def test_bool_false(self) -> None:
        result = ValueFormatter().format(False)
        assert result.formatted_value == "false"
        assert result.detected_type == "bool"

    def test_bool_is_detected_before_int(self) -> None:
        # bool is a subclass of int in Python -- must not be reported as "int".
        result = ValueFormatter().format(True)
        assert result.detected_type != "int"

    def test_int(self) -> None:
        result = ValueFormatter().format(42)
        assert result.formatted_value == "42"
        assert result.detected_type == "int"

    def test_negative_int(self) -> None:
        result = ValueFormatter().format(-7)
        assert result.formatted_value == "-7"
        assert result.detected_type == "int"

    def test_float_is_not_rounded(self) -> None:
        result = ValueFormatter().format(3.14159265)
        assert result.formatted_value == "3.14159265"
        assert result.detected_type == "float"

    def test_float_has_no_thousands_separator(self) -> None:
        result = ValueFormatter().format(1234567.5)
        assert "," not in result.formatted_value
        assert result.formatted_value == "1234567.5"

    def test_decimal_preserves_exact_precision(self) -> None:
        result = ValueFormatter().format(Decimal("19.990"))
        assert result.formatted_value == "19.990"
        assert result.detected_type == "decimal"

    def test_str_is_unmodified(self) -> None:
        result = ValueFormatter().format("Alice")
        assert result.formatted_value == "Alice"
        assert result.detected_type == "str"

    def test_date_is_isoformat(self) -> None:
        result = ValueFormatter().format(date(2026, 8, 3))
        assert result.formatted_value == "2026-08-03"
        assert result.detected_type == "date"

    def test_datetime_is_isoformat(self) -> None:
        result = ValueFormatter().format(datetime(2026, 8, 3, 10, 15, 0, tzinfo=UTC))
        assert result.formatted_value == "2026-08-03T10:15:00+00:00"
        assert result.detected_type == "datetime"

    def test_datetime_is_detected_before_date(self) -> None:
        # datetime is a subclass of date in Python -- must not be reported as "date".
        result = ValueFormatter().format(datetime(2026, 8, 3, 10, 15, 0))
        assert result.detected_type != "date"

    def test_unknown_type_falls_back_to_str_and_its_class_name(self) -> None:
        value = UUID("12345678-1234-5678-1234-567812345678")
        result = ValueFormatter().format(value)
        assert result.formatted_value == str(value)
        assert result.detected_type == "UUID"

    def test_original_value_is_preserved_unmodified(self) -> None:
        original = Decimal("100.00")
        result = ValueFormatter().format(original)
        assert result.original_value == original
