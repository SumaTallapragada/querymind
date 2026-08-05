"""Tests for `querymind.sql_repair.strategy.RepairStrategy`."""

from __future__ import annotations

import pytest

from querymind.sql_repair.exceptions import SQLRepairConfigurationError
from querymind.sql_repair.models import RepairAttempt, RepairReason, RepairStatus
from querymind.sql_repair.strategy import DEFAULT_MAX_ATTEMPTS, RepairStrategy

from .conftest import make_generated_sql, make_issue, make_llm_response, make_validation_result


def _attempt(
    *, attempt_number: int, success: bool, error_codes: tuple[str, ...] = ()
) -> RepairAttempt:
    generated = make_generated_sql("SELECT 1;")
    validation = make_validation_result(
        generated, errors=tuple(make_issue(code) for code in error_codes) if not success else ()
    )
    return RepairAttempt(
        attempt_number=attempt_number,
        repair_reason=RepairReason.UNKNOWN_TABLE,
        input_sql="SELECT * FROM bogus;",
        repaired_sql="SELECT 1;",
        validation_result=validation,
        prompt_version="1.0.0-repair",
        llm_metrics=make_llm_response().metrics,
        success=success,
    )


class TestConstruction:
    def test_default_max_attempts(self) -> None:
        strategy = RepairStrategy()
        assert strategy.max_attempts == DEFAULT_MAX_ATTEMPTS

    def test_rejects_max_attempts_below_one(self) -> None:
        with pytest.raises(SQLRepairConfigurationError):
            RepairStrategy(0)

    def test_allows_max_attempts_of_one(self) -> None:
        strategy = RepairStrategy(1)
        assert strategy.max_attempts == 1


class TestShouldContinue:
    def test_stops_immediately_on_empty_history(self) -> None:
        assert RepairStrategy().should_continue(()) is False

    def test_stops_after_a_successful_attempt(self) -> None:
        history = (_attempt(attempt_number=1, success=True),)
        assert RepairStrategy().should_continue(history) is False

    def test_continues_after_one_failed_attempt_under_max(self) -> None:
        history = (_attempt(attempt_number=1, success=False, error_codes=("unknown_table",)),)
        assert RepairStrategy(3).should_continue(history) is True

    def test_stops_once_max_attempts_reached(self) -> None:
        history = tuple(
            _attempt(attempt_number=n, success=False, error_codes=("unknown_table",))
            for n in range(1, 4)
        )
        assert RepairStrategy(3).should_continue(history) is False

    def test_stops_when_consecutive_attempts_report_the_same_errors(self) -> None:
        history = (
            _attempt(attempt_number=1, success=False, error_codes=("unknown_table",)),
            _attempt(attempt_number=2, success=False, error_codes=("unknown_table",)),
        )
        assert RepairStrategy(5).should_continue(history) is False

    def test_continues_when_consecutive_attempts_report_different_errors(self) -> None:
        history = (
            _attempt(attempt_number=1, success=False, error_codes=("unknown_table",)),
            _attempt(attempt_number=2, success=False, error_codes=("unknown_column",)),
        )
        assert RepairStrategy(5).should_continue(history) is True


class TestFinalStatus:
    def test_empty_history_is_unrepairable(self) -> None:
        assert RepairStrategy().final_status(()) is RepairStatus.UNREPAIRABLE

    def test_a_successful_last_attempt_is_repaired(self) -> None:
        history = (
            _attempt(attempt_number=1, success=False, error_codes=("unknown_table",)),
            _attempt(attempt_number=2, success=True),
        )
        assert RepairStrategy().final_status(history) is RepairStatus.REPAIRED

    def test_exhausting_max_attempts_is_max_attempts_reached(self) -> None:
        history = tuple(
            _attempt(attempt_number=n, success=False, error_codes=(f"code_{n}",))
            for n in range(1, 4)
        )
        assert RepairStrategy(3).final_status(history) is RepairStatus.MAX_ATTEMPTS_REACHED

    def test_no_progress_between_last_two_attempts_is_no_progress(self) -> None:
        history = (
            _attempt(attempt_number=1, success=False, error_codes=("unknown_table",)),
            _attempt(attempt_number=2, success=False, error_codes=("unknown_table",)),
        )
        assert RepairStrategy(5).final_status(history) is RepairStatus.NO_PROGRESS
