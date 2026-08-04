"""Checks every function call is on the approved list.

Reads the AST's function calls exactly as `querymind.sql_validation.parser`
extracted them — a function's name, rendered as it would appear in the
target dialect's SQL — never its arguments' meaning or values.
"""

from __future__ import annotations

from querymind.sql_validation.models import ValidationIssue, ValidationSeverity
from querymind.sql_validation.parser import ParsedSQL, extract_functions

#: The approved function set, per the architecture spec.
APPROVED_FUNCTIONS: frozenset[str] = frozenset(
    {
        "COUNT",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
        "ROUND",
        "COALESCE",
        "CASE",
        "LOWER",
        "UPPER",
        "DATE_TRUNC",
    }
)


class FunctionValidator:
    """Validates every function call referenced in the SQL is on `APPROVED_FUNCTIONS`."""

    name = "function"

    def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        for function in extract_functions(parsed.ast, dialect=parsed.dialect):
            if function.name not in APPROVED_FUNCTIONS:
                issues.append(
                    ValidationIssue(
                        code="unsupported_function",
                        severity=ValidationSeverity.ERROR,
                        message=f"Function {function.name!r} is not in the approved function list.",
                        related_object=function.name,
                    )
                )
        return tuple(issues)
