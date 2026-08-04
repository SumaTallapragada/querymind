"""Tests for `querymind.sql_validation.validators.dialect.DialectValidator`."""

from __future__ import annotations

from querymind.sql_validation.parser import ParsedSQL
from querymind.sql_validation.validators.dialect import DialectValidator
from tests.sql_validation.conftest import parse


class TestPostgresCompatibility:
    def test_ordinary_postgres_sql_produces_no_issues(self) -> None:
        issues = DialectValidator().validate(parse("SELECT customer_id FROM customers;"))
        assert issues == ()

    def test_a_query_parsed_under_a_different_dialect_is_rejected(self) -> None:
        parsed = parse("SELECT customer_id FROM customers;", dialect="mysql")
        issues = DialectValidator(dialect="postgres").validate(parsed)
        assert any(issue.code == "unsupported_dialect" for issue in issues)

    def test_matching_the_configured_dialect_never_flags_unsupported_dialect(self) -> None:
        parsed = parse("SELECT customer_id FROM customers;", dialect="mysql")
        issues = DialectValidator(dialect="mysql").validate(parsed)
        assert not any(issue.code == "unsupported_dialect" for issue in issues)


class TestBacktickIdentifiers:
    def test_backtick_quoted_identifiers_are_rejected(self) -> None:
        # Construct a ParsedSQL directly -- backticks in raw_sql are what this check
        # looks at, independent of whether sqlglot's postgres parser tolerated them.
        parsed = parse("SELECT customer_id FROM customers;")
        with_backtick = ParsedSQL(
            ast=parsed.ast, dialect=parsed.dialect, raw_sql="SELECT `customer_id` FROM customers;"
        )
        issues = DialectValidator().validate(with_backtick)
        assert any(issue.code == "unsupported_dialect_construct" for issue in issues)

    def test_ordinary_sql_has_no_backtick_issue(self) -> None:
        issues = DialectValidator().validate(parse("SELECT customer_id FROM customers;"))
        assert not any(issue.related_object == "`" for issue in issues)
