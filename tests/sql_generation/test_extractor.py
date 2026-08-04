"""Tests for `querymind.sql_generation.extractor.SQLExtractor`."""

from __future__ import annotations

import pytest

from querymind.sql_generation.exceptions import SQLExtractionError
from querymind.sql_generation.extractor import SQLExtractor
from querymind.sql_generation.models import ExtractionMethod


class TestPlainText:
    def test_extracts_unfenced_sql_verbatim(self) -> None:
        result = SQLExtractor().extract("SELECT * FROM customers;")
        assert result.sql == "SELECT * FROM customers;"
        assert result.method is ExtractionMethod.RAW_TEXT

    def test_strips_surrounding_whitespace(self) -> None:
        result = SQLExtractor().extract("  \n SELECT 1;  \n")
        assert result.sql == "SELECT 1;"
        assert result.method is ExtractionMethod.RAW_TEXT


class TestSqlFencedBlock:
    def test_extracts_content_of_a_sql_fenced_block(self) -> None:
        response = "Here is the SQL:\n```sql\nSELECT * FROM customers;\n```\nDone."
        result = SQLExtractor().extract(response)
        assert result.sql == "SELECT * FROM customers;"
        assert result.method is ExtractionMethod.FENCED_SQL_BLOCK

    def test_is_case_insensitive_on_the_sql_tag(self) -> None:
        response = "```SQL\nSELECT 1;\n```"
        result = SQLExtractor().extract(response)
        assert result.method is ExtractionMethod.FENCED_SQL_BLOCK

    def test_handles_no_newline_between_tag_and_code(self) -> None:
        response = "```sql SELECT 1;```"
        result = SQLExtractor().extract(response)
        assert result.sql == "SELECT 1;"
        assert result.method is ExtractionMethod.FENCED_SQL_BLOCK

    def test_prefers_sql_fence_over_prose_around_it(self) -> None:
        response = "I'll write this as a SELECT query.\n```sql\nSELECT 1;\n```\nLet me know if you need changes."
        result = SQLExtractor().extract(response)
        assert result.sql == "SELECT 1;"

    def test_multiline_sql_inside_fence(self) -> None:
        response = "```sql\nSELECT\n  customer_id\nFROM customers;\n```"
        result = SQLExtractor().extract(response)
        assert result.sql == "SELECT\n  customer_id\nFROM customers;"


class TestGenericFencedBlock:
    def test_extracts_content_of_an_untagged_fence(self) -> None:
        response = "```\nSELECT 1;\n```"
        result = SQLExtractor().extract(response)
        assert result.sql == "SELECT 1;"
        assert result.method is ExtractionMethod.FENCED_GENERIC_BLOCK

    def test_extracts_content_of_a_differently_tagged_fence(self) -> None:
        response = "```postgresql\nSELECT 1;\n```"
        result = SQLExtractor().extract(response)
        assert result.sql == "SELECT 1;"
        assert result.method is ExtractionMethod.FENCED_GENERIC_BLOCK

    def test_generic_fence_is_only_used_when_no_sql_fence_exists(self) -> None:
        response = "```\nSELECT 1;\n```\n```sql\nSELECT 2;\n```"
        result = SQLExtractor().extract(response)
        assert result.sql == "SELECT 2;"
        assert result.method is ExtractionMethod.FENCED_SQL_BLOCK


class TestExtractionFailures:
    def test_raises_on_entirely_empty_response(self) -> None:
        with pytest.raises(SQLExtractionError):
            SQLExtractor().extract("")

    def test_raises_on_whitespace_only_response(self) -> None:
        with pytest.raises(SQLExtractionError):
            SQLExtractor().extract("   \n\t  ")

    def test_raises_on_empty_sql_fenced_block(self) -> None:
        with pytest.raises(SQLExtractionError):
            SQLExtractor().extract("```sql\n\n```")

    def test_raises_on_empty_generic_fenced_block(self) -> None:
        with pytest.raises(SQLExtractionError):
            SQLExtractor().extract("```\n\n```")
