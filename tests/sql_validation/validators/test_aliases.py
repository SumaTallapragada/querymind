"""Tests for `querymind.sql_validation.validators.aliases.AliasValidator`."""

from __future__ import annotations

from querymind.sql_validation.validators.aliases import AliasValidator
from tests.sql_validation.conftest import parse


class TestDuplicateTableAliases:
    def test_two_tables_sharing_an_alias_are_flagged(self) -> None:
        sql = "SELECT * FROM customers c JOIN orders c ON c.customer_id = c.customer_id;"
        issues = AliasValidator().validate(parse(sql))
        duplicates = [i for i in issues if i.code == "duplicate_alias" and i.related_object == "c"]
        assert len(duplicates) == 1

    def test_distinct_table_aliases_produce_no_duplicate_issue(self) -> None:
        sql = "SELECT * FROM customers c JOIN orders o ON o.customer_id = c.customer_id;"
        issues = AliasValidator().validate(parse(sql))
        assert not any(issue.code == "duplicate_alias" for issue in issues)


class TestDuplicateOutputAliases:
    def test_two_select_items_sharing_an_alias_are_flagged(self) -> None:
        sql = "SELECT first_name AS name, last_name AS name FROM customers;"
        issues = AliasValidator().validate(parse(sql))
        duplicates = [
            i for i in issues if i.code == "duplicate_alias" and i.related_object == "name"
        ]
        assert len(duplicates) == 1

    def test_distinct_output_aliases_produce_no_issue(self) -> None:
        sql = "SELECT first_name AS fname, last_name AS lname FROM customers;"
        issues = AliasValidator().validate(parse(sql))
        assert not any(issue.code == "duplicate_alias" for issue in issues)


class TestUnknownAliases:
    def test_a_qualifier_matching_no_table_is_flagged(self) -> None:
        sql = "SELECT z.customer_id FROM customers c;"
        issues = AliasValidator().validate(parse(sql))
        unknown = [i for i in issues if i.code == "unknown_alias"]
        assert len(unknown) == 1
        assert unknown[0].related_object == "z"

    def test_a_qualifier_matching_a_declared_alias_is_not_flagged(self) -> None:
        sql = "SELECT c.customer_id FROM customers c;"
        issues = AliasValidator().validate(parse(sql))
        assert not any(issue.code == "unknown_alias" for issue in issues)

    def test_a_qualifier_matching_the_unaliased_table_name_is_not_flagged(self) -> None:
        sql = "SELECT customers.customer_id FROM customers;"
        issues = AliasValidator().validate(parse(sql))
        assert not any(issue.code == "unknown_alias" for issue in issues)
