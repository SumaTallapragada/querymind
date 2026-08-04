"""Tests for `querymind.sql_validation.validators.schema.SchemaValidator`."""

from __future__ import annotations

from querymind.metadata.registry import MetadataRegistry
from querymind.sql_validation.validators.schema import SchemaValidator
from tests.sql_validation.conftest import parse


class TestKnownSchema:
    def test_real_tables_and_columns_produce_no_issues(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        sql = "SELECT c.customer_id, c.first_name FROM customers c;"
        issues = SchemaValidator(metadata_registry).validate(parse(sql))
        assert issues == ()

    def test_unqualified_columns_are_not_checked_by_this_validator(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        # SchemaValidator only checks *qualified* columns -- ambiguity/ownership of
        # unqualified columns is ColumnValidator's job.
        sql = "SELECT customer_id FROM customers;"
        issues = SchemaValidator(metadata_registry).validate(parse(sql))
        assert issues == ()


class TestUnknownTable:
    def test_a_nonexistent_table_is_flagged(self, metadata_registry: MetadataRegistry) -> None:
        issues = SchemaValidator(metadata_registry).validate(
            parse("SELECT * FROM nonexistent_table;")
        )
        codes = [issue.code for issue in issues]
        assert "unknown_table" in codes

    def test_the_table_name_is_the_related_object(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        issues = SchemaValidator(metadata_registry).validate(parse("SELECT * FROM ghost_table;"))
        issue = next(i for i in issues if i.code == "unknown_table")
        assert issue.related_object == "ghost_table"


class TestUnknownColumn:
    def test_a_nonexistent_column_on_a_real_table_is_flagged(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        sql = "SELECT c.not_a_real_column FROM customers c;"
        issues = SchemaValidator(metadata_registry).validate(parse(sql))
        codes = [issue.code for issue in issues]
        assert "unknown_column" in codes

    def test_a_column_on_the_wrong_table_is_flagged(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        # order_id doesn't exist on customers.
        sql = "SELECT c.order_id FROM customers c;"
        issues = SchemaValidator(metadata_registry).validate(parse(sql))
        codes = [issue.code for issue in issues]
        assert "unknown_column" in codes


class TestCTEsAreExempt:
    def test_a_cte_name_is_not_flagged_as_an_unknown_table(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        sql = "WITH recent AS (SELECT * FROM orders) " "SELECT r.order_id FROM recent r;"
        issues = SchemaValidator(metadata_registry).validate(parse(sql))
        assert not any(issue.related_object == "recent" for issue in issues)


class TestSchemaQualifier:
    def test_the_public_schema_is_accepted(self, metadata_registry: MetadataRegistry) -> None:
        issues = SchemaValidator(metadata_registry).validate(
            parse("SELECT * FROM public.customers;")
        )
        assert not any(issue.code == "unknown_schema" for issue in issues)

    def test_a_non_public_schema_is_rejected(self, metadata_registry: MetadataRegistry) -> None:
        issues = SchemaValidator(metadata_registry).validate(
            parse("SELECT * FROM other_schema.customers;")
        )
        codes = [issue.code for issue in issues]
        assert "unknown_schema" in codes
