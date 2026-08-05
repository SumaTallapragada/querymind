"""Tests for `querymind.sql_repair.models`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from querymind.sql_repair.models import (
    RepairAttempt,
    RepairHistory,
    RepairReason,
    RepairStatistics,
    RepairStatus,
    SQLRepairResult,
)

from .conftest import make_generated_sql, make_llm_response, make_validation_result


def _attempt(**overrides: object) -> RepairAttempt:
    generated = make_generated_sql("SELECT 1;")
    defaults: dict[str, object] = {
        "attempt_number": 1,
        "repair_reason": RepairReason.UNKNOWN_TABLE,
        "input_sql": "SELECT * FROM bogus;",
        "repaired_sql": "SELECT 1;",
        "validation_result": make_validation_result(generated),
        "prompt_version": "1.0.0-repair",
        "llm_metrics": make_llm_response().metrics,
        "success": True,
    }
    defaults.update(overrides)
    return RepairAttempt(**defaults)  # type: ignore[arg-type]


def _statistics(**overrides: object) -> RepairStatistics:
    defaults: dict[str, object] = {
        "attempt_count": 1,
        "successful_repairs": 1,
        "failed_repairs": 0,
        "repair_latency_ms": 5.0,
        "average_validation_latency_ms": 1.0,
    }
    defaults.update(overrides)
    return RepairStatistics(**defaults)  # type: ignore[arg-type]


class TestRepairAttempt:
    def test_valid_construction(self) -> None:
        attempt = _attempt()
        assert attempt.success is True
        assert attempt.repair_reason is RepairReason.UNKNOWN_TABLE

    def test_rejects_attempt_number_below_one(self) -> None:
        with pytest.raises(ValidationError):
            _attempt(attempt_number=0)

    def test_is_frozen(self) -> None:
        attempt = _attempt()
        with pytest.raises(ValidationError):
            attempt.success = False  # type: ignore[misc]


class TestRepairHistory:
    def test_defaults_to_empty(self) -> None:
        history = RepairHistory()
        assert history.attempts == ()
        assert history.attempt_count == 0
        assert history.last_attempt is None

    def test_attempt_count_and_last_attempt(self) -> None:
        first = _attempt(attempt_number=1, success=False)
        second = _attempt(attempt_number=2, success=True)
        history = RepairHistory(attempts=(first, second))
        assert history.attempt_count == 2
        assert history.last_attempt == second


class TestRepairStatistics:
    def test_valid_construction(self) -> None:
        statistics = _statistics()
        assert statistics.attempt_count == 1

    def test_rejects_negative_counts(self) -> None:
        with pytest.raises(ValidationError):
            _statistics(attempt_count=-1)

    def test_is_frozen(self) -> None:
        statistics = _statistics()
        with pytest.raises(ValidationError):
            statistics.attempt_count = 5  # type: ignore[misc]


class TestSQLRepairResult:
    def test_valid_construction(self) -> None:
        generated = make_generated_sql("SELECT 1;")
        result = SQLRepairResult(
            original_sql=generated,
            final_sql=generated,
            final_validation_result=make_validation_result(generated),
            history=RepairHistory(),
            statistics=_statistics(),
            status=RepairStatus.REPAIRED,
        )
        assert result.status is RepairStatus.REPAIRED

    def test_is_frozen(self) -> None:
        generated = make_generated_sql("SELECT 1;")
        result = SQLRepairResult(
            original_sql=generated,
            final_sql=generated,
            final_validation_result=make_validation_result(generated),
            history=RepairHistory(),
            statistics=_statistics(),
            status=RepairStatus.REPAIRED,
        )
        with pytest.raises(ValidationError):
            result.status = RepairStatus.UNREPAIRABLE  # type: ignore[misc]

    def test_unknown_fields_are_rejected(self) -> None:
        generated = make_generated_sql("SELECT 1;")
        with pytest.raises(ValidationError):
            SQLRepairResult(
                original_sql=generated,
                final_sql=generated,
                final_validation_result=make_validation_result(generated),
                history=RepairHistory(),
                statistics=_statistics(),
                status=RepairStatus.REPAIRED,
                bogus="nope",
            )  # type: ignore[call-arg]
