"""Tests for `querymind.sql_validation.validators.column.ColumnValidator`."""

from __future__ import annotations

from querymind.metadata.registry import MetadataRegistry
from querymind.sql_validation.validators.column import ColumnValidator
from tests.sql_validation.conftest import parse


class TestQualifiedColumns:
    def test_a_real_qualified_column_produces_no_issues(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        issues = ColumnValidator(metadata_registry).validate(
            parse("SELECT c.customer_id FROM customers c;")
        )
        assert issues == ()

    def test_a_nonexistent_column_on_a_known_table_is_unknown(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        issues = ColumnValidator(metadata_registry).validate(
            parse("SELECT c.bogus FROM customers c;")
        )
        assert any(issue.code == "unknown_column" for issue in issues)

    def test_a_qualifier_that_matches_no_table_is_invalid_qualification(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        issues = ColumnValidator(metadata_registry).validate(
            parse("SELECT z.customer_id FROM customers c;")
        )
        issue = next(i for i in issues if i.code == "invalid_qualification")
        assert issue.related_object == "z.customer_id"

    def test_a_ctes_columns_are_not_checked(self, metadata_registry: MetadataRegistry) -> None:
        sql = "WITH recent AS (SELECT * FROM orders) SELECT r.anything_at_all FROM recent r;"
        issues = ColumnValidator(metadata_registry).validate(parse(sql))
        assert issues == ()


class TestUnqualifiedColumns:
    def test_a_real_column_with_one_table_in_scope_produces_no_issues(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        issues = ColumnValidator(metadata_registry).validate(
            parse("SELECT customer_id FROM customers;")
        )
        assert issues == ()

    def test_a_nonexistent_column_with_one_table_in_scope_is_unknown(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        issues = ColumnValidator(metadata_registry).validate(
            parse("SELECT bogus_column FROM customers;")
        )
        assert any(issue.code == "unknown_column" for issue in issues)

    def test_a_column_existing_on_two_tables_in_scope_is_ambiguous(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        # customer_id exists on both customers and orders.
        sql = "SELECT customer_id FROM customers c JOIN orders o ON o.customer_id = c.customer_id;"
        issues = ColumnValidator(metadata_registry).validate(parse(sql))
        ambiguous = [
            i for i in issues if i.code == "ambiguous_column" and i.related_object == "customer_id"
        ]
        assert len(ambiguous) == 1

    def test_a_select_list_alias_referenced_elsewhere_is_not_flagged(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        sql = "SELECT total_amount * 1.1 AS adjusted FROM orders ORDER BY adjusted;"
        issues = ColumnValidator(metadata_registry).validate(parse(sql))
        assert not any(issue.related_object == "adjusted" for issue in issues)
