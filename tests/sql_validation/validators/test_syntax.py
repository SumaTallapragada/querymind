"""Tests for `querymind.sql_validation.validators.syntax.SyntaxValidator`."""

from __future__ import annotations

from querymind.sql_validation.models import ValidationSeverity
from querymind.sql_validation.validators.syntax import SyntaxValidator
from tests.sql_validation.conftest import parse


class TestSupportedStatements:
    def test_a_simple_select_statement_produces_no_issues(self) -> None:
        issues = SyntaxValidator().validate(parse("SELECT 1;"))
        assert issues == ()

    def test_a_select_with_joins_and_aggregates_produces_no_issues(self) -> None:
        sql = "SELECT customer_id, SUM(total_amount) FROM orders GROUP BY customer_id;"
        issues = SyntaxValidator().validate(parse(sql))
        assert issues == ()

    def test_a_with_cte_select_produces_no_issues(self) -> None:
        sql = """
            WITH sales AS (
                SELECT * FROM orders
            )
            SELECT * FROM sales;
        """
        issues = SyntaxValidator().validate(parse(sql))
        assert issues == ()

    def test_a_nested_cte_produces_no_issues(self) -> None:
        sql = """
            WITH a AS (
                SELECT 1 AS x
            ),
            b AS (
                SELECT x FROM a
            )
            SELECT * FROM b;
        """
        issues = SyntaxValidator().validate(parse(sql))
        assert issues == ()


class TestUnsupportedStatements:
    def test_an_insert_statement_is_rejected(self) -> None:
        issues = SyntaxValidator().validate(parse("INSERT INTO customers (id) VALUES (1);"))
        assert len(issues) == 1
        assert issues[0].code == "unsupported_statement_type"
        assert issues[0].severity is ValidationSeverity.ERROR
        assert issues[0].related_object == "INSERT"
        assert issues[0].message == "Statement type 'INSERT' is not supported by QueryMind."

    def test_an_update_statement_is_rejected(self) -> None:
        issues = SyntaxValidator().validate(parse("UPDATE customers SET first_name = 'x';"))
        assert issues[0].code == "unsupported_statement_type"
        assert issues[0].related_object == "UPDATE"

    def test_a_delete_statement_is_rejected(self) -> None:
        issues = SyntaxValidator().validate(parse("DELETE FROM customers;"))
        assert issues[0].code == "unsupported_statement_type"
        assert issues[0].related_object == "DELETE"

    def test_a_create_statement_is_rejected(self) -> None:
        issues = SyntaxValidator().validate(parse("CREATE TABLE t (a INT);"))
        assert issues[0].code == "unsupported_statement_type"
        assert issues[0].related_object == "CREATE"

    def test_a_drop_statement_is_rejected(self) -> None:
        issues = SyntaxValidator().validate(parse("DROP TABLE customers;"))
        assert issues[0].code == "unsupported_statement_type"
        assert issues[0].related_object == "DROP"

    def test_an_alter_statement_is_rejected(self) -> None:
        issues = SyntaxValidator().validate(parse("ALTER TABLE customers ADD COLUMN x INT;"))
        assert issues[0].code == "unsupported_statement_type"
        assert issues[0].related_object == "ALTER"

    def test_a_merge_statement_is_rejected(self) -> None:
        sql = "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN UPDATE SET a = 1;"
        issues = SyntaxValidator().validate(parse(sql))
        assert issues[0].code == "unsupported_statement_type"
        assert issues[0].related_object == "MERGE"

    def test_a_with_cte_prefixed_insert_is_still_rejected(self) -> None:
        # A CTE prefix doesn't launder an otherwise-unsupported statement type --
        # the root node here is Insert, not Select.
        sql = "WITH x AS (SELECT 1 AS a) INSERT INTO t SELECT * FROM x;"
        issues = SyntaxValidator().validate(parse(sql))
        assert issues[0].code == "unsupported_statement_type"
        assert issues[0].related_object == "INSERT"

    def test_exactly_one_issue_is_reported(self) -> None:
        issues = SyntaxValidator().validate(parse("DELETE FROM customers;"))
        assert len(issues) == 1
