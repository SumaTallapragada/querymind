"""Tests for `querymind.sql_validation.report.build_result`."""

from __future__ import annotations

from querymind.sql_validation import report
from querymind.sql_validation.models import (
    ValidationIssue,
    ValidationSeverity,
    ValidatorExecutionTime,
)

from .conftest import make_generated_sql


class TestBuildResult:
    def test_no_issues_means_valid(self) -> None:
        result = report.build_result(
            generated_sql=make_generated_sql("SELECT 1;"),
            issues=(),
            validated_tables=(),
            validated_columns=(),
            validated_functions=(),
            join_count=0,
            validator_execution_times=(),
            validation_latency_ms=1.0,
        )
        assert result.is_valid is True
        assert result.errors == ()
        assert result.warnings == ()

    def test_any_error_makes_it_invalid(self) -> None:
        result = report.build_result(
            generated_sql=make_generated_sql("SELECT 1;"),
            issues=(ValidationIssue(code="x", severity=ValidationSeverity.ERROR, message="bad"),),
            validated_tables=(),
            validated_columns=(),
            validated_functions=(),
            join_count=0,
            validator_execution_times=(),
            validation_latency_ms=1.0,
        )
        assert result.is_valid is False
        assert len(result.errors) == 1

    def test_warnings_alone_do_not_make_it_invalid(self) -> None:
        result = report.build_result(
            generated_sql=make_generated_sql("SELECT 1;"),
            issues=(ValidationIssue(code="x", severity=ValidationSeverity.WARNING, message="hmm"),),
            validated_tables=(),
            validated_columns=(),
            validated_functions=(),
            join_count=0,
            validator_execution_times=(),
            validation_latency_ms=1.0,
        )
        assert result.is_valid is True
        assert len(result.warnings) == 1

    def test_errors_and_warnings_are_partitioned_correctly(self) -> None:
        result = report.build_result(
            generated_sql=make_generated_sql("SELECT 1;"),
            issues=(
                ValidationIssue(code="a", severity=ValidationSeverity.ERROR, message="a"),
                ValidationIssue(code="b", severity=ValidationSeverity.WARNING, message="b"),
                ValidationIssue(code="c", severity=ValidationSeverity.ERROR, message="c"),
            ),
            validated_tables=(),
            validated_columns=(),
            validated_functions=(),
            join_count=0,
            validator_execution_times=(),
            validation_latency_ms=1.0,
        )
        assert {i.code for i in result.errors} == {"a", "c"}
        assert {i.code for i in result.warnings} == {"b"}

    def test_deduplicates_and_sorts_validated_tables_columns_functions(self) -> None:
        result = report.build_result(
            generated_sql=make_generated_sql("SELECT 1;"),
            issues=(),
            validated_tables=("orders", "customers", "orders"),
            validated_columns=("orders.id", "orders.id", "customers.id"),
            validated_functions=("SUM", "SUM", "COUNT"),
            join_count=0,
            validator_execution_times=(),
            validation_latency_ms=1.0,
        )
        assert result.validated_tables == ("customers", "orders")
        assert result.validated_columns == ("customers.id", "orders.id")
        assert result.validated_functions == ("COUNT", "SUM")

    def test_statistics_counts_match_deduplicated_inputs(self) -> None:
        result = report.build_result(
            generated_sql=make_generated_sql("SELECT 1;"),
            issues=(),
            validated_tables=("orders", "orders"),
            validated_columns=("orders.id",),
            validated_functions=(),
            join_count=2,
            validator_execution_times=(
                ValidatorExecutionTime(validator="schema", duration_ms=1.0),
            ),
            validation_latency_ms=9.5,
        )
        statistics = result.validation_statistics
        assert statistics.table_count == 1
        assert statistics.column_count == 1
        assert statistics.join_count == 2
        assert statistics.validation_latency_ms == 9.5
        assert len(statistics.validator_execution_times) == 1

    def test_error_and_warning_counts_in_statistics(self) -> None:
        result = report.build_result(
            generated_sql=make_generated_sql("SELECT 1;"),
            issues=(
                ValidationIssue(code="a", severity=ValidationSeverity.ERROR, message="a"),
                ValidationIssue(code="b", severity=ValidationSeverity.WARNING, message="b"),
            ),
            validated_tables=(),
            validated_columns=(),
            validated_functions=(),
            join_count=0,
            validator_execution_times=(),
            validation_latency_ms=1.0,
        )
        assert result.validation_statistics.error_count == 1
        assert result.validation_statistics.warning_count == 1
