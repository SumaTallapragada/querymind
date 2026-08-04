"""Tests for `querymind.sql_validation.models`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from querymind.sql_validation.models import (
    SQLValidationResult,
    ValidationIssue,
    ValidationSeverity,
    ValidationStatistics,
    ValidationWarning,
    ValidatorExecutionTime,
)

from .conftest import make_generated_sql


def _statistics(**overrides: object) -> ValidationStatistics:
    defaults: dict[str, object] = {
        "validation_latency_ms": 5.0,
        "validator_execution_times": (),
        "table_count": 1,
        "column_count": 2,
        "join_count": 0,
        "function_count": 0,
        "error_count": 0,
        "warning_count": 0,
    }
    defaults.update(overrides)
    return ValidationStatistics(**defaults)  # type: ignore[arg-type]


class TestValidationIssue:
    def test_construction_with_only_required_fields(self) -> None:
        issue = ValidationIssue(
            code="unknown_table", severity=ValidationSeverity.ERROR, message="x"
        )
        assert issue.location is None
        assert issue.related_object is None

    def test_is_frozen(self) -> None:
        issue = ValidationIssue(code="x", severity=ValidationSeverity.ERROR, message="x")
        with pytest.raises(ValidationError):
            issue.code = "y"  # type: ignore[misc]


class TestValidationWarning:
    def test_severity_defaults_to_warning(self) -> None:
        warning = ValidationWarning(code="x", message="x")
        assert warning.severity is ValidationSeverity.WARNING

    def test_is_a_validation_issue(self) -> None:
        warning = ValidationWarning(code="x", message="x")
        assert isinstance(warning, ValidationIssue)


class TestValidationStatistics:
    def test_valid_construction(self) -> None:
        statistics = _statistics()
        assert statistics.table_count == 1

    def test_rejects_negative_counts(self) -> None:
        with pytest.raises(ValidationError):
            _statistics(table_count=-1)

    def test_is_frozen(self) -> None:
        statistics = _statistics()
        with pytest.raises(ValidationError):
            statistics.table_count = 5  # type: ignore[misc]


class TestValidatorExecutionTime:
    def test_rejects_negative_duration(self) -> None:
        with pytest.raises(ValidationError):
            ValidatorExecutionTime(validator="schema", duration_ms=-1.0)


class TestSQLValidationResult:
    def test_valid_construction(self) -> None:
        generated = make_generated_sql("SELECT 1;")
        result = SQLValidationResult(
            generated_sql=generated,
            is_valid=True,
            errors=(),
            warnings=(),
            validated_tables=(),
            validated_columns=(),
            validated_functions=(),
            validation_statistics=_statistics(),
        )
        assert result.is_valid is True
        assert result.generated_sql == generated

    def test_is_frozen(self) -> None:
        result = SQLValidationResult(
            generated_sql=make_generated_sql("SELECT 1;"),
            is_valid=True,
            validation_statistics=_statistics(),
        )
        with pytest.raises(ValidationError):
            result.is_valid = False  # type: ignore[misc]

    def test_unknown_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SQLValidationResult(
                generated_sql=make_generated_sql("SELECT 1;"),
                is_valid=True,
                validation_statistics=_statistics(),
                bogus="nope",
            )  # type: ignore[call-arg]

    def test_defaults_are_empty_tuples(self) -> None:
        result = SQLValidationResult(
            generated_sql=make_generated_sql("SELECT 1;"),
            is_valid=True,
            validation_statistics=_statistics(),
        )
        assert result.errors == ()
        assert result.warnings == ()
        assert result.validated_tables == ()
