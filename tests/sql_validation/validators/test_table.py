"""Tests for `querymind.sql_validation.validators.table.TableValidator`."""

from __future__ import annotations

from querymind.metadata.registry import MetadataRegistry
from querymind.sql_validation.validators.table import TableValidator
from tests.sql_validation.conftest import parse


class TestUnknownTable:
    def test_a_nonexistent_table_is_flagged(self, metadata_registry: MetadataRegistry) -> None:
        issues = TableValidator(metadata_registry).validate(
            parse("SELECT * FROM nonexistent_table;")
        )
        assert any(issue.code == "unknown_table" for issue in issues)

    def test_a_real_table_produces_no_unknown_table_issue(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        issues = TableValidator(metadata_registry).validate(parse("SELECT * FROM customers;"))
        assert not any(issue.code == "unknown_table" for issue in issues)

    def test_a_cte_name_is_not_flagged_as_unknown(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        sql = "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent;"
        issues = TableValidator(metadata_registry).validate(parse(sql))
        assert not any(issue.related_object == "recent" for issue in issues)


class TestDuplicateAlias:
    def test_two_different_tables_sharing_an_alias_are_flagged(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        sql = "SELECT * FROM customers c JOIN orders c ON c.customer_id = c.customer_id;"
        issues = TableValidator(metadata_registry).validate(parse(sql))
        duplicate = [i for i in issues if i.code == "duplicate_table_alias"]
        assert len(duplicate) == 1
        assert duplicate[0].related_object == "c"

    def test_distinct_aliases_produce_no_duplicate_issue(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        sql = "SELECT * FROM customers c JOIN orders o ON o.customer_id = c.customer_id;"
        issues = TableValidator(metadata_registry).validate(parse(sql))
        assert not any(issue.code == "duplicate_table_alias" for issue in issues)


class TestAmbiguousTableReference:
    def test_the_same_table_twice_with_no_aliases_is_flagged(
        self, metadata_registry: MetadataRegistry
    ) -> None:
        sql = "SELECT * FROM customers, customers;"
        issues = TableValidator(metadata_registry).validate(parse(sql))
        assert any(issue.code == "ambiguous_table_reference" for issue in issues)

    def test_a_single_reference_is_never_flagged(self, metadata_registry: MetadataRegistry) -> None:
        issues = TableValidator(metadata_registry).validate(parse("SELECT * FROM customers;"))
        assert not any(issue.code == "ambiguous_table_reference" for issue in issues)
