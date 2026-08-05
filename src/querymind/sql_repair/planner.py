"""Converts validation issues into repair categories, priority, and a summary.

`RepairPlanner` never builds prompts and never calls an LLM — it only
reads a `SQLValidationResult` and produces a `RepairPlan` describing
*what* needs fixing and in what order, for `RepairPromptBuilder` and
`SQLRepairEngine` to act on.
"""

from __future__ import annotations

from dataclasses import dataclass

from querymind.sql_repair.models import RepairReason
from querymind.sql_validation.models import SQLValidationResult, ValidationIssue

#: Maps a `ValidationIssue.code` (as produced by `querymind.sql_validation`'s
#: validators) onto the `RepairReason` category it belongs to. Any code not
#: listed here falls back to `RepairReason.OTHER`.
_ISSUE_CODE_TO_REASON: dict[str, RepairReason] = {
    "sql_syntax_error": RepairReason.SYNTAX_ERROR,
    "unsupported_statement_type": RepairReason.UNSUPPORTED_STATEMENT,
    "unknown_table": RepairReason.UNKNOWN_TABLE,
    "unknown_schema": RepairReason.SCHEMA_ISSUE,
    "ambiguous_table_reference": RepairReason.SCHEMA_ISSUE,
    "unknown_column": RepairReason.UNKNOWN_COLUMN,
    "ambiguous_column": RepairReason.UNKNOWN_COLUMN,
    "invalid_qualification": RepairReason.ALIAS_ISSUE,
    "duplicate_table_alias": RepairReason.ALIAS_ISSUE,
    "duplicate_alias": RepairReason.ALIAS_ISSUE,
    "unknown_alias": RepairReason.ALIAS_ISSUE,
    "unknown_join_relationship": RepairReason.INVALID_JOIN,
    "join_columns_do_not_match_relationship": RepairReason.INVALID_JOIN,
    "missing_group_by": RepairReason.MISSING_GROUP_BY,
    "having_without_aggregation": RepairReason.AGGREGATE_ERROR,
    "nested_aggregate": RepairReason.AGGREGATE_ERROR,
    "unsupported_function": RepairReason.UNSUPPORTED_FUNCTION,
    "unsupported_dialect": RepairReason.DIALECT_ISSUE,
    "unsupported_dialect_construct": RepairReason.DIALECT_ISSUE,
    "business_metric_schema_mismatch": RepairReason.BUSINESS_RULE_MISMATCH,
}

#: Fix-this-first ordering. A category not listed here sorts last (see `_priority_for`).
_REASON_PRIORITY: dict[RepairReason, int] = {
    RepairReason.SYNTAX_ERROR: 0,
    RepairReason.UNSUPPORTED_STATEMENT: 1,
    RepairReason.UNKNOWN_TABLE: 2,
    RepairReason.SCHEMA_ISSUE: 3,
    RepairReason.UNKNOWN_COLUMN: 4,
    RepairReason.ALIAS_ISSUE: 5,
    RepairReason.INVALID_JOIN: 6,
    RepairReason.MISSING_GROUP_BY: 7,
    RepairReason.AGGREGATE_ERROR: 8,
    RepairReason.UNSUPPORTED_FUNCTION: 9,
    RepairReason.DIALECT_ISSUE: 10,
    RepairReason.BUSINESS_RULE_MISMATCH: 11,
    RepairReason.OTHER: 99,
}

#: Issue codes that represent an internal validator crash, not a real SQL
#: problem an LLM rewrite could plausibly fix.
_UNREPAIRABLE_CODES = frozenset({"validator_internal_error"})


def _priority_for(reason: RepairReason) -> int:
    return _REASON_PRIORITY.get(reason, 99)


@dataclass(frozen=True, slots=True)
class RepairCategory:
    """Every validation issue sharing one `RepairReason`, in priority order."""

    reason: RepairReason
    priority: int
    issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True, slots=True)
class RepairPlan:
    """What `RepairPromptBuilder`/`SQLRepairEngine` need to act on one validation result."""

    categories: tuple[RepairCategory, ...]
    primary_reason: RepairReason
    summary: str
    is_repairable: bool


class RepairPlanner:
    """Deterministically categorizes a `SQLValidationResult`'s issues into a `RepairPlan`."""

    def plan(self, validation_result: SQLValidationResult) -> RepairPlan:
        """Build a `RepairPlan` from `validation_result`. Never builds a prompt or calls an LLM."""
        issues = validation_result.errors or validation_result.warnings
        if not issues:
            return RepairPlan(
                categories=(),
                primary_reason=RepairReason.OTHER,
                summary="No validation issues to repair.",
                is_repairable=False,
            )

        grouped: dict[RepairReason, list[ValidationIssue]] = {}
        for issue in issues:
            reason = _ISSUE_CODE_TO_REASON.get(issue.code, RepairReason.OTHER)
            grouped.setdefault(reason, []).append(issue)

        categories = tuple(
            RepairCategory(
                reason=reason, priority=_priority_for(reason), issues=tuple(grouped_issues)
            )
            for reason, grouped_issues in sorted(
                grouped.items(), key=lambda item: _priority_for(item[0])
            )
        )
        primary_reason = categories[0].reason
        is_repairable = not all(issue.code in _UNREPAIRABLE_CODES for issue in issues)

        return RepairPlan(
            categories=categories,
            primary_reason=primary_reason,
            summary=self._build_summary(categories),
            is_repairable=is_repairable,
        )

    @staticmethod
    def _build_summary(categories: tuple[RepairCategory, ...]) -> str:
        parts = [f"{category.reason.value} ({len(category.issues)})" for category in categories]
        return "Repair needed: " + ", ".join(parts) + "."
