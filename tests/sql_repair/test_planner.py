"""Tests for `querymind.sql_repair.planner.RepairPlanner`."""

from __future__ import annotations

from querymind.sql_repair.models import RepairReason
from querymind.sql_repair.planner import RepairPlanner
from querymind.sql_validation.models import ValidationSeverity

from .conftest import make_generated_sql, make_issue, make_validation_result


class TestPlanWithErrors:
    def test_a_single_error_produces_one_category(self) -> None:
        generated = make_generated_sql("SELECT * FROM bogus;")
        validation = make_validation_result(generated, errors=(make_issue("unknown_table"),))
        plan = RepairPlanner().plan(validation)
        assert len(plan.categories) == 1
        assert plan.categories[0].reason is RepairReason.UNKNOWN_TABLE
        assert plan.primary_reason is RepairReason.UNKNOWN_TABLE
        assert plan.is_repairable is True

    def test_multiple_issues_of_the_same_reason_are_grouped(self) -> None:
        generated = make_generated_sql("SELECT a, b FROM t;")
        validation = make_validation_result(
            generated, errors=(make_issue("unknown_column"), make_issue("unknown_column"))
        )
        plan = RepairPlanner().plan(validation)
        assert len(plan.categories) == 1
        assert len(plan.categories[0].issues) == 2

    def test_categories_are_sorted_by_priority(self) -> None:
        generated = make_generated_sql("SELECT 1;")
        validation = make_validation_result(
            generated,
            errors=(
                make_issue("unsupported_function"),  # low priority
                make_issue("sql_syntax_error"),  # highest priority
                make_issue("unknown_table"),  # mid priority
            ),
        )
        plan = RepairPlanner().plan(validation)
        reasons = [category.reason for category in plan.categories]
        assert reasons == [
            RepairReason.SYNTAX_ERROR,
            RepairReason.UNKNOWN_TABLE,
            RepairReason.UNSUPPORTED_FUNCTION,
        ]
        assert plan.primary_reason is RepairReason.SYNTAX_ERROR

    def test_unrecognized_code_falls_back_to_other(self) -> None:
        generated = make_generated_sql("SELECT 1;")
        validation = make_validation_result(
            generated, errors=(make_issue("something_new_and_unknown"),)
        )
        plan = RepairPlanner().plan(validation)
        assert plan.primary_reason is RepairReason.OTHER
        assert plan.is_repairable is True


class TestPlanWithoutErrors:
    def test_falls_back_to_warnings_when_no_errors(self) -> None:
        generated = make_generated_sql("SELECT 1;")
        validation = make_validation_result(
            generated,
            warnings=(
                make_issue("business_metric_schema_mismatch", severity=ValidationSeverity.WARNING),
            ),
        )
        plan = RepairPlanner().plan(validation)
        assert plan.primary_reason is RepairReason.BUSINESS_RULE_MISMATCH

    def test_no_issues_at_all_is_not_repairable(self) -> None:
        generated = make_generated_sql("SELECT 1;")
        validation = make_validation_result(generated)
        plan = RepairPlanner().plan(validation)
        assert plan.categories == ()
        assert plan.is_repairable is False


class TestUnrepairablePlans:
    def test_only_internal_validator_errors_are_marked_unrepairable(self) -> None:
        generated = make_generated_sql("SELECT 1;")
        validation = make_validation_result(
            generated, errors=(make_issue("validator_internal_error"),)
        )
        plan = RepairPlanner().plan(validation)
        assert plan.is_repairable is False

    def test_a_mix_of_internal_error_and_real_error_is_still_repairable(self) -> None:
        generated = make_generated_sql("SELECT 1;")
        validation = make_validation_result(
            generated, errors=(make_issue("validator_internal_error"), make_issue("unknown_table"))
        )
        plan = RepairPlanner().plan(validation)
        assert plan.is_repairable is True


class TestSummary:
    def test_summary_mentions_every_category(self) -> None:
        generated = make_generated_sql("SELECT 1;")
        validation = make_validation_result(
            generated, errors=(make_issue("unknown_table"), make_issue("missing_group_by"))
        )
        plan = RepairPlanner().plan(validation)
        assert "unknown_table" in plan.summary
        assert "missing_group_by" in plan.summary
