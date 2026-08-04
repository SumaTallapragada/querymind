"""Tests for `querymind.sql_generation.normalizer.SQLNormalizer`."""

from __future__ import annotations

from querymind.sql_generation.normalizer import SQLNormalizer


class TestWhitespace:
    def test_strips_leading_and_trailing_whitespace(self) -> None:
        result = SQLNormalizer().normalize("  \n SELECT 1  \n ")
        assert result == "SELECT 1;"

    def test_leaves_internal_whitespace_untouched(self) -> None:
        result = SQLNormalizer().normalize("SELECT\n  customer_id\nFROM customers")
        assert result == "SELECT\n  customer_id\nFROM customers;"


class TestLineEndings:
    def test_converts_crlf_to_lf(self) -> None:
        result = SQLNormalizer().normalize("SELECT 1\r\nFROM customers")
        assert "\r" not in result
        assert result == "SELECT 1\nFROM customers;"

    def test_converts_bare_cr_to_lf(self) -> None:
        result = SQLNormalizer().normalize("SELECT 1\rFROM customers")
        assert "\r" not in result
        assert result == "SELECT 1\nFROM customers;"


class TestTrailingSemicolon:
    def test_adds_a_semicolon_when_missing(self) -> None:
        result = SQLNormalizer().normalize("SELECT 1")
        assert result == "SELECT 1;"

    def test_collapses_multiple_trailing_semicolons_to_one(self) -> None:
        result = SQLNormalizer().normalize("SELECT 1;;;")
        assert result == "SELECT 1;"

    def test_collapses_a_semicolon_followed_by_whitespace(self) -> None:
        result = SQLNormalizer().normalize("SELECT 1;   \n\n")
        assert result == "SELECT 1;"

    def test_leaves_an_already_single_trailing_semicolon_unchanged(self) -> None:
        result = SQLNormalizer().normalize("SELECT 1;")
        assert result == "SELECT 1;"

    def test_does_not_touch_semicolons_that_are_not_trailing(self) -> None:
        result = SQLNormalizer().normalize("SELECT 1; SELECT 2")
        assert result == "SELECT 1; SELECT 2;"


class TestNeverChangesMeaning:
    def test_never_changes_keyword_casing(self) -> None:
        result = SQLNormalizer().normalize("select customer_id from customers")
        assert result == "select customer_id from customers;"

    def test_never_reindents_or_reflows(self) -> None:
        sql = "SELECT\n    a,\n        b\nFROM t"
        result = SQLNormalizer().normalize(sql)
        assert result == "SELECT\n    a,\n        b\nFROM t;"
