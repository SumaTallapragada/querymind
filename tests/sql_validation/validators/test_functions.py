"""Tests for `querymind.sql_validation.validators.functions.FunctionValidator`."""

from __future__ import annotations

import pytest

from querymind.sql_validation.validators.functions import FunctionValidator
from tests.sql_validation.conftest import parse


class TestApprovedFunctions:
    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT COUNT(*) FROM orders;",
            "SELECT SUM(total_amount) FROM orders;",
            "SELECT AVG(total_amount) FROM orders;",
            "SELECT MIN(total_amount) FROM orders;",
            "SELECT MAX(total_amount) FROM orders;",
            "SELECT ROUND(total_amount, 2) FROM orders;",
            "SELECT COALESCE(total_amount, 0) FROM orders;",
            "SELECT CASE WHEN total_amount > 0 THEN 1 ELSE 0 END FROM orders;",
            "SELECT LOWER(first_name) FROM customers;",
            "SELECT UPPER(first_name) FROM customers;",
            "SELECT DATE_TRUNC('month', order_date) FROM orders;",
        ],
    )
    def test_approved_functions_produce_no_issues(self, sql: str) -> None:
        issues = FunctionValidator().validate(parse(sql))
        assert issues == ()

    def test_nested_approved_functions_produce_no_issues(self) -> None:
        issues = FunctionValidator().validate(
            parse("SELECT ROUND(SUM(total_amount), 2) FROM orders;")
        )
        assert issues == ()


class TestUnsupportedFunctions:
    def test_an_unrecognized_function_is_rejected(self) -> None:
        issues = FunctionValidator().validate(
            parse("SELECT MY_CUSTOM_FUNC(total_amount) FROM orders;")
        )
        assert len(issues) == 1
        assert issues[0].code == "unsupported_function"
        assert issues[0].related_object == "MY_CUSTOM_FUNC"

    def test_an_unapproved_builtin_function_is_rejected(self) -> None:
        # STDDEV is a real SQL function sqlglot recognizes, but it's not on the approved list.
        issues = FunctionValidator().validate(parse("SELECT STDDEV(total_amount) FROM orders;"))
        assert any(issue.code == "unsupported_function" for issue in issues)

    def test_one_unsupported_function_among_several_calls_is_reported_individually(self) -> None:
        sql = "SELECT SUM(total_amount), MY_FUNC(customer_id) FROM orders;"
        issues = FunctionValidator().validate(parse(sql))
        assert len(issues) == 1
        assert issues[0].related_object == "MY_FUNC"
