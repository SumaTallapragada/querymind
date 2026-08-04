"""Tests for `querymind.sql_validation.validators.aggregates.AggregateValidator`."""

from __future__ import annotations

from querymind.sql_validation.models import ValidationSeverity
from querymind.sql_validation.validators.aggregates import AggregateValidator
from tests.sql_validation.conftest import parse


class TestGroupByCorrectness:
    def test_a_query_with_no_aggregates_and_no_group_by_produces_no_issues(self) -> None:
        issues = AggregateValidator().validate(
            parse("SELECT customer_id, first_name FROM customers;")
        )
        assert issues == ()

    def test_a_single_aggregate_with_no_bare_columns_needs_no_group_by(self) -> None:
        issues = AggregateValidator().validate(parse("SELECT SUM(total_amount) FROM orders;"))
        assert issues == ()

    def test_a_correct_group_by_produces_no_issues(self) -> None:
        sql = "SELECT customer_id, SUM(total_amount) FROM orders GROUP BY customer_id;"
        issues = AggregateValidator().validate(parse(sql))
        assert issues == ()

    def test_a_bare_column_missing_from_group_by_is_flagged(self) -> None:
        sql = "SELECT customer_id, SUM(total_amount) FROM orders;"
        issues = AggregateValidator().validate(parse(sql))
        missing = [i for i in issues if i.code == "missing_group_by"]
        assert len(missing) == 1
        assert missing[0].related_object == "customer_id"

    def test_a_group_by_with_no_aggregates_still_requires_every_column_listed(self) -> None:
        sql = "SELECT customer_id, first_name FROM customers GROUP BY customer_id;"
        issues = AggregateValidator().validate(parse(sql))
        missing = [i for i in issues if i.code == "missing_group_by"]
        assert len(missing) == 1
        assert missing[0].related_object == "first_name"


class TestHavingUsage:
    def test_having_with_group_by_produces_no_warning(self) -> None:
        sql = "SELECT customer_id FROM orders GROUP BY customer_id HAVING SUM(total_amount) > 10;"
        issues = AggregateValidator().validate(parse(sql))
        assert not any(issue.code == "having_without_aggregation" for issue in issues)

    def test_having_without_group_by_or_aggregates_is_a_warning(self) -> None:
        sql = "SELECT customer_id FROM customers HAVING customer_id > 10;"
        issues = AggregateValidator().validate(parse(sql))
        warning = next(i for i in issues if i.code == "having_without_aggregation")
        assert warning.severity is ValidationSeverity.WARNING

    def test_no_having_clause_produces_no_having_issue(self) -> None:
        issues = AggregateValidator().validate(parse("SELECT customer_id FROM customers;"))
        assert not any(issue.code == "having_without_aggregation" for issue in issues)


class TestNestedAggregates:
    def test_an_aggregate_nested_inside_another_is_flagged(self) -> None:
        issues = AggregateValidator().validate(parse("SELECT SUM(AVG(total_amount)) FROM orders;"))
        nested = [i for i in issues if i.code == "nested_aggregate"]
        assert len(nested) == 1
        assert nested[0].severity is ValidationSeverity.ERROR

    def test_two_separate_aggregates_are_not_nested(self) -> None:
        issues = AggregateValidator().validate(
            parse("SELECT SUM(total_amount), AVG(total_amount) FROM orders;")
        )
        assert not any(issue.code == "nested_aggregate" for issue in issues)
