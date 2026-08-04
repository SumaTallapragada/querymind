"""Builds the immutable `SQLValidationResult` from one validation run's raw outputs.

The step between the validator pipeline and the final result — every
validator returns its own flat tuple of `ValidationIssue`s, unaware of
the others; this module is where those are combined with the AST-derived
table/column/function inventory and per-validator timings into one
coherent, immutable report. `SQLValidationEngine` calls this once, at
the very end of `validate()` — it never assembles the result itself.
"""

from __future__ import annotations

from collections.abc import Sequence

from querymind.sql_generation.models import GeneratedSQL
from querymind.sql_validation.models import (
    SQLValidationResult,
    ValidationIssue,
    ValidationSeverity,
    ValidationStatistics,
    ValidatorExecutionTime,
)


def build_result(
    *,
    generated_sql: GeneratedSQL,
    issues: Sequence[ValidationIssue],
    validated_tables: Sequence[str],
    validated_columns: Sequence[str],
    validated_functions: Sequence[str],
    join_count: int,
    validator_execution_times: Sequence[ValidatorExecutionTime],
    validation_latency_ms: float,
) -> SQLValidationResult:
    """Assemble the final `SQLValidationResult` from one run's raw pipeline outputs."""
    errors = tuple(issue for issue in issues if issue.severity is ValidationSeverity.ERROR)
    warnings = tuple(issue for issue in issues if issue.severity is ValidationSeverity.WARNING)

    statistics = ValidationStatistics(
        validation_latency_ms=validation_latency_ms,
        validator_execution_times=tuple(validator_execution_times),
        table_count=len(set(validated_tables)),
        column_count=len(set(validated_columns)),
        join_count=join_count,
        function_count=len(set(validated_functions)),
        error_count=len(errors),
        warning_count=len(warnings),
    )

    return SQLValidationResult(
        generated_sql=generated_sql,
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        validated_tables=tuple(sorted(set(validated_tables))),
        validated_columns=tuple(sorted(set(validated_columns))),
        validated_functions=tuple(sorted(set(validated_functions))),
        validation_statistics=statistics,
    )
