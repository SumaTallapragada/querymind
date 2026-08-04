"""Tests for `querymind.sql_generation.parser.StatementTypeDetector`."""

from __future__ import annotations

import pytest

from querymind.sql_generation.models import SQLStatementType
from querymind.sql_generation.parser import StatementTypeDetector


class TestDetect:
    @pytest.mark.parametrize(
        ("sql", "expected"),
        [
            ("SELECT * FROM customers;", SQLStatementType.SELECT),
            ("select * from customers;", SQLStatementType.SELECT),
            ("WITH recent AS (SELECT 1) SELECT * FROM recent;", SQLStatementType.WITH),
            ("INSERT INTO customers (id) VALUES (1);", SQLStatementType.INSERT),
            ("UPDATE customers SET name = 'x';", SQLStatementType.UPDATE),
            ("DELETE FROM customers WHERE id = 1;", SQLStatementType.DELETE),
            ("DROP TABLE customers;", SQLStatementType.UNKNOWN),
            ("", SQLStatementType.UNKNOWN),
        ],
    )
    def test_detects_the_leading_keyword(self, sql: str, expected: SQLStatementType) -> None:
        assert StatementTypeDetector().detect(sql) is expected

    def test_ignores_leading_whitespace(self) -> None:
        result = StatementTypeDetector().detect("   \n  SELECT 1;")
        assert result is SQLStatementType.SELECT

    def test_does_not_match_a_keyword_appearing_mid_statement(self) -> None:
        # "SELECTOR" starts with the letters of SELECT but is not the keyword SELECT.
        result = StatementTypeDetector().detect("SELECTOR_TABLE_NAME")
        assert result is SQLStatementType.UNKNOWN
