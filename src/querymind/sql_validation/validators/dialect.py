"""Checks the SQL is PostgreSQL-compatible.

Combines three checks: the SQL was actually parsed as `"postgres"` (the
engine parses using the dialect `GeneratedSQL.dialect` maps to — this
validator, hardcoded to require Postgres specifically per its own scope,
flags anything else); the raw SQL text contains no other dialect's
identifier-quoting syntax; and the AST can be re-rendered as PostgreSQL
SQL without sqlglot raising `UnsupportedError` for a construct its
Postgres generator can't produce.
"""

from __future__ import annotations

from sqlglot.errors import SqlglotError

from querymind.sql_validation.models import ValidationIssue, ValidationSeverity
from querymind.sql_validation.parser import ParsedSQL

#: MySQL-style backtick identifier quoting — not valid PostgreSQL syntax.
_BACKTICK = "`"


class DialectValidator:
    """Validates PostgreSQL compatibility; rejects other-dialect constructs."""

    name = "dialect"

    def __init__(self, dialect: str = "postgres") -> None:
        self._dialect = dialect

    def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []

        if parsed.dialect != self._dialect:
            issues.append(
                ValidationIssue(
                    code="unsupported_dialect",
                    severity=ValidationSeverity.ERROR,
                    message=f"SQL was parsed as dialect {parsed.dialect!r}; only {self._dialect!r} is supported.",
                    related_object=parsed.dialect,
                )
            )

        if _BACKTICK in parsed.raw_sql:
            issues.append(
                ValidationIssue(
                    code="unsupported_dialect_construct",
                    severity=ValidationSeverity.ERROR,
                    message="Backtick-quoted identifiers are not valid PostgreSQL syntax.",
                    related_object=_BACKTICK,
                )
            )

        try:
            parsed.ast.sql(dialect=self._dialect)
        except SqlglotError as exc:
            issues.append(
                ValidationIssue(
                    code="unsupported_dialect_construct",
                    severity=ValidationSeverity.ERROR,
                    message=f"This SQL cannot be rendered for {self._dialect!r}: {exc}",
                )
            )

        return tuple(issues)
