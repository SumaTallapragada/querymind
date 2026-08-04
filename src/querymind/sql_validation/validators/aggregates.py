"""Checks GROUP BY correctness, HAVING usage, and aggregate-expression nesting.

A deterministic, AST-structural check — comparing each SELECT-list
expression's normalized SQL text against the GROUP BY list — not a full
functional-dependency analysis. Good enough to catch the ordinary
"selected a bare column alongside an aggregate with no GROUP BY" mistake
without requiring semantic knowledge of primary keys or column
functional dependencies.
"""

from __future__ import annotations

from sqlglot import exp

from querymind.sql_validation.models import ValidationIssue, ValidationSeverity
from querymind.sql_validation.parser import ParsedSQL


class AggregateValidator:
    """Validates GROUP BY completeness, HAVING usage, and non-nested aggregate expressions."""

    name = "aggregate"

    def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
        select = parsed.ast
        if not isinstance(select, exp.Select):
            return ()

        issues: list[ValidationIssue] = []
        issues.extend(self._check_group_by(select))
        issues.extend(self._check_having(select))
        issues.extend(self._check_nested_aggregates(select))
        return tuple(issues)

    @staticmethod
    def _check_group_by(select: exp.Select) -> list[ValidationIssue]:
        group = select.args.get("group")
        has_any_aggregate = select.find(exp.AggFunc) is not None
        if group is None and not has_any_aggregate:
            return []

        group_texts = (
            {expression.sql(normalize=True) for expression in group.expressions} if group else set()
        )
        issues: list[ValidationIssue] = []
        for item in select.expressions:
            unaliased = item.this if isinstance(item, exp.Alias) else item
            if unaliased.find(exp.AggFunc) is not None:
                continue
            if isinstance(unaliased, exp.Literal):
                continue
            if unaliased.sql(normalize=True) not in group_texts:
                issues.append(
                    ValidationIssue(
                        code="missing_group_by",
                        severity=ValidationSeverity.ERROR,
                        message=(
                            f"{unaliased.sql()!r} must appear in GROUP BY or be wrapped in an "
                            "aggregate function."
                        ),
                        related_object=unaliased.sql(),
                    )
                )
        return issues

    @staticmethod
    def _check_having(select: exp.Select) -> list[ValidationIssue]:
        having = select.args.get("having")
        if having is None:
            return []
        if select.args.get("group") is None and select.find(exp.AggFunc) is None:
            return [
                ValidationIssue(
                    code="having_without_aggregation",
                    severity=ValidationSeverity.WARNING,
                    message="HAVING is used without GROUP BY or any aggregate function.",
                )
            ]
        return []

    @staticmethod
    def _check_nested_aggregates(select: exp.Select) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for aggregate in select.find_all(exp.AggFunc):
            if aggregate.find_ancestor(exp.AggFunc) is not None:
                issues.append(
                    ValidationIssue(
                        code="nested_aggregate",
                        severity=ValidationSeverity.ERROR,
                        message=(
                            f"{aggregate.sql()!r} is nested inside another aggregate function, "
                            "which is not valid SQL."
                        ),
                        related_object=aggregate.sql(),
                    )
                )
        return issues
