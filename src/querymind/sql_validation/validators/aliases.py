"""Checks alias declarations and references are consistent, across both tables and output columns.

Independently re-derives table-alias duplicates from the AST rather than
depending on `TableValidator`'s findings (each validator is independent —
this one happens to check an overlapping concern from the "aliases" angle
rather than the "tables" angle, so either can be disabled without losing
alias-duplicate detection entirely) — and additionally covers SELECT-list
output-column aliases, which `TableValidator` never looks at.
"""

from __future__ import annotations

from sqlglot import exp

from querymind.sql_validation.models import ValidationIssue, ValidationSeverity
from querymind.sql_validation.parser import (
    ParsedSQL,
    build_alias_map,
    extract_columns,
    extract_tables,
)


class AliasValidator:
    """Validates duplicate aliases (table and output-column) and unresolvable alias references."""

    name = "alias"

    def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        issues.extend(self._check_duplicate_table_aliases(parsed.ast))
        issues.extend(self._check_duplicate_output_aliases(parsed.ast))
        issues.extend(self._check_unknown_aliases(parsed.ast))
        return tuple(issues)

    @staticmethod
    def _check_duplicate_table_aliases(ast: exp.Expression) -> list[ValidationIssue]:
        counts: dict[str, int] = {}
        for ref in extract_tables(ast):
            if ref.alias:
                counts[ref.alias] = counts.get(ref.alias, 0) + 1
        return [
            ValidationIssue(
                code="duplicate_alias",
                severity=ValidationSeverity.ERROR,
                message=f"Table alias {alias!r} is declared {count} times.",
                related_object=alias,
            )
            for alias, count in counts.items()
            if count > 1
        ]

    @staticmethod
    def _check_duplicate_output_aliases(ast: exp.Expression) -> list[ValidationIssue]:
        if not isinstance(ast, exp.Select):
            return []
        counts: dict[str, int] = {}
        for item in ast.expressions:
            if isinstance(item, exp.Alias) and item.alias:
                counts[item.alias] = counts.get(item.alias, 0) + 1
        return [
            ValidationIssue(
                code="duplicate_alias",
                severity=ValidationSeverity.ERROR,
                message=f"Output column alias {alias!r} is declared {count} times.",
                related_object=alias,
            )
            for alias, count in counts.items()
            if count > 1
        ]

    @staticmethod
    def _check_unknown_aliases(ast: exp.Expression) -> list[ValidationIssue]:
        alias_map = build_alias_map(ast)
        qualifiers = {column.qualifier for column in extract_columns(ast) if column.qualifier}
        return [
            ValidationIssue(
                code="unknown_alias",
                severity=ValidationSeverity.ERROR,
                message=f"Qualifier {qualifier!r} does not match any declared table or alias.",
                related_object=qualifier,
            )
            for qualifier in sorted(qualifiers - alias_map.keys())
        ]
